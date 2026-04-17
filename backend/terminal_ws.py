# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — Web Terminal (SSH PTY 双向代理)
@Version: 2.0.0
@Date: 2026-03-28

功能: 通过 WebSocket 将浏览器终端连接到目标服务器运行中的容器。
支持工单粒度接入、docker attach 断线防杀机制、Docker API Resize、自动恢复对话（auto_resume）。
"""

import asyncio
import json
import logging

import asyncssh
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt

from config import settings
from crypto import decrypt_password
from database import get_pool

logger = logging.getLogger("ones-ai.terminal")
router = APIRouter(tags=["Terminal"])

# 活跃终端会话跟踪 (ticket_db_id -> set of sessions)
_active_sessions: dict[int, set] = {}


@router.websocket("/ws/tickets/{ticket_db_id}/terminal")
async def terminal_ws(websocket: WebSocket, ticket_db_id: int, 
                      token: str = Query(""), auto_resume: bool = Query(False)):
    """
    工单级 Web Terminal WebSocket 端点
    
    连接: ws://host/ws/tickets/{ticket_db_id}/terminal?token=<JWT>&auto_resume=true
    """
    # ---- 1. JWT 验证 ----
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = int(payload.get("sub", 0))
        role = payload.get("role", "user")
    except (JWTError, Exception):
        await websocket.close(code=4001, reason="Token 无效")
        return

    # ---- 2. 权限校验 + 查询容器信息 ----
    pool = await get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow("""
            SELECT tt.id, tt.task_id, tt.container_name, tt.status as ticket_status,
                   tt.conversation_id,
                   t.user_id, t.server_id,
                   usc.ssh_username, usc.ssh_password_encrypted,
                   s.host, s.ssh_port
            FROM task_tickets tt
            JOIN tasks t ON t.id = tt.task_id
            JOIN user_server_credentials usc ON usc.id = t.credential_id
            JOIN servers s ON s.id = t.server_id
            WHERE tt.id = $1
        """, ticket_db_id)

    if not record:
        await websocket.close(code=4004, reason="工单不存在")
        return
    if record["user_id"] != user_id and role != "admin":
        await websocket.close(code=4003, reason="无权限")
        return
    
    container_name = record["container_name"] or ""
    if not container_name:
        await websocket.close(code=4005, reason="该工单尚未绑定容器，无法接入")
        return
    # 安全校验：防止命令注入
    import re
    if not re.fullmatch(r'ones-ai-[\w-]+', container_name):
        await websocket.close(code=4005, reason="容器名格式异常，拒绝接入")
        return

    # ---- 3. 建立 SSH 连接 ----
    ssh_conn = None
    ssh_process = None
    is_intervene = False

    try:
        ssh_password = decrypt_password(record["ssh_password_encrypted"])
        ssh_conn = await asyncio.wait_for(
            asyncssh.connect(
                record["host"],
                port=record["ssh_port"],
                username=record["ssh_username"],
                password=ssh_password,
                known_hosts=None,
            ),
            timeout=15,
        )

        # 检查容器状态
        status_res = await ssh_conn.run(f"docker inspect -f '{{{{.State.Running}}}}' {container_name}")
        if status_res.stdout.strip() != "true":
            await websocket.close(code=4006, reason=f"容器 {container_name} 暂未运行，请先唤醒")
            ssh_conn.close()
            return
            
        # 统一终端接入策略：观测(只读日志) vs 干预(交互式)
        is_intervene = "intervene" in container_name
        if is_intervene:
            saved_conv_id = (record.get("conversation_id") or "").strip()
            # 预检: session 文件必须存在才能 resume, 否则当"首次干预"处理
            # (session 存放位置: 容器内 $HOME/.claude/projects/*/<sessionId>.jsonl)
            if saved_conv_id:
                check = await ssh_conn.run(
                    f"docker exec {container_name} bash -c "
                    f"'ls $HOME/.claude/projects/*/{saved_conv_id}.jsonl 2>/dev/null | head -1'"
                )
                if not check.stdout.strip():
                    logger.info(f"conversation_id {saved_conv_id} 对应 session 不存在, 走首次干预路径")
                    saved_conv_id = ""

            if saved_conv_id:
                # 后续干预: resume 上次会话
                # claude CLI 的 resume 语法是 `claude --resume <sessionId>` (位置参数, 不是 --conversation-id)
                # 用 exec 让 claude 替换 bash 进程 — 否则 claude 作为 bash 子进程,
                # docker exec -it 分配的 TTY 前台控制权留在 bash 那里, claude 拿不到键盘输入
                cmd = (f"docker exec -it {container_name} bash -c "
                       f"'echo \"🔧 恢复干预会话: {saved_conv_id}\" && "
                       f"exec claude --resume {saved_conv_id}'")
            else:
                # 首次干预：用 auto_resume.sh
                has_resume = await ssh_conn.run(
                    f"docker exec {container_name} test -f /tmp/auto_resume.sh && echo yes || echo no"
                )
                if has_resume.stdout.strip() == "yes":
                    await ssh_conn.run(f"docker exec {container_name} rm -f /tmp/.claude_resumed")
                    cmd = f"docker exec -it {container_name} bash --rcfile /tmp/auto_resume.sh"
                else:
                    cmd = f"docker exec -it {container_name} bash"
        else:
            # 任务容器（运行中）：观测模式，持续查看日志，防止乱入字符干扰主进程
            cmd = f"docker logs -f --tail 100 {container_name}"

        ssh_process = await ssh_conn.create_process(
            cmd,
            term_type="xterm-256color",
            term_size=(80, 24), # 初始大小
            encoding=None,      # bytes 模式
        )

    except asyncio.TimeoutError:
        await websocket.close(code=4008, reason="SSH 建立连接超时")
        return
    except Exception as e:
        logger.error(f"Terminal SSH 连接失败: {e}")
        await websocket.close(code=4010, reason=f"SSH 连接失败: {str(e)[:100]}")
        if ssh_conn:
            ssh_conn.close()
        return

    # ---- 4. WebSocket 握手 ----
    await websocket.accept()
    logger.info(f"Terminal 已连接: ticket={ticket_db_id}, container={container_name}")
    
    _active_sessions.setdefault(ticket_db_id, set()).add(id(websocket))

    # ---- 5. 双向代理 ----
    async def _handle_resize(cols: int, rows: int):
        """利用 Docker Engine API 发送 resize 信号给 attach 的容器"""
        try:
            # ssh_process.change_terminal_size 无法把信号透传给 docker attach 内部
            # 必须调用 Docker API: POST /containers/{id}/resize?h=<height>&w=<width>
            resize_cmd = (
                f"curl -s --unix-socket /var/run/docker.sock -X POST "
                f"\"http://localhost/containers/{container_name}/resize?h={rows}&w={cols}\" "
                f"> /dev/null 2>&1"
            )
            await ssh_conn.run(resize_cmd)
        except Exception as e:
            logger.debug(f"Docker resize API failed: {e}")

    async def _ssh_to_ws():
        """SSH stdout/stderr → WebSocket (binary)"""
        try:
            while True:
                data = await ssh_process.stdout.read(4096)
                if not data:
                    break
                await websocket.send_bytes(data)
        except (WebSocketDisconnect, Exception):
            pass

    async def _ws_to_ssh():
        """WebSocket → SSH stdin"""
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break

                if "bytes" in msg and msg["bytes"]:
                    # 观测模式下不转发键盘输入（docker logs -f 不读 stdin）
                    if is_intervene:
                        ssh_process.stdin.write(msg["bytes"])
                elif "text" in msg and msg["text"]:
                    try:
                        cmd = json.loads(msg["text"])
                        if cmd.get("type") == "resize":
                            cols = int(cmd.get("cols", 80))
                            rows = int(cmd.get("rows", 24))
                            ssh_process.change_terminal_size(cols, rows) # 改变本地 PTY 大小
                            await _handle_resize(cols, rows)            # 改变 Docker PTY 大小
                    except Exception:
                        pass
        except (WebSocketDisconnect, Exception):
            pass

    # 并发运行收发协程
    try:
        done, pending = await asyncio.wait(
            [asyncio.create_task(_ssh_to_ws()), asyncio.create_task(_ws_to_ssh())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    except Exception as e:
        logger.warning(f"Terminal 会话异常: {e}")
    finally:
        # ---- 6. 清理退出 ----
        _active_sessions.get(ticket_db_id, set()).discard(id(websocket))

        # 干预容器断开时，捕获本次干预会话的 conversation_id
        if is_intervene and ssh_conn:
            try:
                # 查找容器工作目录下最近的 Claude 对话文件
                find_cmd = (
                    f"docker exec {container_name} bash -c \""
                    f"ls -t $HOME/.claude/projects/*/*.jsonl 2>/dev/null | head -1 | "
                    f"xargs -I{{}} basename {{}} .jsonl\""
                )
                conv_res = await asyncio.wait_for(ssh_conn.run(find_cmd), timeout=5)
                conv_id = (conv_res.stdout or "").strip()
                if conv_id and len(conv_id) > 8:
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE task_tickets SET conversation_id=$1 WHERE id=$2",
                            conv_id, ticket_db_id
                        )
                    logger.info(f"已保存干预会话 ID: {conv_id} (ticket={ticket_db_id})")
            except Exception as conv_err:
                logger.debug(f"捕获干预会话 ID 失败: {conv_err}")

        if ssh_process:
            try:
                ssh_process.stdin.write_eof()
                ssh_process.close()
            except Exception:
                pass
        if ssh_conn:
            ssh_conn.close()
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(f"Terminal 已断开: ticket={ticket_db_id}")
