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

# 任务队列 — 按用户隔离，每个用户一个队列 + worker
_user_queues: dict[int, asyncio.Queue] = {}       # user_id -> Queue
_user_workers: dict[int, asyncio.Task] = {}        # user_id -> worker Task
_queue_lock = asyncio.Lock()

# WebSocket 订阅者: {task_id: [websocket1, websocket2, ...]}
_log_subscribers: dict[int, list] = {}
_sub_lock = asyncio.Lock()


async def enqueue_task(task_id: int):
    """将任务入队到对应用户的队列"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT user_id FROM tasks WHERE id=$1", task_id)
    if not user_id:
        logger.error(f"任务 {task_id} 不存在，无法入队")
        return
    async with _queue_lock:
        if user_id not in _user_queues:
            _user_queues[user_id] = asyncio.Queue()
            _user_workers[user_id] = asyncio.create_task(_user_task_worker(user_id))
            logger.info(f"为用户 {user_id} 创建独立 Worker")
        await _user_queues[user_id].put(task_id)
    logger.info(f"任务 {task_id} 入队 (user={user_id}, 队列深度={_user_queues[user_id].qsize()})")


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
    return f"export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUNBUFFERED=1 && cd ~ && {cmd}"


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

            if task["status"] in ("completed", "failed", "cancelled"):
                logger.warning(f"任务 {task_id} 状态为 {task['status']}，跳过")
                return

            # 更新状态为 running（保留已有 started_at，防止重启覆盖）
            await conn.execute(
                "UPDATE tasks SET status='running', started_at=COALESCE(started_at, NOW()) WHERE id=$1",
                task_id,
            )

            # 获取待执行工单列表（仅 pending，打回重做场景下不重跑已完成工单）
            tickets = await conn.fetch(
                "SELECT * FROM task_tickets WHERE task_id=$1 AND status='pending' ORDER BY seq_order",
                task_id,
            )

            # 空任务保护（无工单记录则直接完成，防止空壳任务卡在队列）
            if not tickets:
                logger.warning(f"任务 {task_id} 无待执行工单，直接标记完成")
                await conn.execute(
                    "UPDATE tasks SET status='completed', completed_at=NOW() WHERE id=$1",
                    task_id)
                return

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

        # 逐工单串行执行 —— 每个工单独立一次 ones-AI 命令
        success_count = 0
        failed_count = 0
        agent_dir = task.get("agent_dir") or ""
        task_mode = task.get("task_mode") or "fix"

        for idx, ticket in enumerate(tickets):
            db_id = ticket["id"]
            ticket_id_str = ticket["ticket_id"]

            # 广播"开始执行第 N 个工单"
            start_msg = f"─────────────────  [{idx+1}/{len(tickets)}]  {ticket_id_str}  ─────────────────"
            await _save_log(task_id, start_msg, "stdout")
            await _broadcast_log(task_id, {
                "type": "log", "content": start_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # 构建单工单命令
            single_data = [{"ticket_id": ticket_id_str,
                            "note": ticket["note"] or "",
                            "code_directory": ticket["code_directory"] or ""}]
            extra_mounts_str = ticket.get("extra_mounts") or ""
            extra_mounts = [m.strip() for m in extra_mounts_str.split(',') if m.strip()] if extra_mounts_str else None
            command = _build_remote_command(single_data, agent_dir=agent_dir,
                                            extra_mounts=extra_mounts,
                                            task_mode=task_mode)
            await _save_log(task_id, f"执行命令: {command}", "system")

            # 标记工单为 running
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE task_tickets SET status='running', started_at=COALESCE(started_at, NOW()) WHERE id=$1",
                    db_id)

            # SSH 执行（2小时超时保护）
            ticket_success = False
            TICKET_TIMEOUT = 7200  # 2 小时
            try:
                process = await ssh_conn.create_process(command)
                process.stdin.write_eof()  # 关闭 stdin 防止 docker run -i 卡死

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
                                "type": "progress", "data": progress_data,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })
                        except json.JSONDecodeError:
                            pass
                        continue

                    # 解析 JSON 输出（工单结果）
                    if line.startswith("{") and '"ticket_id"' in line:
                        try:
                            result = json.loads(line)
                            ticket_status = result.get("status", "failed")
                            duration = result.get("duration", 0)
                            summary = result.get("summary", "")
                            title = result.get("title", "")
                            conclusion = result.get("conclusion", "")
                            analysis = result.get("analysis", "")
                            report_path = result.get("report_path", "")

                            # 用 DB id 精确更新（不用 ticket_id 防止打回重做多行命中）
                            async with pool.acquire() as conn:
                                await conn.execute("""
                                    UPDATE task_tickets SET
                                        status=$1, result_summary=$2, duration=$3,
                                        ticket_title=$4, result_conclusion=$5,
                                        report_path=$6, result_analysis=$7,
                                        completed_at=NOW()
                                    WHERE id=$8
                                """, "completed" if ticket_status == "success" else "failed",
                                    summary, duration, title, conclusion,
                                    report_path, analysis, db_id)

                            if ticket_status == "success":
                                success_count += 1
                                ticket_success = True
                            else:
                                failed_count += 1

                            # 日志
                            status_emoji = "\u2705" if ticket_status == "success" else "\u274c"
                            readable_log = f"{status_emoji} \u4efb\u52a1{ticket_status}: {ticket_id_str} (\u8017\u65f6 {duration:.1f}s)"
                            await _save_log(task_id, readable_log, "system")
                            await _broadcast_log(task_id, {
                                "type": "log", "content": readable_log,
                                "log_type": "system",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })
                        except json.JSONDecodeError:
                            await _save_log(task_id, line, "stdout")
                            await _broadcast_log(task_id, {
                                "type": "log", "content": line,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })
                        continue

                    # 普通日志
                    await _save_log(task_id, line, "stdout")
                    await _broadcast_log(task_id, {
                        "type": "log", "content": line,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                # 读取 stderr
                if process.stderr:
                    try:
                        stderr_content = await asyncio.wait_for(process.stderr.read(), timeout=10)
                        if stderr_content:
                            await _save_log(task_id, stderr_content.strip(), "stderr")
                    except asyncio.TimeoutError:
                        pass

                await asyncio.wait_for(process.wait(), timeout=TICKET_TIMEOUT)

            except asyncio.TimeoutError:
                error_msg = f"⏰ 工单 {ticket_id_str} 执行超时 ({TICKET_TIMEOUT//3600}h)，已终止"
                logger.error(error_msg)
                await _save_log(task_id, error_msg, "system")
                try:
                    process.kill()
                except Exception:
                    pass
                if not ticket_success:
                    failed_count += 1
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE task_tickets SET status='failed', error_message=$1, completed_at=NOW() WHERE id=$2",
                            error_msg, db_id)

            except Exception as e:
                error_msg = f"工单 {ticket_id_str} 执行异常: {e}"
                logger.error(error_msg)
                await _save_log(task_id, error_msg, "system")
                await _broadcast_log(task_id, {
                    "type": "log", "content": error_msg, "log_type": "system",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                # 标记该工单为 failed
                if not ticket_success:
                    failed_count += 1
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE task_tickets SET status='failed', error_message=$1, completed_at=NOW() WHERE id=$2",
                            error_msg, db_id)
                # SSH 断连检测 + 自动重连（防止后续工单连锁失败）
                err_lower = str(e).lower()
                if 'connection closed' in err_lower or 'connection lost' in err_lower or 'connection reset' in err_lower:
                    logger.warning(f"检测到 SSH 断连，尝试重连 {task['host']}...")
                    await _save_log(task_id, "⚠️ SSH 连接已断开，正在重连...", "system")
                    try:
                        ssh_conn = await get_ssh_connection(
                            task["host"], task["ssh_port"],
                            task["ssh_username"], ssh_password,
                        )
                        logger.info(f"SSH 重连成功: {task['host']}")
                        await _save_log(task_id, "✅ SSH 重连成功，继续执行后续工单", "system")
                    except Exception as re_err:
                        reconnect_msg = f"SSH 重连失败: {re_err}，剩余工单将全部标记失败"
                        logger.error(reconnect_msg)
                        await _save_log(task_id, reconnect_msg, "system")
                        # 重连失败，将剩余工单全部标 failed
                        async with pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE task_tickets SET status='failed', error_message=$1, completed_at=NOW() WHERE task_id=$2 AND status='pending'",
                                f"SSH 连接丢失且重连失败: {re_err}", task_id)
                            remaining = await conn.fetchval(
                                "SELECT count(*) FROM task_tickets WHERE task_id=$1 AND status='failed'", task_id)
                            failed_count = remaining
                        break
                # 继续执行下一个工单（不中断循环）
                continue

            # 执行完一个工单后立即下载报告
            await _download_single_report(ssh_conn, pool, db_id)

            # 增量更新 tasks 表（前端实时看到进度）
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE tasks SET success_count=$1, failed_count=$2 WHERE id=$3
                """, success_count, failed_count, task_id)
            # 广播进度
            await _broadcast_log(task_id, {
                "type": "progress",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        # ========== 所有工单执行完毕 ==========
        total_duration = time.time() - start_time

        # 最终状态 —— 基于数据库实际状态判定，而非仅看本次循环计数
        # 先清理遗留的 running 工单（ones-AI 未返回 JSON 结果行时会卡在 running）
        async with pool.acquire() as conn:
            orphaned = await conn.fetchval(
                "SELECT count(*) FROM task_tickets WHERE task_id=$1 AND status='running'",
                task_id)
            if orphaned > 0:
                logger.warning(f"任务 {task_id} 有 {orphaned} 个工单仍为 running，强制标记为 failed")
                await conn.execute("""
                    UPDATE task_tickets SET status='failed',
                        error_message=COALESCE(error_message, '工单未返回处理结果（ones-AI 可能内部异常）'),
                        completed_at=NOW()
                    WHERE task_id=$1 AND status='running'
                """, task_id)

        async with pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT
                    count(*) FILTER (WHERE status='completed') as done,
                    count(*) FILTER (WHERE status='failed') as fail,
                    count(*) FILTER (WHERE status='pending') as pend,
                    count(*) as total
                FROM task_tickets WHERE task_id=$1
            """, task_id)
        db_done = stats["done"]
        db_fail = stats["fail"]
        db_pend = stats["pend"]
        db_total = stats["total"]

        if db_pend > 0:
            # 还有未处理的工单，不应标记完成
            logger.warning(f"任务 {task_id} 仍有 {db_pend} 个 pending 工单，标记为 failed")
            final_status = "failed"
        elif db_done == 0:
            final_status = "failed"
        elif db_fail > 0:
            final_status = "completed"  # 有成功有失败，仍标记完成（部分成功）
        else:
            final_status = "completed"

        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE tasks SET
                    status=$1, success_count=$2, failed_count=$3,
                    total_duration=$4, completed_at=NOW()
                WHERE id=$5
            """, final_status, db_done, db_fail, total_duration, task_id)

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


async def _download_single_report(ssh_conn, pool, db_id: int):
    """下载单个工单的 1.md 报告文件"""
    try:
        async with pool.acquire() as conn:
            ticket = await conn.fetchrow(
                "SELECT ticket_id, report_path, code_directory FROM task_tickets "
                "WHERE id=$1 AND report_path != '' AND report_path IS NOT NULL",
                db_id,
            )
        if not ticket:
            return
        report_path = ticket["report_path"]
        code_dir = ticket["code_directory"] or ""

        # 报告路径可能是相对路径（如 workspace/doc/xxx/report/1.md）
        # 需要拼接 code_directory 构建绝对路径
        if not report_path.startswith("/"):
            if code_dir:
                abs_path = f"{code_dir.rstrip('/')}/{report_path}"
            else:
                # 没有 code_directory，尝试在 home 目录下查找
                abs_path = report_path
        else:
            abs_path = report_path

        async def _fetch(_path=abs_path):
            proc = await ssh_conn.create_process(f"cat {_path} 2>/dev/null")
            proc.stdin.write_eof()
            content = ""
            async for rline in proc.stdout:
                content += rline
            await proc.wait()
            return content

        report_content = await asyncio.wait_for(_fetch(), timeout=30)
        if report_content.strip():
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE task_tickets SET result_report=$1 WHERE id=$2",
                    report_content.strip(), db_id,
                )
            logger.info(f"已下载报告: {report_path} (ticket={ticket['ticket_id']})")
    except asyncio.TimeoutError:
        logger.warning(f"下载报告超时 (db_id={db_id})")
    except Exception as e:
        logger.warning(f"下载报告失败 (db_id={db_id}): {e}")


async def _user_task_worker(user_id: int):
    """单个用户的串行 Worker —— 不同用户各自并行"""
    logger.info(f"用户 {user_id} Worker 已启动")
    queue = _user_queues[user_id]
    while True:
        try:
            task_id = await asyncio.wait_for(queue.get(), timeout=300)
            logger.info(f"用户 {user_id} Worker 取出任务: {task_id}")
            await _execute_task(task_id)
        except asyncio.TimeoutError:
            # 5 分钟无新任务，清理 worker
            async with _queue_lock:
                if queue.empty():
                    del _user_queues[user_id]
                    del _user_workers[user_id]
                    logger.info(f"用户 {user_id} Worker 空闲超时，已清理")
                    return
                # 还有任务，继续
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"用户 {user_id} Worker 异常: {e}")


async def task_worker():
    """后台启动入口 —— 扫描 DB 中已有的 pending/running 任务并分发到 per-user 队列"""
    logger.info("任务分发器已启动（per-user 串行模式）")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            pending = await conn.fetch(
                "SELECT id, user_id FROM tasks WHERE status IN ('pending', 'running') ORDER BY id"
            )
        if pending:
            logger.info(f"发现 {len(pending)} 个待执行任务，分发到用户队列")
            for row in pending:
                await enqueue_task(row["id"])
    except Exception as e:
        logger.warning(f"扫描 pending 任务失败: {e}")

