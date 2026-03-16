# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 用户评价 API
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §4.7 评价模块
关联需求: FR-008
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from auth import get_current_user, UserInfo
from database import get_pool

logger = logging.getLogger("ones-ai.eval")
router = APIRouter(prefix="/api/evaluations", tags=["用户评价"])


class EvalRequest(BaseModel):
    task_ticket_id: int
    passed: bool
    reason: str = ""


class EvalInfo(BaseModel):
    id: int
    task_ticket_id: int
    passed: bool
    reason: str
    evaluated_at: str


@router.post("")
async def submit_evaluation(req: EvalRequest, user: UserInfo = Depends(get_current_user)):
    """提交评价 [FR-008]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 检查工单是否存在且属于该用户
        ticket = await conn.fetchrow("""
            SELECT tt.id FROM task_tickets tt
            JOIN tasks t ON t.id = tt.task_id
            WHERE tt.id=$1 AND t.user_id=$2
        """, req.task_ticket_id, user.id)
        if not ticket:
            raise HTTPException(status_code=404, detail="工单不存在或无权操作")

        # 检查是否已评价
        existing = await conn.fetchrow(
            "SELECT id FROM task_evaluations WHERE task_ticket_id=$1",
            req.task_ticket_id,
        )
        if existing:
            raise HTTPException(status_code=400, detail="该工单已评价，不可重复提交")

        await conn.execute("""
            INSERT INTO task_evaluations (task_ticket_id, user_id, passed, reason)
            VALUES ($1, $2, $3, $4)
        """, req.task_ticket_id, user.id, req.passed, req.reason)

    return {"success": True}


@router.get("/task/{task_id}", response_model=list[EvalInfo])
async def get_task_evaluations(task_id: int, user: UserInfo = Depends(get_current_user)):
    """获取任务的所有评价"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT te.* FROM task_evaluations te
            JOIN task_tickets tt ON tt.id = te.task_ticket_id
            WHERE tt.task_id=$1
        """, task_id)
    return [
        EvalInfo(
            id=r["id"], task_ticket_id=r["task_ticket_id"],
            passed=r["passed"], reason=r["reason"] or "",
            evaluated_at=str(r["evaluated_at"]),
        )
        for r in rows
    ]
