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
from database import get_pool

logger = logging.getLogger("ones-ai.tasks")
router = APIRouter(prefix="/api/tasks", tags=["任务管理"])


# ---- Pydantic 模型 ----

class TicketInput(BaseModel):
    ticket_id: str
    note: str = ""
    code_directory: str = ""


class CreateTaskRequest(BaseModel):
    server_id: int
    credential_id: int
    tickets: list[TicketInput]


class TicketResult(BaseModel):
    id: int
    ticket_id: str
    note: str
    code_directory: str
    status: str
    result_summary: str
    result_report: str
    error_message: str
    duration: float
    seq_order: int
    evaluation: Optional[dict] = None


class TaskInfo(BaseModel):
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
    submitted_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskDetail(TaskInfo):
    tickets: list[TicketResult] = []


# ---- 工具函数 ----

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
    if not req.tickets:
        raise HTTPException(status_code=400, detail="至少需要一个工单号")

    pool = await get_pool()
    async with pool.acquire() as conn:
        # 验证服务器和凭证
        cred = await conn.fetchrow("""
            SELECT usc.*, s.name as server_name, s.host, s.ssh_port
            FROM user_server_credentials usc
            JOIN servers s ON s.id = usc.server_id
            WHERE usc.id=$1 AND usc.user_id=$2 AND usc.server_id=$3 AND usc.is_verified=TRUE
        """, req.credential_id, user.id, req.server_id)
        if not cred:
            raise HTTPException(status_code=400, detail="凭证不存在或未验证")

        # 创建任务
        task_id = await conn.fetchval("""
            INSERT INTO tasks (user_id, server_id, credential_id, status, ticket_count, submitted_at)
            VALUES ($1, $2, $3, 'pending', $4, NOW())
            RETURNING id
        """, user.id, req.server_id, req.credential_id, len(req.tickets))

        # 创建工单明细
        for i, t in enumerate(req.tickets):
            normalized_id = normalize_ticket_id(t.ticket_id)
            await conn.execute("""
                INSERT INTO task_tickets (task_id, ticket_id, note, code_directory, status, seq_order)
                VALUES ($1, $2, $3, $4, 'pending', $5)
            """, task_id, normalized_id, t.note, t.code_directory, i)

        row = await conn.fetchrow("""
            SELECT t.*, s.name as server_name
            FROM tasks t JOIN servers s ON s.id = t.server_id
            WHERE t.id=$1
        """, task_id)

    logger.info(f"任务已创建: id={task_id}, tickets={len(req.tickets)}")

    # 触发执行（异步）
    from task_executor import enqueue_task
    await enqueue_task(task_id)

    return TaskInfo(
        id=row["id"], user_id=row["user_id"], user_email=user.ones_email,
        server_id=row["server_id"], server_name=row["server_name"],
        status=row["status"], ticket_count=row["ticket_count"],
        success_count=row["success_count"], failed_count=row["failed_count"],
        total_duration=row["total_duration"], submitted_at=str(row["submitted_at"]),
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
        )
        for r in rows
    ]


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
            error_message=t["error_message"] or "", duration=t["duration"],
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
    return {"success": True}
