# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 任务管理 API
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §4.4 任务管理模块
关联需求: FR-004, FR-005, FR-007
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import get_current_user, UserInfo
from config import settings
from database import get_pool

logger = logging.getLogger("ones-ai.tasks")
router = APIRouter(prefix="/api/tasks", tags=["任务管理"])


# ---- Pydantic 模型 ----

class TicketInput(BaseModel):
    ticket_id: str
    note: str = ""
    code_directory: str = ""
    extra_mounts: list[str] = []


class CreateTaskRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    server_id: int
    credential_id: int
    agent_dir: str
    task_mode: str = "fix"
    engine_type: str = "glm"          # 新增: Provider 类型 [FR-ME-004]
    model_name: str = ""              # 新增: 模型名称 [FR-ME-004]
    api_key_id: Optional[int] = None  # 新增: 用户 API Key ID [FR-ME-004]
    tickets: list[TicketInput]


class TicketResult(BaseModel):
    id: int
    ticket_id: str
    note: str
    code_directory: str
    status: str
    result_summary: str
    result_report: str
    result_analysis: str = ""
    error_message: str
    ticket_title: str = ""
    result_conclusion: str = ""
    report_path: str = ""
    duration: float
    seq_order: int
    evaluation: Optional[dict] = None


class TaskInfo(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: int
    user_id: int
    user_email: str = ""
    server_id: int
    server_name: str = ""
    status: str
    ticket_count: int
    success_count: int
    failed_count: int
    total_duration: float
    task_mode: str = "fix"
    engine_type: str = "glm"          # 新增 [FR-ME-010]
    model_name: str = ""              # 新增 [FR-ME-010]
    submitted_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskDetail(TaskInfo):
    tickets: list[TicketResult] = []


# ---- 工具函数 ----

BLOCKED_PATHS = {'/', '/etc', '/sys', '/proc', '/dev', '/boot', '/root',
                 '/var', '/usr', '/sbin', '/bin', '/lib', '/lib64', '/run', '/tmp'}

def validate_path(path: str, field_name: str = "路径"):
    """校验路径安全性（防挂载系统敏感目录）"""
    p = path.rstrip('/')
    if not p:  # path was "/" after stripping
        raise HTTPException(400, f"不允许挂载根目录")
    if not p.startswith('/'):
        raise HTTPException(400, f"{field_name}必须为绝对路径")
    if ',' in p:
        raise HTTPException(400, f"{field_name}不允许包含逗号")
    if p in BLOCKED_PATHS:
        raise HTTPException(400, f"不允许挂载系统敏感路径: {p}")
    if len([x for x in p.split('/') if x]) < 2:
        raise HTTPException(400, f"{field_name}路径层级过浅，至少需要 2 级目录")


def normalize_ticket_id(tid: str) -> str:
    """标准化工单号: 纯数字补 ONES- 前缀"""
    tid = tid.strip()
    if re.match(r"^\d+$", tid):
        return f"ONES-{tid}"
    return tid


# ---- API 端点 ----

@router.post("", response_model=TaskInfo)
async def create_task(req: CreateTaskRequest, user: UserInfo = Depends(get_current_user)):
    """创建工单处理任务 [FR-004]"""
    import asyncio

    if not req.tickets:
        raise HTTPException(status_code=400, detail="至少需要一个工单号")

    # 校验路径安全性
    validate_path(req.agent_dir, "Agent 目录")
    if req.task_mode not in ("analysis", "fix", "auto"):
        raise HTTPException(400, "task_mode 必须为 analysis/fix/auto")

    # ---- 引擎校验 [FR-ME-004, FR-ME-005] ----
    VALID_ENGINE_TYPES = ("glm", "anthropic", "openai")
    if req.engine_type not in VALID_ENGINE_TYPES:
        raise HTTPException(400, f"engine_type 必须为 {'/'.join(VALID_ENGINE_TYPES)}")

    pool = await get_pool()

    if req.engine_type != "glm":
        # 多引擎功能开关 + Key 校验（合并为一次连接）
        async with pool.acquire() as conn:
            flag = await conn.fetchval(
                "SELECT config_value FROM external_configs WHERE config_key='multi_engine_enabled'")
            if flag != "true":
                raise HTTPException(403, "多引擎功能尚未开放，请联系管理员开启")

            # 非 GLM 引擎需要 api_key_id
            if not req.api_key_id:
                raise HTTPException(400, f"{req.engine_type} 引擎需要指定 api_key_id")
            # 验证 Key 归属当前用户 + Provider 匹配
            key_row = await conn.fetchrow(
                "SELECT id, provider FROM user_api_keys WHERE id=$1 AND user_id=$2",
                req.api_key_id, user.id,
            )
            if not key_row:
                raise HTTPException(400, "API Key 不存在或不属于当前用户")
            if key_row["provider"] != req.engine_type:
                raise HTTPException(400, f"API Key 的 Provider ({key_row['provider']}) 与引擎类型 ({req.engine_type}) 不匹配")
    else:
        # GLM 模式不需要 api_key_id
        if req.api_key_id:
            logger.warning(f"GLM 模式下忽略 api_key_id={req.api_key_id}")
            req.api_key_id = None

    # model_name 允许自定义（不在 provider_models 表中也放行）
    if req.model_name:
        async with pool.acquire() as conn:
            model_exists = await conn.fetchval(
                "SELECT 1 FROM provider_models WHERE provider=$1 AND model_id=$2 AND is_active=TRUE",
                req.engine_type, req.model_name,
            )
            if not model_exists:
                logger.warning(f"自定义模型名: engine={req.engine_type}, model={req.model_name} (不在 provider_models 表中)")

    for t in req.tickets:
        if t.code_directory:
            validate_path(t.code_directory, "代码位置")
        for mp in t.extra_mounts:
            if mp:
                validate_path(mp, "额外挂载路径")

    # ---- 步骤1: 查凭证（快速 DB 查询，单独获取连接）----
    async with pool.acquire() as conn:
        cred = await conn.fetchrow("""
            SELECT usc.*, s.name as server_name, s.host, s.ssh_port
            FROM user_server_credentials usc
            JOIN servers s ON s.id = usc.server_id
            WHERE usc.id=$1 AND usc.user_id=$2 AND usc.server_id=$3 AND usc.is_verified=TRUE
        """, req.credential_id, user.id, req.server_id)
        if not cred:
            raise HTTPException(status_code=400, detail="凭证不存在或未验证")

    # ---- 步骤2: SSH 路径预校验（不占 DB 连接）----
    try:
        from crypto import decrypt_password
        from ssh_pool import get_ssh_connection

        ssh_password = decrypt_password(cred["ssh_password_encrypted"])
        ssh_conn = await asyncio.wait_for(
            get_ssh_connection(cred["host"], cred["ssh_port"], cred["ssh_username"], ssh_password),
            timeout=15,
        )

        paths_to_check = [req.agent_dir]
        for t in req.tickets:
            if t.code_directory:
                paths_to_check.append(t.code_directory)
            for mp in t.extra_mounts:
                if mp and mp.strip():
                    paths_to_check.append(mp.strip())
        paths_to_check = list(dict.fromkeys(paths_to_check))

        check_parts = []
        for p in paths_to_check:
            safe_p = p.replace("'", "'\\''")
            check_parts.append(f"if [ -d '{safe_p}' ]; then echo '{safe_p}|EXISTS'; else echo '{safe_p}|MISSING'; fi")
        check_cmd = " && ".join(check_parts)

        proc = await ssh_conn.create_process(check_cmd)
        proc.stdin.write_eof()
        output = ""
        async for line in proc.stdout:
            output += line
        await asyncio.wait_for(proc.wait(), timeout=15)

        missing_paths = []
        for line in output.strip().split('\n'):
            if '|MISSING' in line:
                missing_paths.append(line.split('|')[0])

        if missing_paths:
            detail_parts = []
            for mp in missing_paths:
                if mp == req.agent_dir:
                    detail_parts.append(f"Agent 目录不存在: {mp}")
                else:
                    detail_parts.append(f"路径不存在: {mp}")
            raise HTTPException(
                status_code=400,
                detail="以下路径在服务器 {} 上不存在:\n{}".format(
                    cred['host'], "\n".join(detail_parts)
                )
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"SSH 路径预校验失败 (server={cred['host']}): {e}")

    # ---- 步骤3: 事务创建任务+工单（原子操作，防止空任务）----
    async with pool.acquire() as conn:
        # 防重复提交: 5分钟内同用户/同服务器/同目录不允许重复创建
        existing = await conn.fetchval("""
            SELECT id FROM tasks
            WHERE user_id=$1 AND server_id=$2 AND agent_dir=$3
              AND status IN ('pending', 'running')
              AND submitted_at > NOW() - INTERVAL '5 minutes'
            LIMIT 1
        """, user.id, req.server_id, req.agent_dir)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"您在 5 分钟内已提交过相同任务 (#{existing})，请勿重复提交。如需重新提交请稍候。"
            )

        async with conn.transaction():
            task_id = await conn.fetchval("""
                INSERT INTO tasks (user_id, server_id, credential_id, status, ticket_count, submitted_at, agent_dir, task_mode,
                                   engine_type, model_name, api_key_id)
                VALUES ($1, $2, $3, 'pending', $4, NOW(), $5, $6, $7, $8, $9)
                RETURNING id
            """, user.id, req.server_id, req.credential_id, len(req.tickets), req.agent_dir, req.task_mode,
               req.engine_type, req.model_name, req.api_key_id)

            # [FR-111] 14.1 工单级去重：同一任务内不允许重复工单号
            seen_ids = set()
            for i, t in enumerate(req.tickets):
                normalized_id = normalize_ticket_id(t.ticket_id)
                if normalized_id in seen_ids:
                    raise HTTPException(400, f"工单号 {normalized_id} 重复，请移除重复项")
                seen_ids.add(normalized_id)
                extra_mounts_str = ','.join(m for m in t.extra_mounts if m)
                await conn.execute("""
                    INSERT INTO task_tickets (task_id, ticket_id, note, code_directory, extra_mounts, status, seq_order)
                    VALUES ($1, $2, $3, $4, $5, 'pending', $6)
                """, task_id, normalized_id, t.note, t.code_directory, extra_mounts_str, i)

        row = await conn.fetchrow("""
            SELECT t.*, s.name as server_name
            FROM tasks t JOIN servers s ON s.id = t.server_id
            WHERE t.id=$1
        """, task_id)

    logger.info(f"任务已创建: id={task_id}, tickets={len(req.tickets)}")

    # 触发执行（异步）
    from task_executor import enqueue_task
    await enqueue_task(task_id)

    # 自动保存代码路径历史 [FR-107]
    try:
        async with pool.acquire() as conn:
            for t in req.tickets:
                if t.code_directory:
                    await conn.execute("""
                        INSERT INTO user_code_paths (user_id, server_id, path, use_count, last_used_at)
                        VALUES ($1, $2, $3, 1, NOW())
                        ON CONFLICT (user_id, server_id, path)
                        DO UPDATE SET use_count = user_code_paths.use_count + 1, last_used_at = NOW()
                    """, user.id, req.server_id, t.code_directory)
    except Exception as e:
        logger.warning(f"保存代码路径历史失败: {e}")

    return TaskInfo(
        id=row["id"], user_id=row["user_id"], user_email=user.ones_email,
        server_id=row["server_id"], server_name=row["server_name"],
        status=row["status"], ticket_count=row["ticket_count"],
        success_count=row["success_count"], failed_count=row["failed_count"],
        total_duration=row["total_duration"], submitted_at=str(row["submitted_at"]),
        engine_type=row["engine_type"] or "glm",
        model_name=row["model_name"] or "",
    )


@router.get("", response_model=list[TaskInfo])
async def list_tasks(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInfo = Depends(get_current_user),
):
    """获取当前用户的任务列表 [FR-007]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        where = "WHERE t.user_id=$1"
        params = [user.id]
        if status:
            where += " AND t.status=$2"
            params.append(status)

        offset = (page - 1) * page_size
        rows = await conn.fetch(f"""
            SELECT t.*, s.name as server_name, u.ones_email as user_email
            FROM tasks t
            JOIN servers s ON s.id = t.server_id
            JOIN users u ON u.id = t.user_id
            {where}
            ORDER BY t.created_at DESC
            LIMIT {page_size} OFFSET {offset}
        """, *params)

    return [
        TaskInfo(
            id=r["id"], user_id=r["user_id"], user_email=r["user_email"],
            server_id=r["server_id"], server_name=r["server_name"],
            status=r["status"], ticket_count=r["ticket_count"],
            success_count=r["success_count"], failed_count=r["failed_count"],
            total_duration=r["total_duration"], submitted_at=str(r["submitted_at"]),
            started_at=str(r["started_at"]) if r["started_at"] else None,
            completed_at=str(r["completed_at"]) if r["completed_at"] else None,
            engine_type=r["engine_type"] or "glm",
            model_name=r["model_name"] or "",
        )
        for r in rows
    ]


@router.get("/code-paths")
async def get_code_paths(
    server_id: int = Query(..., description="服务器 ID"),
    user: UserInfo = Depends(get_current_user),
):
    """获取用户在指定服务器上的历史代码路径 [FR-107]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, path, use_count, last_used_at
            FROM user_code_paths
            WHERE user_id=$1 AND server_id=$2
            ORDER BY use_count DESC, last_used_at DESC
            LIMIT 30
        """, user.id, server_id)

    return [
        {
            "id": r["id"],
            "path": r["path"],
            "use_count": r["use_count"],
            "last_used_at": str(r["last_used_at"]) if r["last_used_at"] else None,
        }
        for r in rows
    ]


@router.delete("/code-paths/{path_id}")
async def delete_code_path(
    path_id: int,
    user: UserInfo = Depends(get_current_user),
):
    """删除历史代码路径 [FR-107]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM user_code_paths WHERE id=$1 AND user_id=$2",
            path_id, user.id,
        )
    return {"message": "已删除"}


class ReworkRequest(BaseModel):
    feedback: str


@router.post("/{task_id}/tickets/{ticket_id}/rework")
async def rework_ticket(task_id: int, ticket_id: int, req: ReworkRequest,
                        user: UserInfo = Depends(get_current_user)):
    """打回重做：基于上次结果和用户反馈重新执行工单"""
    if not req.feedback.strip():
        raise HTTPException(400, "请输入追加要求")

    pool = await get_pool()
    async with pool.acquire() as conn:
        # 验证任务归属
        task = await conn.fetchrow("SELECT * FROM tasks WHERE id=$1 AND user_id=$2", task_id, user.id)
        if not task:
            raise HTTPException(404, "任务不存在")

        # 读取原 ticket
        orig = await conn.fetchrow("SELECT * FROM task_tickets WHERE id=$1 AND task_id=$2", ticket_id, task_id)
        if not orig:
            raise HTTPException(404, "工单不存在")

        # 构建打回重做的 note（注入上次结果+用户反馈）
        prev_summary = orig["result_summary"] or ""
        prev_report = orig["result_report"] or ""
        rework_note = (
            f"[打回重做] {req.feedback.strip()}\n\n"
            f"--- 上次处理摘要 ---\n{prev_summary}\n\n"
        )
        if prev_report:
            # 截取报告前 2000 字符，避免 note 过大
            rework_note += f"--- 上次报告(截取) ---\n{prev_report[:2000]}\n"

        # 获取当前最大 seq_order
        max_seq = await conn.fetchval(
            "SELECT COALESCE(MAX(seq_order), 0) FROM task_tickets WHERE task_id=$1", task_id
        )

        # 创建新 ticket
        new_id = await conn.fetchval("""
            INSERT INTO task_tickets (task_id, ticket_id, note, code_directory, extra_mounts, status, seq_order)
            VALUES ($1, $2, $3, $4, $5, 'pending', $6)
            RETURNING id
        """, task_id, orig["ticket_id"], rework_note, orig["code_directory"],
           orig.get("extra_mounts", ""), max_seq + 1)

        # 更新任务状态和计数
        await conn.execute("""
            UPDATE tasks SET status='pending',
                             ticket_count = ticket_count + 1
            WHERE id=$1
        """, task_id)

    logger.info(f"打回重做: task={task_id}, ticket={orig['ticket_id']}, new_id={new_id}")

    # 重新触发执行
    from task_executor import enqueue_task
    await enqueue_task(task_id)

    return {"message": "已提交重做", "new_ticket_id": new_id}


@router.get("/{task_id}", response_model=TaskDetail)
async def get_task(task_id: int, user: UserInfo = Depends(get_current_user)):
    """获取任务详情（含工单结果）[FR-007]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT t.*, s.name as server_name, u.ones_email as user_email
            FROM tasks t
            JOIN servers s ON s.id = t.server_id
            JOIN users u ON u.id = t.user_id
            WHERE t.id=$1 AND (t.user_id=$2 OR $3='admin')
        """, task_id, user.id, user.role)
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")

        tickets = await conn.fetch("""
            SELECT tt.*, te.passed as eval_passed, te.reason as eval_reason,
                   te.evaluated_at as eval_at
            FROM task_tickets tt
            LEFT JOIN task_evaluations te ON te.task_ticket_id = tt.id
            WHERE tt.task_id=$1
            ORDER BY tt.seq_order
        """, task_id)

    ticket_results = []
    for t in tickets:
        eval_data = None
        if t["eval_passed"] is not None:
            eval_data = {
                "passed": t["eval_passed"],
                "reason": t["eval_reason"] or "",
                "evaluated_at": str(t["eval_at"]) if t["eval_at"] else None,
            }
        ticket_results.append(TicketResult(
            id=t["id"], ticket_id=t["ticket_id"], note=t["note"] or "",
            code_directory=t["code_directory"] or "", status=t["status"],
            result_summary=t["result_summary"] or "", result_report=t["result_report"] or "",
            result_analysis=t["result_analysis"] if "result_analysis" in t.keys() else "",
            error_message=t["error_message"] or "",
            ticket_title=t["ticket_title"] if "ticket_title" in t.keys() else "",
            result_conclusion=t["result_conclusion"] if "result_conclusion" in t.keys() else "",
            report_path=t["report_path"] if "report_path" in t.keys() else "",
            duration=t["duration"],
            seq_order=t["seq_order"], evaluation=eval_data,
        ))

    return TaskDetail(
        id=row["id"], user_id=row["user_id"], user_email=row["user_email"],
        server_id=row["server_id"], server_name=row["server_name"],
        status=row["status"], ticket_count=row["ticket_count"],
        success_count=row["success_count"], failed_count=row["failed_count"],
        total_duration=row["total_duration"], submitted_at=str(row["submitted_at"]),
        started_at=str(row["started_at"]) if row["started_at"] else None,
        completed_at=str(row["completed_at"]) if row["completed_at"] else None,
        engine_type=row["engine_type"] or "glm",
        model_name=row["model_name"] or "",
        tickets=ticket_results,
    )


@router.delete("/{task_id}")
async def cancel_task(task_id: int, user: UserInfo = Depends(get_current_user)):
    """取消任务（仅 pending 状态）"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE tasks SET status='cancelled' WHERE id=$1 AND user_id=$2 AND status='pending'",
            task_id, user.id,
        )
    # result 格式为 "UPDATE N"，检查受影响行数
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="任务不存在或不可取消（仅 pending 状态可取消）")
    return {"success": True}


@router.get("/{task_id}/tickets/{ticket_id}/report")
async def get_ticket_report(
    task_id: int, ticket_id: str,
    user: UserInfo = Depends(get_current_user),
):
    """获取工单完整报告内容"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT tt.ticket_id, tt.result_report, tt.ticket_title,
                   tt.result_conclusion, tt.result_analysis, tt.report_path
            FROM task_tickets tt
            JOIN tasks t ON t.id = tt.task_id
            WHERE tt.task_id=$1 AND tt.ticket_id=$2
              AND (t.user_id=$3 OR $4='admin')
        """, task_id, ticket_id, user.id, user.role)
    if not row:
        raise HTTPException(status_code=404, detail="工单不存在")
    return {
        "ticket_id": row["ticket_id"],
        "title": row["ticket_title"] or "",
        "conclusion": row["result_conclusion"] or "",
        "analysis": row["result_analysis"] if "result_analysis" in row.keys() else "",
        "report": row["result_report"] or "",
        "report_path": row["report_path"] or "",
    }


@router.get("/{task_id}/logs")
async def get_task_logs(
    task_id: int,
    user: UserInfo = Depends(get_current_user),
):
    """获取任务的历史执行日志（支持已完成任务回看）"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 权限校验
        task = await conn.fetchrow(
            "SELECT user_id FROM tasks WHERE id=$1", task_id
        )
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task["user_id"] != user.id and user.role != "admin":
            raise HTTPException(status_code=403, detail="无权限")

        logs = await conn.fetch(
            "SELECT content, log_type, phase_name, timestamp FROM task_logs "
            "WHERE task_id=$1 ORDER BY id",
            task_id,
        )

    return {
        "task_id": task_id,
        "logs": [
            {
                "content": log["content"],
                "log_type": log["log_type"],
                "phase_name": log["phase_name"] if "phase_name" in log.keys() else "",
                "timestamp": str(log["timestamp"]),
            }
            for log in logs
        ],
    }


@router.get("/{task_id}/tickets/{ticket_db_id}/terminal-logs")
async def get_ticket_terminal_logs(
    task_id: int, ticket_db_id: int,
    user: UserInfo = Depends(get_current_user),
):
    """获取单个工单的终端日志（用于历史回放）[FR-112]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        task = await conn.fetchrow(
            "SELECT user_id FROM tasks WHERE id=$1", task_id
        )
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task["user_id"] != user.id and user.role != "admin":
            raise HTTPException(status_code=403, detail="无权限")

        logs = await conn.fetch(
            "SELECT content, log_type, phase_name, timestamp FROM task_logs "
            "WHERE task_id=$1 AND (task_ticket_id=$2 OR task_ticket_id IS NULL) "
            "ORDER BY id",
            task_id, ticket_db_id,
        )

    return {
        "task_id": task_id,
        "ticket_db_id": ticket_db_id,
        "logs": [
            {
                "content": log["content"],
                "log_type": log["log_type"],
                "timestamp": str(log["timestamp"]),
            }
            for log in logs
        ],
    }


# ============================================================
#  新增 API — 阶段查询 / 工单编辑 / 代码路径历史
#  关联: FR-101, FR-107, FR-108
# ============================================================

@router.get("/{task_id}/tickets/{ticket_db_id}/phases")
async def get_ticket_phases(
    task_id: int, ticket_db_id: int,
    user: UserInfo = Depends(get_current_user),
):
    """获取工单的处理阶段列表 [FR-101]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 权限校验
        task = await conn.fetchrow(
            "SELECT user_id FROM tasks WHERE id=$1", task_id
        )
        if not task:
            raise HTTPException(404, "任务不存在")
        if task["user_id"] != user.id and user.role != "admin":
            raise HTTPException(403, "无权限")

        ticket = await conn.fetchrow(
            "SELECT id FROM task_tickets WHERE id=$1 AND task_id=$2",
            ticket_db_id, task_id
        )
        if not ticket:
            raise HTTPException(404, "工单不存在")

    from phases import get_phases
    phases = await get_phases(ticket_db_id)
    return {"ticket_db_id": ticket_db_id, "phases": phases}


class EditTicketRequest(BaseModel):
    note: Optional[str] = None
    code_directory: Optional[str] = None


@router.put("/{task_id}/tickets/{ticket_db_id}")
async def edit_pending_ticket(
    task_id: int, ticket_db_id: int, req: EditTicketRequest,
    user: UserInfo = Depends(get_current_user),
):
    """编辑排队中的工单（仅 pending 状态）[FR-108]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        task = await conn.fetchrow(
            "SELECT user_id FROM tasks WHERE id=$1", task_id
        )
        if not task:
            raise HTTPException(404, "任务不存在")
        if task["user_id"] != user.id and user.role != "admin":
            raise HTTPException(403, "无权限")

        ticket = await conn.fetchrow(
            "SELECT id, status FROM task_tickets WHERE id=$1 AND task_id=$2",
            ticket_db_id, task_id
        )
        if not ticket:
            raise HTTPException(404, "工单不存在")
        if ticket["status"] != "pending":
            raise HTTPException(400, f"只能编辑排队中的工单，当前状态: {ticket['status']}")

        # 校验路径
        if req.code_directory:
            validate_path(req.code_directory, "代码位置")

        # 动态构建 UPDATE
        updates = []
        params = []
        param_idx = 1
        if req.note is not None:
            updates.append(f"note=${param_idx}")
            params.append(req.note)
            param_idx += 1
        if req.code_directory is not None:
            updates.append(f"code_directory=${param_idx}")
            params.append(req.code_directory)
            param_idx += 1

        if not updates:
            raise HTTPException(400, "没有需要更新的字段")

        params.append(ticket_db_id)
        sql = f"UPDATE task_tickets SET {', '.join(updates)} WHERE id=${param_idx}"
        await conn.execute(sql, *params)

    logger.info(f"编辑工单: task={task_id}, ticket={ticket_db_id}")
    return {"message": "工单已更新", "ticket_db_id": ticket_db_id}



# ============================================================
#  容器管理 API
# ============================================================

from crypto import decrypt_password
from ssh_pool import get_ssh_connection

@router.get("/{task_id}/tickets/{ticket_db_id}/container")
async def get_ticket_container(
    task_id: int, ticket_db_id: int,
    user: UserInfo = Depends(get_current_user),
):
    """获取工单关联的容器信息及运行状态"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow("""
            SELECT tt.container_name, t.user_id,
                   usc.ssh_username, usc.ssh_password_encrypted,
                   s.host, s.ssh_port
            FROM task_tickets tt
            JOIN tasks t ON t.id = tt.task_id
            JOIN user_server_credentials usc ON usc.id = t.credential_id
            JOIN servers s ON s.id = t.server_id
            WHERE tt.id = $1 AND tt.task_id = $2
        """, ticket_db_id, task_id)

    if not record:
        raise HTTPException(404, "工单不存在")
    if record["user_id"] != user.id and user.role != "admin":
        raise HTTPException(403, "无权限查询")

    container_name = record["container_name"]
    if not container_name:
        return {"container_name": "", "status": "not_bound"}
    # 安全校验（re 已在模块顶部导入）
    if not re.fullmatch(r'ones-ai-[\w-]+', container_name):
        raise HTTPException(400, "容器名格式异常")

    # 通过 SSH 查询状态
    try:
        ssh_password = decrypt_password(record["ssh_password_encrypted"])
        ssh_conn = await get_ssh_connection(
            record["host"], record["ssh_port"],
            record["ssh_username"], ssh_password
        )
        # 查询状态和创建时间
        res = await ssh_conn.run(
            f"docker inspect -f '{{{{.State.Status}}}},{{{{.Created}}}}' {container_name}"
        )
        if res.exit_status == 0:
            status, created = res.stdout.strip().split(',', 1)
            return {
                "container_name": container_name,
                "status": status,  # running, exited, etc.
                "created_at": created,
            }
        else:
            return {"container_name": container_name, "status": "not_found"}
    except Exception as e:
        logger.error(f"获取容器状态失败: {e}")
        return {"container_name": container_name, "status": "error", "message": str(e)}


@router.post("/{task_id}/tickets/{ticket_db_id}/container/start")
async def start_ticket_container(
    task_id: int, ticket_db_id: int,
    user: UserInfo = Depends(get_current_user),
):
    """一键唤醒(启动)已停止的容器，或为未绑定容器的工单创建新容器"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow("""
            SELECT tt.container_name, tt.ticket_id, tt.code_directory, tt.note,
                   tt.conversation_id,
                   t.user_id, t.agent_dir, t.task_mode, t.status AS task_status,
                   usc.ssh_username, usc.ssh_password_encrypted,
                   s.host, s.ssh_port
            FROM task_tickets tt
            JOIN tasks t ON t.id = tt.task_id
            JOIN user_server_credentials usc ON usc.id = t.credential_id
            JOIN servers s ON s.id = t.server_id
            WHERE tt.id = $1 AND tt.task_id = $2
        """, ticket_db_id, task_id)

    if not record:
        raise HTTPException(404, "工单不存在")
    if record["user_id"] != user.id and user.role != "admin":
        raise HTTPException(403, "无权限启动")
    if record["task_status"] == "running":
        raise HTTPException(400, "任务正在自动化执行，禁止挂起或创建干预容器")

    container_name = record["container_name"] or ""

    try:
        ssh_password = decrypt_password(record["ssh_password_encrypted"])
        ssh_conn = await get_ssh_connection(
            record["host"], record["ssh_port"],
            record["ssh_username"], ssh_password
        )

        # 情况1: 有容器名 → 检查状态
        is_intervene_container = "intervene" in container_name
        if container_name and re.fullmatch(r'ones-ai-[\w-]+', container_name):
            check = await ssh_conn.run(
                f"docker inspect -f '{{{{.State.Status}}}}' {container_name} 2>/dev/null"
            )
            if check.exit_status == 0:
                status = check.stdout.strip()
                if status == "running":
                    # 容器正在运行（任务执行中 或 干预容器未退出）
                    return {"message": "容器已在运行中", "container_name": container_name}
                if is_intervene_container:
                    # 干预容器已停止 → docker start（主进程是 bash，安全）
                    logger.info(f"正在唤醒干预容器: {container_name}")
                    res = await ssh_conn.run(f"docker start {container_name}")
                    if res.exit_status != 0:
                        raise HTTPException(500, f"容器启动失败: {res.stderr}")
                    return {"message": "容器已成功唤醒", "container_name": container_name}
                # 任务容器已停止 → 不能 docker start（会重跑任务），创建干预容器
                logger.info(f"任务容器 {container_name} 已停止，创建干预容器")
            else:
                logger.info(f"容器 {container_name} 已不存在，将创建新容器")

        # 情况2: 容器不存在或未绑定 → 创建新的交互式容器
        ssh_user = record["ssh_username"]

        # 获取用户 HOME 目录
        home_res = await ssh_conn.run(f"echo ~{ssh_user}")
        user_home = home_res.stdout.strip() or f"/home/{ssh_user}"
        # 解析可能的符号链接
        realpath_res = await ssh_conn.run(f"readlink -f {user_home} 2>/dev/null || echo {user_home}")
        user_home = realpath_res.stdout.strip() or user_home

        code_dir = record["code_directory"] or user_home
        agent_dir = record["agent_dir"] or ""

        # 获取 API Key（模仿 ones-AI 脚本）
        key_script = (
            "python3 -c \""
            "import json,urllib.request;"
            f"r=urllib.request.urlopen('http://172.60.1.35:9601/api/allocate?username={ssh_user}',timeout=10);"
            "d=json.loads(r.read());"
            "print(d.get('api_key','') if d.get('success') else '')"
            "\" 2>/dev/null"
        )
        key_res = await ssh_conn.run(key_script)
        api_key = key_res.stdout.strip()
        if not api_key:
            raise HTTPException(500, "无法获取 API Key，请检查密钥网关")

        # 生成容器名
        import time as _time
        new_container_name = f"ones-ai-{ssh_user}-intervene-{int(_time.time()) % 100000}"

        # 构建 docker run 命令（模仿 ones-AI 脚本但不执行 runner）
        # 使用 -dit 后台启动，用户通过 WebTerminal 连入
        uid_res = await ssh_conn.run(f"id -u {ssh_user} 2>/dev/null")
        gid_res = await ssh_conn.run(f"id -g {ssh_user} 2>/dev/null")
        uid = uid_res.stdout.strip() or "1000"
        gid = gid_res.stdout.strip() or "1000"

        # 创建临时 passwd 和 group 文件（消除 groups 警告）
        passwd_line = f"{ssh_user}:x:{uid}:{gid}:{ssh_user}:{user_home}:/bin/bash"
        group_line = f"{ssh_user}:x:{gid}:"
        await ssh_conn.run(f"echo '{passwd_line}' > /tmp/{new_container_name}-passwd")
        await ssh_conn.run(f"echo '{group_line}' > /tmp/{new_container_name}-group")

        # 构建挂载参数
        mounts = [
            f"-v {user_home}:{user_home}",
            f"-v /opt/lango:/opt/lango:ro",
            f"-v /tmp/{new_container_name}-passwd:/etc/passwd:ro",
            f"-v /tmp/{new_container_name}-group:/etc/group:ro",
        ]
        if agent_dir and not agent_dir.startswith(user_home):
            mounts.append(f"-v {agent_dir}:{agent_dir}:ro")

        mount_str = " ".join(mounts)

        docker_cmd = (
            f"docker run -dit "
            f"--name {new_container_name} "
            f"--user {uid}:{gid} "
            f"--network host "
            f"--entrypoint /bin/bash "
            f"-e HOME={user_home} "
            f"-e USER={ssh_user} "
            f"-e TERM=xterm-256color "
            f"-e ANTHROPIC_AUTH_TOKEN={api_key} "
            f'-e ANTHROPIC_BASE_URL={settings.AI_BASE_URL} '
            f"-e ANTHROPIC_DEFAULT_HAIKU_MODEL={settings.CLAUDE_HAIKU_MODEL} "
            f"-e ANTHROPIC_DEFAULT_SONNET_MODEL={settings.CLAUDE_SONNET_MODEL} "
            f"-e ANTHROPIC_DEFAULT_OPUS_MODEL={settings.CLAUDE_OPUS_MODEL} "
            f"-e API_TIMEOUT_MS=3000000 "
            f"-e CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 "
            f"-e GIT_DISCOVERY_ACROSS_FILESYSTEM=1 "
            f"{mount_str} "
            f"-w {code_dir} "
            f"lango-claude:latest"
        )

        logger.info(f"正在创建干预容器: {new_container_name}")
        res = await ssh_conn.run(docker_cmd)
        if res.exit_status != 0:
            raise HTTPException(500, f"容器创建失败: {res.stderr}")

        # 在容器内设置 git safe.directory
        await ssh_conn.run(
            f"docker exec {new_container_name} git config --global --add safe.directory '*' 2>/dev/null"
        )

        # 写入自动启动脚本：
        # - 有 conversation_id → resume 上次干预会话
        # - 无 conversation_id → 新建会话，告知 ones-AI 报告位置
        ticket_id_str = record["ticket_id"] or ""
        conversation_id = record.get("conversation_id") or ""

        if conversation_id:
            # 后续干预：resume 上次的干预会话
            lines = [
                "#!/bin/bash",
                "if [ ! -f /tmp/.claude_resumed ]; then",
                "  touch /tmp/.claude_resumed",
                "  echo ''",
                f"  echo '🔧 干预模式 - 工单 {ticket_id_str}'",
                f"  echo '🔑 恢复上次干预会话: {conversation_id}'",
                "  echo ''",
                f"  claude --resume --conversation-id {conversation_id} 2>/dev/null || claude",
                "fi",
            ]
        else:
            # 首次干预：直接启动交互式 claude，提示报告位置
            lines = [
                "#!/bin/bash",
                "if [ ! -f /tmp/.claude_resumed ]; then",
                "  touch /tmp/.claude_resumed",
                "  echo ''",
                f"  echo '🔧 干预模式 - 工单 {ticket_id_str} (首次)'",
                f"  REPORT=$(find {code_dir} -path '*/doc/{ticket_id_str}/report/1.md' 2>/dev/null | head -1)",
                '  if [ -n \\"$REPORT\\" ]; then',
                '    echo \\"📄 ones-AI 报告: $REPORT\\"',
                "    echo '💡 进入 Claude 后，请告诉它阅读上述报告路径'",
                "  else",
                "    echo '⚠️ 未找到 ones-AI 报告'",
                "  fi",
                "  echo ''",
                "  claude",
                "fi",
            ]

        # 用 base64 编码写入脚本（避免 SSH + docker exec 多层转义问题）
        import base64 as _b64
        script_content = "\n".join(lines)
        b64 = _b64.b64encode(script_content.encode()).decode()
        await ssh_conn.run(
            f"docker exec {new_container_name} bash -c \"echo '{b64}' | base64 -d > /tmp/auto_resume.sh && chmod +x /tmp/auto_resume.sh\""
        )

        # 更新数据库中的容器名
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE task_tickets SET container_name=$1 WHERE id=$2",
                new_container_name, ticket_db_id
            )

        logger.info(f"干预容器已创建: {new_container_name}, 已绑定到工单 {ticket_db_id}")
        return {
            "message": "干预容器已创建，请打开终端操作",
            "container_name": new_container_name,
            "created": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动/创建容器失败: {e}")
        raise HTTPException(500, f"服务器连接异常: {e}")

