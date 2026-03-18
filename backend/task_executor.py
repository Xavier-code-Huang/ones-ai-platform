# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 任务执行引擎
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §4.5 任务执行引擎
关联需求: FR-005, FR-006
"""

import asyncio
import json
import logging
import shlex
import time
from datetime import datetime, timezone

from crypto import decrypt_password
from database import get_pool
from ssh_pool import get_ssh_connection

logger = logging.getLogger("ones-ai.executor")

# 任务队列
_task_queue: asyncio.Queue = asyncio.Queue()

# WebSocket 订阅者: {task_id: [websocket1, websocket2, ...]}
_log_subscribers: dict[int, list] = {}
_sub_lock = asyncio.Lock()


async def enqueue_task(task_id: int):
    """将任务加入执行队列"""
    await _task_queue.put(task_id)
    logger.info(f"任务 {task_id} 已入队")


def subscribe_logs(task_id: int, ws):
    """订阅任务日志"""
    if task_id not in _log_subscribers:
        _log_subscribers[task_id] = []
    _log_subscribers[task_id].append(ws)


def unsubscribe_logs(task_id: int, ws):
    """取消订阅"""
    if task_id in _log_subscribers:
        try:
            _log_subscribers[task_id].remove(ws)
        except ValueError:
            pass


async def _broadcast_log(task_id: int, log_data: dict):
    """向所有订阅者广播日志"""
    subscribers = _log_subscribers.get(task_id, [])
    dead = []
    for ws in subscribers:
        try:
            await ws.send_json(log_data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            subscribers.remove(ws)
        except ValueError:
            pass


async def _save_log(task_id: int, content: str, log_type: str = "stdout",
                    ticket_id: int = None):
    """保存日志到数据库"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO task_logs (task_id, task_ticket_id, log_type, content)
            VALUES ($1, $2, $3, $4)
        """, task_id, ticket_id, log_type, content)


def _build_remote_command(tickets: list[dict], agent_dir: str = "",
                          extra_mounts: list[str] = None,
                          task_mode: str = "fix") -> str:
    """构建发送到远程服务器的 ones-AI 命令

    通过 ones-AI 脚本执行（走 Docker 容器），和命令行方式完全一致，
    避免宿主机 Python 版本、依赖等环境不一致问题。
    工作目录设为用户家目录（每个用户的 process/ 日志隔离）。
    """
    # ones-AI 已安装在 PATH 中（如 /usr/local/bin/ones-AI）
    cmd_parts = ["ones-AI", "--json-output", "--tickets"]

    for t in tickets:
        cmd_parts.append(t["ticket_id"])

    # 添加代码位置（必填）
    code_dirs = [t.get("code_directory", "") for t in tickets]
    if any(d for d in code_dirs):
        cmd_parts.append("--code-dirs")
        for d in code_dirs:
            cmd_parts.append(d if d else '""')

    # 添加补充说明（可选）
    notes = [t.get("note", "") for t in tickets]
    if any(n for n in notes):
        cmd_parts.append("--notes")
        for n in notes:
            cmd_parts.append(n if n else '""')

    # 添加 Agent Teams 目录（必填）
    if agent_dir:
        cmd_parts.extend(["--agent-dir", agent_dir])

    # 添加额外挂载路径（可选，逗号分隔）
    if extra_mounts:
        cmd_parts.extend(["--extra-mounts", ",".join(extra_mounts)])

    # 添加任务模式
    if task_mode:
        cmd_parts.extend(["--task-mode", task_mode])

    cmd = " ".join(shlex.quote(p) for p in cmd_parts)

    # cd 到用户家目录（确保 process/ 日志按用户隔离）
    # 设置 UTF-8 locale 避免 ones-AI 脚本中 printf '%q' 破坏中文
    return f"export LANG=C.UTF-8 LC_ALL=C.UTF-8 && cd ~ && {cmd}"


async def _execute_task(task_id: int):
    """执行单个任务"""
    pool = await get_pool()
    start_time = time.time()

    try:
        async with pool.acquire() as conn:
            # 获取任务信息
            task = await conn.fetchrow("""
                SELECT t.*, usc.ssh_username, usc.ssh_password_encrypted,
                       s.host, s.ssh_port
                FROM tasks t
                JOIN user_server_credentials usc ON usc.id = t.credential_id
                JOIN servers s ON s.id = t.server_id
                WHERE t.id = $1
            """, task_id)
            if not task:
                logger.error(f"任务 {task_id} 不存在")
                return

            if task["status"] != "pending":
                logger.warning(f"任务 {task_id} 状态为 {task['status']}，跳过")
                return

            # 更新状态为 running
            await conn.execute(
                "UPDATE tasks SET status='running', started_at=NOW() WHERE id=$1",
                task_id,
            )

            # 获取工单列表
            tickets = await conn.fetch(
                "SELECT * FROM task_tickets WHERE task_id=$1 ORDER BY seq_order",
                task_id,
            )

        # 广播状态变更
        await _broadcast_log(task_id, {
            "type": "status", "status": "running",
            "message": "任务开始执行",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await _save_log(task_id, "=== 任务开始执行 ===", "system")

        # SSH 连接
        ssh_password = decrypt_password(task["ssh_password_encrypted"])
        try:
            ssh_conn = await get_ssh_connection(
                task["host"], task["ssh_port"],
                task["ssh_username"], ssh_password,
            )
        except Exception as e:
            error_msg = f"SSH 连接失败: {e}"
            logger.error(error_msg)
            await _save_log(task_id, error_msg, "system")
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tasks SET status='failed', completed_at=NOW() WHERE id=$1",
                    task_id,
                )
            await _broadcast_log(task_id, {
                "type": "complete", "status": "failed",
                "message": error_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return

        # 构建远程命令
        ticket_data = [{"ticket_id": t["ticket_id"], "note": t["note"] or "",
                        "code_directory": t["code_directory"] or ""} for t in tickets]
        # 收集所有额外挂载路径（去重）
        all_extra_mounts = set()
        for t in tickets:
            mounts_str = t.get("extra_mounts") or ""
            if mounts_str:
                for m in mounts_str.split(','):
                    if m.strip():
                        all_extra_mounts.add(m.strip())
        agent_dir = task.get("agent_dir") or ""
        task_mode = task.get("task_mode") or "fix"
        command = _build_remote_command(ticket_data, agent_dir=agent_dir,
                                        extra_mounts=list(all_extra_mounts) if all_extra_mounts else None,
                                        task_mode=task_mode)
        await _save_log(task_id, f"执行命令: {command}", "system")

        # 执行远程命令
        success_count = 0
        failed_count = 0

        try:
            process = await ssh_conn.create_process(command)

            # 实时读取 stdout
            async for line in process.stdout:
                line = line.rstrip("\n")
                if not line:
                    continue

                # 解析进度标记
                if line.startswith("[PROGRESS]"):
                    try:
                        progress_data = json.loads(line[len("[PROGRESS] "):])
                        await _broadcast_log(task_id, {
                            "type": "progress",
                            "data": progress_data,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                    except json.JSONDecodeError:
                        pass
                    continue

                # 解析 JSON 输出（工单结果）
                if line.startswith("{") and '"ticket_id"' in line:
                    try:
                        result = json.loads(line)
                        ticket_id_str = result.get("ticket_id", "")
                        ticket_status = result.get("status", "failed")
                        duration = result.get("duration", 0)
                        summary = result.get("summary", "")
                        # 新增结构化字段（兼容旧版 Runner）
                        title = result.get("title", "")
                        conclusion = result.get("conclusion", "")
                        analysis = result.get("analysis", "")
                        report_path = result.get("report_path", "")

                        # [FR-018] analysis 独立存储到 result_analysis 列，不再混入 summary

                        # 更新工单状态（含新字段）
                        async with pool.acquire() as conn:
                            await conn.execute("""
                                UPDATE task_tickets SET
                                    status=$1, result_summary=$2, duration=$3,
                                    ticket_title=$4, result_conclusion=$5,
                                    report_path=$6, result_analysis=$7,
                                    completed_at=NOW()
                                WHERE task_id=$8 AND ticket_id=$9
                            """, "completed" if ticket_status == "success" else "failed",
                                summary, duration, title, conclusion,
                                report_path, analysis, task_id, ticket_id_str)

                        if ticket_status == "success":
                            success_count += 1
                        else:
                            failed_count += 1

                        # [FR-019] JSON 结果行已结构化存入 task_tickets，日志中写可读摘要
                        status_emoji = "\u2705" if ticket_status == "success" else "\u274c"
                        readable_log = f"{status_emoji} \u4efb\u52a1{ticket_status}: {ticket_id_str} (\u8017\u65f6 {duration:.1f}s)"
                        await _save_log(task_id, readable_log, "system")
                        await _broadcast_log(task_id, {
                            "type": "log", "content": readable_log,
                            "log_type": "system",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        # 广播进度更新（触发前端实时刷新工单结果区）
                        await _broadcast_log(task_id, {
                            "type": "progress",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                    except json.JSONDecodeError:
                        # JSON 解析失败，将原始行作为普通日志保存
                        await _save_log(task_id, line, "stdout")
                        await _broadcast_log(task_id, {
                            "type": "log", "content": line,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                    continue  # 跳过后面的通用日志保存

                # 保存和广播日志
                await _save_log(task_id, line, "stdout")
                await _broadcast_log(task_id, {
                    "type": "log", "content": line,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            # 读取 stderr
            if process.stderr:
                stderr = await process.stderr.read()
                if stderr:
                    await _save_log(task_id, stderr.strip(), "stderr")

            await process.wait()

            # 下载工单报告（1.md）
            await _download_reports(ssh_conn, pool, task_id)

        except Exception as e:
            error_msg = f"执行异常: {e}"
            logger.error(error_msg)
            await _save_log(task_id, error_msg, "system")
            failed_count = len(tickets) - success_count

        # 计算总耗时
        total_duration = time.time() - start_time

        # 更新任务状态
        final_status = "completed" if failed_count == 0 else ("failed" if success_count == 0 else "completed")
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE tasks SET
                    status=$1, success_count=$2, failed_count=$3,
                    total_duration=$4, completed_at=NOW()
                WHERE id=$5
            """, final_status, success_count, failed_count, total_duration, task_id)

        # 广播完成
        await _broadcast_log(task_id, {
            "type": "complete", "status": final_status,
            "success_count": success_count, "failed_count": failed_count,
            "total_duration": total_duration,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await _save_log(task_id, f"=== 任务完成: 成功 {success_count}, 失败 {failed_count}, 耗时 {total_duration:.1f}s ===", "system")

        # 触发企微通知
        try:
            from notifications import send_task_notification
            await send_task_notification(task_id)
        except Exception as e:
            logger.warning(f"通知发送失败: {e}")

    except Exception as e:
        logger.error(f"任务 {task_id} 执行异常: {e}")
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET status='failed', completed_at=NOW() WHERE id=$1",
                task_id,
            )


async def _download_reports(ssh_conn, pool, task_id: int):
    """通过 SSH 下载各工单的 1.md 报告文件，存入 result_report 列"""
    try:
        async with pool.acquire() as conn:
            tickets = await conn.fetch(
                "SELECT ticket_id, report_path FROM task_tickets "
                "WHERE task_id=$1 AND report_path != '' AND report_path IS NOT NULL",
                task_id,
            )
        for t in tickets:
            report_path = t["report_path"]
            try:
                proc = await ssh_conn.create_process(
                    f"cat {report_path} 2>/dev/null"
                )
                report_content = ""
                async for rline in proc.stdout:
                    report_content += rline
                await proc.wait()
                if report_content.strip():
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE task_tickets SET result_report=$1 "
                            "WHERE task_id=$2 AND ticket_id=$3",
                            report_content.strip(), task_id, t["ticket_id"],
                        )
                    logger.info(f"已下载报告: {report_path} (ticket={t['ticket_id']})")
            except Exception as e:
                logger.warning(f"下载报告失败 {report_path}: {e}")
    except Exception as e:
        logger.warning(f"报告下载阶段异常: {e}")


async def task_worker():
    """后台任务执行 Worker"""
    logger.info("任务执行 Worker 已启动")
    while True:
        try:
            task_id = await _task_queue.get()
            logger.info(f"Worker 取出任务: {task_id}")
            await _execute_task(task_id)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Worker 异常: {e}")
