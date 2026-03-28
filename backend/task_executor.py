# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 任务执行引擎
@Version: 2.0.0
@Date: 2026-03-26

关联设计文档: §4.5 任务执行引擎, §3.2 阶段推进
关联需求: FR-005, FR-006, FR-103, FR-111
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
from phases import (
    init_phases, advance_phase, complete_remaining_phases,
    format_phase_for_ws,
)

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
                    ticket_id: int = None, phase_name: str = ""):
    """保存日志到数据库"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO task_logs (task_id, task_ticket_id, log_type, content, phase_name)
            VALUES ($1, $2, $3, $4, $5)
        """, task_id, ticket_id, log_type, content, phase_name)


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

            if task["status"] in ("cancelled",):
                logger.warning(f"任务 {task_id} 状态为 {task['status']}，跳过")
                return
            # 允许 completed/failed 任务重新执行（打回重做场景：rework API 已插入新pending工单）
            if task["status"] in ("completed", "failed"):
                has_pending = await conn.fetchval(
                    "SELECT count(*) FROM task_tickets WHERE task_id=$1 AND status='pending'",
                    task_id)
                if not has_pending:
                    logger.info(f"任务 {task_id} 状态为 {task['status']} 且无pending工单，跳过")
                    return
                logger.info(f"任务 {task_id} 状态为 {task['status']} 但有 {has_pending} 个pending工单（打回重做），继续执行")

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

            # 初始化阶段记录并推进前序阶段
            await init_phases(db_id)

            # 阶段 1: validating
            await advance_phase(db_id, "validating", "active", "正在校验工单信息...")
            await _broadcast_log(task_id, format_phase_for_ws(
                "validating", "active", "正在校验工单信息...", ticket_id_str, db_id))
            await advance_phase(db_id, "validating", "completed", "工单信息校验通过")
            await _broadcast_log(task_id, format_phase_for_ws(
                "validating", "completed", "工单信息校验通过", ticket_id_str, db_id))

            # 阶段 2: checking_path
            await advance_phase(db_id, "checking_path", "active", "正在检查代码路径...")
            await _broadcast_log(task_id, format_phase_for_ws(
                "checking_path", "active", "正在检查代码路径...", ticket_id_str, db_id))
            await advance_phase(db_id, "checking_path", "completed",
                                f"代码路径: {ticket['code_directory'] or '默认'}")
            await _broadcast_log(task_id, format_phase_for_ws(
                "checking_path", "completed",
                f"代码路径: {ticket['code_directory'] or '默认'}", ticket_id_str, db_id))

            # 阶段 3: checking_agent_dir
            if agent_dir:
                await advance_phase(db_id, "checking_agent_dir", "active", "正在检查 Agent-Teams 目录...")
                await _broadcast_log(task_id, format_phase_for_ws(
                    "checking_agent_dir", "active", "正在检查 Agent-Teams 目录...", ticket_id_str, db_id))
                await advance_phase(db_id, "checking_agent_dir", "completed", f"Agent 目录: {agent_dir}")
                await _broadcast_log(task_id, format_phase_for_ws(
                    "checking_agent_dir", "completed", f"Agent 目录: {agent_dir}", ticket_id_str, db_id))
            else:
                await advance_phase(db_id, "checking_agent_dir", "skipped", "未配置 Agent-Teams 目录")
                await _broadcast_log(task_id, format_phase_for_ws(
                    "checking_agent_dir", "skipped", "未配置 Agent-Teams 目录", ticket_id_str, db_id))

            # 阶段 4: container_starting
            await advance_phase(db_id, "container_starting", "active", "正在启动容器环境...")
            await _broadcast_log(task_id, format_phase_for_ws(
                "container_starting", "active", "正在启动容器环境...", ticket_id_str, db_id))

            # 追踪当前阶段（用于 stdout 日志关联）
            current_phase = "container_starting"
            container_name = ""  # 追踪 AI 容器名称，用于报告读取

            # SSH 执行（2小时总超时 + 20分钟心跳超时保护）[FR-111]
            ticket_success = False
            TICKET_TIMEOUT = 7200  # 2 小时总超时
            HEARTBEAT_TIMEOUT = 1200  # 20 分钟无输出视为卡死
            try:
                process = await ssh_conn.create_process(command)
                process.stdin.write_eof()  # 关闭 stdin 防止 docker run -i 卡死

                # 带心跳超时的实时 stdout 读取 [14.2]
                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=HEARTBEAT_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        error_msg = f"⏰ 工单 {ticket_id_str} 超过 {HEARTBEAT_TIMEOUT//60} 分钟无输出，判定为卡死"
                        logger.warning(error_msg)
                        await _save_log(task_id, error_msg, "system")
                        await _broadcast_log(task_id, {
                            "type": "log", "content": error_msg, "log_type": "system",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        try:
                            process.kill()
                        except Exception:
                            pass
                        break
                    if not line:  # EOF
                        break
                    line = line.rstrip("\n")
                    if not line:
                        continue

                    # 捕获容器名（ones-AI 输出: "正在进入容器: ones-ai-xxx-123 ..."）
                    if not container_name and ("正在进入容器" in line or "Entering container" in line):
                        import re as _re
                        _m = _re.search(r'(ones-ai-[\w-]+)', line)
                        if _m:
                            container_name = _m.group(1)
                            logger.info(f"捕获容器名: {container_name}")
                            # 立即将容器名保存到数据库，供终端连接使用
                            async with pool.acquire() as conn:
                                await conn.execute(
                                    "UPDATE task_tickets SET container_name=$1 WHERE id=$2",
                                    container_name, db_id
                                )

                    # 解析 [PHASE] 标记行（由 runner 输出）
                    if line.startswith("[PHASE]"):
                        parts = line[len("[PHASE]"):].strip().split(" ", 1)
                        phase_name_raw = parts[0] if parts else ""
                        phase_msg = parts[1] if len(parts) > 1 else ""

                        if phase_name_raw.endswith("_done"):
                            # 阶段完成标记
                            real_phase = phase_name_raw[:-5]
                            await advance_phase(db_id, real_phase, "completed", phase_msg)
                            await _broadcast_log(task_id, format_phase_for_ws(
                                real_phase, "completed", phase_msg, ticket_id_str, db_id))
                        else:
                            # 容器启动完成后的首个 agent 阶段
                            if current_phase == "container_starting":
                                await advance_phase(db_id, "container_starting", "completed", "容器环境已启动")
                                await _broadcast_log(task_id, format_phase_for_ws(
                                    "container_starting", "completed", "容器环境已启动", ticket_id_str, db_id))
                            # 推进新阶段
                            await advance_phase(db_id, phase_name_raw, "active", phase_msg)
                            await _broadcast_log(task_id, format_phase_for_ws(
                                phase_name_raw, "active", phase_msg, ticket_id_str, db_id))
                            current_phase = phase_name_raw

                        await _save_log(task_id, line, "phase", db_id, phase_name_raw)
                        continue

                    # 解析进度标记（旧版兼容）
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

                            # 【关键】JSON结果已解析，立即下载报告（容器此时仍在运行）
                            # ones-AI 退出后会清理容器，workspace/ 目录随之消失
                            if report_path and container_name:
                                try:
                                    await _download_single_report(
                                        ssh_conn, pool, db_id,
                                        container_name=container_name)
                                except Exception as dl_err:
                                    logger.warning(f"提前下载报告失败: {dl_err}")

                            # 日志
                            status_emoji = "\u2705" if ticket_status == "success" else "\u274c"
                            readable_log = f"{status_emoji} \u4efb\u52a1{ticket_status}: {ticket_id_str} (\u8017\u65f6 {duration:.1f}s)"
                            await _save_log(task_id, readable_log, "system")
                            await _broadcast_log(task_id, {
                                "type": "log", "content": readable_log,
                                "log_type": "system",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })

                            # ---- 阶段完结：推进所有剩余阶段 ----
                            if ticket_status == "success":
                                # 成功：将当前 active 阶段和所有 pending 阶段标记为 completed
                                await complete_remaining_phases(db_id, "completed", f"工单 {ticket_id_str} 处理完成")
                                await _broadcast_log(task_id, format_phase_for_ws(
                                    current_phase, "completed", f"工单处理完成 ({duration:.1f}s)", ticket_id_str, db_id))
                            else:
                                # 失败：当前阶段标记为 failed，其余标记为 skipped
                                await advance_phase(db_id, current_phase, "failed", f"工单处理失败: {summary}")
                                await _broadcast_log(task_id, format_phase_for_ws(
                                    current_phase, "failed", f"工单处理失败", ticket_id_str, db_id))
                                await complete_remaining_phases(db_id, "skipped", "因工单失败跳过")

                        except json.JSONDecodeError:
                            await _save_log(task_id, line, "stdout")
                            await _broadcast_log(task_id, {
                                "type": "log", "content": line,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })
                        continue

                    # 普通日志
                    await _save_log(task_id, line, "stdout", db_id, current_phase)
                    await _broadcast_log(task_id, {
                        "type": "log", "content": line,
                        "phase_name": current_phase,
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

            # 清理工单剩余阶段
            if ticket_success:
                await complete_remaining_phases(db_id, "completed", "任务完成")
            else:
                await complete_remaining_phases(db_id, "skipped", "前序阶段失败，已跳过")

            # 执行完一个工单后立即下载报告（传入容器名用于 docker exec 读取）
            await _download_single_report(ssh_conn, pool, db_id, container_name=container_name)

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

        # 只在任务仍为 running 时更新终态（防止覆盖 rework API 已设回的 pending 状态）
        async with pool.acquire() as conn:
            updated = await conn.execute("""
                UPDATE tasks SET
                    status=$1, success_count=$2, failed_count=$3,
                    total_duration=$4, completed_at=NOW()
                WHERE id=$5 AND status='running'
            """, final_status, db_done, db_fail, total_duration, task_id)
            if 'UPDATE 0' in str(updated):
                logger.warning(f"任务 {task_id} 状态已非running（可能被rework修改），跳过终态更新")

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
        import traceback
        tb = traceback.format_exc()
        logger.error(f"任务 {task_id} 执行异常: {type(e).__name__}: {e}\n{tb}")
        try:
            error_detail = f"任务执行异常: {type(e).__name__}: {e}"
            await _save_log(task_id, error_detail, "system")
            await _broadcast_log(task_id, {
                "type": "complete", "status": "failed",
                "message": error_detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET status='failed', completed_at=NOW() WHERE id=$1",
                task_id,
            )
            # 同步清理：将所有 pending/running 工单标为 failed（防止工单永远卡住）
            await conn.execute("""
                UPDATE task_tickets SET status='failed',
                    error_message=COALESCE(error_message, $1),
                    completed_at=NOW()
                WHERE task_id=$2 AND status IN ('pending', 'running')
            """, f"任务执行异常: {type(e).__name__}: {e}", task_id)


async def _download_single_report(ssh_conn, pool, db_id: int, container_name: str = ""):
    """下载单个工单的 1.md 报告文件
    
    多级读取策略:
    1. 通过 docker exec 在容器内读取（workspace/ 只在容器内存在）
    2. 通过 docker cp 从容器拷贝到宿主机后读取
    3. 直接从宿主机路径读取（兼容 volume mount 场景）
    """
    try:
        async with pool.acquire() as conn:
            ticket = await conn.fetchrow(
                "SELECT tt.ticket_id, tt.report_path, tt.code_directory, t.agent_dir "
                "FROM task_tickets tt JOIN tasks t ON t.id = tt.task_id "
                "WHERE tt.id=$1 AND tt.report_path != '' AND tt.report_path IS NOT NULL",
                db_id,
            )
        if not ticket:
            return
        report_path = ticket["report_path"].strip()
        agent_dir = (ticket["agent_dir"] or "").strip()
        code_dir = (ticket["code_directory"] or "").strip()
        ticket_id_str = ticket["ticket_id"]

        # 清洗 report_path（AI 输出可能含多余文本，如 "报告位置\nworkspace/..."）
        if "workspace/" in report_path:
            report_path = report_path[report_path.index("workspace/"):]
        report_path = report_path.replace("\n", "").replace("`", "").strip()

        # 构建宿主机绝对路径（fallback 用）
        if not report_path.startswith("/"):
            if agent_dir:
                abs_path = f"{agent_dir.rstrip('/')}/{report_path}"
            elif code_dir:
                abs_path = f"{code_dir.rstrip('/')}/{report_path}"
            else:
                abs_path = report_path
        else:
            abs_path = report_path

        async def _ssh_cat(path: str) -> str:
            """通过 SSH 在宿主机上 cat 文件"""
            proc = await ssh_conn.create_process(f"cat '{path}' 2>/dev/null")
            proc.stdin.write_eof()
            content = ""
            async for rline in proc.stdout:
                content += rline
            await proc.wait()
            return content

        async def _docker_exec_cat(container: str, path: str) -> str:
            """通过 docker exec 在容器内 cat 文件"""
            proc = await ssh_conn.create_process(
                f"docker exec {container} cat '{path}' 2>/dev/null")
            proc.stdin.write_eof()
            content = ""
            async for rline in proc.stdout:
                content += rline
            await proc.wait()
            return content

        async def _docker_cp_then_cat(container: str, src: str) -> str:
            """通过 docker cp 先拷贝到宿主机 /tmp 再 cat"""
            tmp_dest = f"/tmp/_onesai_report_{db_id}.md"
            proc = await ssh_conn.create_process(
                f"docker cp '{container}:{src}' '{tmp_dest}' 2>/dev/null && cat '{tmp_dest}' && rm -f '{tmp_dest}'")
            proc.stdin.write_eof()
            content = ""
            async for rline in proc.stdout:
                content += rline
            await proc.wait()
            return content

        report_content = ""

        # 策略 1: docker exec 在容器内读取（workspace/ 通常只在容器内）
        if container_name and report_path:
            try:
                # 尝试容器内的几种可能路径
                for try_path in [
                    f"/home/user/{report_path}",       # 容器内工作目录
                    f"/root/{report_path}",             # 容器 root 目录
                    f"/{report_path}",                  # 绝对路径
                    report_path,                        # 相对路径
                ]:
                    content = await asyncio.wait_for(
                        _docker_exec_cat(container_name, try_path), timeout=10)
                    if content.strip():
                        report_content = content
                        logger.info(f"[策略1-docker exec] 成功读取: {container_name}:{try_path}")
                        break
            except Exception as e:
                logger.debug(f"[策略1-docker exec] 失败: {e}")

        # 策略 2: docker cp 拷贝出来
        if not report_content.strip() and container_name and report_path:
            try:
                for try_path in [
                    f"/home/user/{report_path}",
                    f"/root/{report_path}",
                    report_path,
                ]:
                    content = await asyncio.wait_for(
                        _docker_cp_then_cat(container_name, try_path), timeout=15)
                    if content.strip():
                        report_content = content
                        logger.info(f"[策略2-docker cp] 成功读取: {container_name}:{try_path}")
                        break
            except Exception as e:
                logger.debug(f"[策略2-docker cp] 失败: {e}")

        # 策略 3: 宿主机直接 cat（多路径尝试）
        # workspace/ 实际在 code_directory 或 HOME 下（不在 agent_dir 下，因为 agent_dir 是 ro 挂载）
        if not report_content.strip():
            host_try_paths = []
            if code_dir:
                host_try_paths.append(f"{code_dir.rstrip('/')}/{report_path}")
            host_try_paths.append(abs_path)  # agent_dir 拼接的路径（原逻辑）
            if agent_dir:
                # 尝试用户 HOME（agent_dir 的父目录通常是 HOME）
                user_home = agent_dir.rstrip('/').rsplit('/', 1)[0]
                host_try_paths.append(f"{user_home}/{report_path}")
            for try_host_path in host_try_paths:
                try:
                    content = await asyncio.wait_for(
                        _ssh_cat(try_host_path), timeout=10)
                    if content.strip():
                        report_content = content
                        logger.info(f"[策略3-宿主机cat] 成功读取: {try_host_path}")
                        break
                except Exception as e:
                    logger.debug(f"[策略3-宿主机cat] {try_host_path} 失败: {e}")

        # 策略 4: 搜索宿主机上可能的位置
        if not report_content.strip() and (agent_dir or code_dir):
            search_dirs = []
            if code_dir:
                search_dirs.append(code_dir)
            if agent_dir:
                search_dirs.append(agent_dir)
            for sdir in search_dirs:
                try:
                    find_proc = await ssh_conn.create_process(
                        f"find '{sdir}' -maxdepth 5 -path '*{ticket_id_str}*/report/1.md' -type f 2>/dev/null | head -1")
                    find_proc.stdin.write_eof()
                    found = ""
                    async for rline in find_proc.stdout:
                        found += rline
                    await find_proc.wait()
                    found = found.strip()
                    if found:
                        report_content = await asyncio.wait_for(
                            _ssh_cat(found), timeout=15)
                        if report_content.strip():
                            logger.info(f"[策略4-find搜索] 成功读取: {found}")
                            break
                except Exception as e:
                    logger.debug(f"[策略4-find搜索] {sdir} 失败: {e}")

        # 写入数据库
        if report_content.strip():
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE task_tickets SET result_report=$1 WHERE id=$2",
                    report_content.strip(), db_id,
                )
            logger.info(f"已下载报告: {ticket_id_str} (db_id={db_id})")
        else:
            logger.warning(
                f"报告获取失败: {ticket_id_str} (db_id={db_id}), "
                f"report_path={report_path}, container={container_name}, abs_path={abs_path}")

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

