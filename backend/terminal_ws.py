# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — Web Terminal (SSH PTY 双向代理)
@Version: 1.0.0
@Date: 2026-03-26

功能: 通过 WebSocket 将浏览器 xterm.js 终端连接到目标服务器的 Shell。
用户可在终端中执行 `docker ps` 和 `docker exec -it <container> bash` 进入容器交互。

架构: xterm.js ←→ WebSocket (binary) ←→ FastAPI ←→ asyncssh PTY ←→ 目标服务器 Shell
"""

import asyncio
import logging

import asyncssh
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt

from config import settings
from crypto import decrypt_password
from database import get_pool

logger = logging.getLogger("ones-ai.terminal")
router = APIRouter(tags=["Terminal"])

# 活跃终端会话跟踪 (task_id → set of sessions)
_active_sessions: dict[int, set] = {}


@router.websocket("/ws/tasks/{task_id}/terminal")
async def terminal_ws(websocket: WebSocket, task_id: int, token: str = Query("")):
    """
    Web Terminal WebSocket 端点

    连接: ws://host/ws/tasks/{task_id}/terminal?token=<JWT>
    协议:
      - 客户端 → 服务端: binary 帧 = 键盘输入 | JSON 文本帧 = 控制命令
      - 服务端 → 客户端: binary 帧 = 终端输出
      - 控制命令: {"type":"resize","cols":80,"rows":24}
    """
    # ---- 1. JWT 验证 ----
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = int(payload.get("sub", 0))
        role = payload.get("role", "user")
    except (JWTError, Exception):
        await websocket.close(code=4001, reason="Token 无效")
        return

    # ---- 2. 任务权限 + 凭证查询 ----
    pool = await get_pool()
    async with pool.acquire() as conn:
        task = await conn.fetchrow("""
            SELECT t.user_id, t.server_id, t.credential_id, t.status,
                   usc.ssh_username, usc.ssh_password_encrypted,
                   s.host, s.ssh_port
            FROM tasks t
            JOIN user_server_credentials usc ON usc.id = t.credential_id
            JOIN servers s ON s.id = t.server_id
            WHERE t.id = $1
        """, task_id)

    if not task:
        await websocket.close(code=4004, reason="任务不存在")
        return
    if task["user_id"] != user_id and role != "admin":
        await websocket.close(code=4003, reason="无权限")
        return

    # ---- 3. 建立独立 SSH 连接 (带 PTY) ----
    ssh_conn = None
    ssh_process = None

    try:
        ssh_password = decrypt_password(task["ssh_password_encrypted"])
        ssh_conn = await asyncio.wait_for(
            asyncssh.connect(
                task["host"],
                port=task["ssh_port"],
                username=task["ssh_username"],
                password=ssh_password,
                known_hosts=None,
            ),
            timeout=15,
        )

        # 查找正在运行的 ones-AI 容器并进入
        # 容器命名规则: ones-ai-{username}-{pid}
        ssh_username = task["ssh_username"]
        # 构建自动进入容器的命令: 先找容器，找到则 exec 进入，否则回退到普通 shell
        enter_container_cmd = (
            f'CONTAINER=$(docker ps --format "{{{{.Names}}}}" '
            f'| grep -E "^ones-ai-{ssh_username}-" | head -1); '
            f'if [ -n "$CONTAINER" ]; then '
            f'  echo "[ones-AI] 正在进入容器: $CONTAINER ..."; '
            f'  exec docker exec -i "$CONTAINER" /bin/bash; '
            f'else '
            f'  echo "[ones-AI] 未找到运行中的容器 (ones-ai-{ssh_username}-*)"; '
            f'  echo "[ones-AI] 已进入服务器 Shell，可手动 docker exec 进入"; '
            f'  exec bash; '
            f'fi'
        )

        ssh_process = await ssh_conn.create_process(
            enter_container_cmd,
            term_type="xterm-256color",
            term_size=(80, 24),
            encoding=None,  # 使用 bytes 模式
        )

    except asyncio.TimeoutError:
        await websocket.close(code=4008, reason="SSH 连接超时")
        return
    except asyncssh.PermissionDenied:
        await websocket.close(code=4009, reason="SSH 认证失败")
        return
    except Exception as e:
        logger.error(f"Terminal SSH 连接失败: {e}")
        await websocket.close(code=4010, reason=f"SSH 连接失败: {str(e)[:100]}")
        return

    # ---- 4. WebSocket 握手 ----
    await websocket.accept()
    logger.info(f"Terminal 已连接: task={task_id}, user={user_id}, server={task['host']}")

    # 跟踪会话
    session_id = id(websocket)
    _active_sessions.setdefault(task_id, set()).add(session_id)

    # ---- 5. 双向代理 ----
    async def _ssh_to_ws():
        """SSH stdout → WebSocket (binary)"""
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
                    # 键盘输入 (binary)
                    ssh_process.stdin.write(msg["bytes"])
                elif "text" in msg and msg["text"]:
                    # 控制命令 (JSON text)
                    import json
                    try:
                        cmd = json.loads(msg["text"])
                        if cmd.get("type") == "resize":
                            cols = int(cmd.get("cols", 80))
                            rows = int(cmd.get("rows", 24))
                            ssh_process.change_terminal_size(cols, rows)
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass  # 忽略无法解析的文本帧
        except (WebSocketDisconnect, Exception):
            pass

    # 并发运行两个方向的代理
    try:
        done, pending = await asyncio.wait(
            [asyncio.create_task(_ssh_to_ws()), asyncio.create_task(_ws_to_ssh())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        # 取消未完成的任务
        for t in pending:
            t.cancel()
    except Exception as e:
        logger.warning(f"Terminal 会话异常: {e}")
    finally:
        # ---- 6. 清理 ----
        _active_sessions.get(task_id, set()).discard(session_id)
        if ssh_process:
            try:
                ssh_process.stdin.write_eof()
            except Exception:
                pass
            try:
                ssh_process.close()
            except Exception:
                pass
        if ssh_conn:
            try:
                ssh_conn.close()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(f"Terminal 已断开: task={task_id}, user={user_id}")
