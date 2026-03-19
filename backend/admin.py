# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 管理统计 API
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §4.9 管理统计模块
关联需求: FR-010~013, FR-014
"""

import logging
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from typing import Optional

from auth import require_admin, get_current_user, UserInfo
from crypto import encrypt_password, decrypt_password
from database import get_pool

logger = logging.getLogger("ones-ai.admin")
router = APIRouter(prefix="/api/admin", tags=["管理统计"])


# ---- 模型 ----

class OverviewStats(BaseModel):
    total_tasks: int
    total_tickets: int
    unique_users: int
    avg_duration: float
    success_rate: float
    estimated_hours_saved: float


class TrendPoint(BaseModel):
    date: str
    count: int
    tickets: int


class UserRank(BaseModel):
    user_id: int
    email: str
    display_name: str
    task_count: int
    ticket_count: int
    avg_duration: float


class ExternalConfigItem(BaseModel):
    config_key: str
    config_value: str
    is_encrypted: bool
    description: str


class ConfigUpdateRequest(BaseModel):
    configs: list[ExternalConfigItem]


# ---- 管理统计 API ----

@router.get("/overview", response_model=OverviewStats)
async def get_overview(
    days: int = Query(30, ge=1, le=365),
    admin: UserInfo = Depends(require_admin),
):
    """总览数据 [FR-010]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(DISTINCT t.id) as total_tasks,
                COALESCE(SUM(t.ticket_count), 0) as total_tickets,
                COUNT(DISTINCT t.user_id) as unique_users,
                COALESCE(AVG(t.total_duration), 0) as avg_duration,
                CASE WHEN SUM(t.ticket_count) > 0
                    THEN SUM(t.success_count)::FLOAT / SUM(t.ticket_count)
                    ELSE 0 END as success_rate,
                COALESCE(SUM(t.ticket_count), 0) * 2.0 as estimated_hours_saved
            FROM tasks t
            WHERE t.created_at >= NOW() - ($1 || ' days')::INTERVAL
              AND t.status IN ('completed', 'failed')
        """, str(days))

    return OverviewStats(
        total_tasks=row["total_tasks"],
        total_tickets=row["total_tickets"],
        unique_users=row["unique_users"],
        avg_duration=float(row["avg_duration"]),
        success_rate=float(row["success_rate"]),
        estimated_hours_saved=float(row["estimated_hours_saved"]),
    )


@router.get("/trends", response_model=list[TrendPoint])
async def get_trends(
    days: int = Query(30, ge=1, le=365),
    granularity: str = Query("day"),
    admin: UserInfo = Depends(require_admin),
):
    """趋势数据 [FR-011]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if granularity == "week":
            trunc = "week"
        elif granularity == "month":
            trunc = "month"
        else:
            trunc = "day"

        rows = await conn.fetch(f"""
            SELECT
                DATE_TRUNC('{trunc}', created_at)::DATE as dt,
                COUNT(*) as cnt,
                COALESCE(SUM(ticket_count), 0) as tickets
            FROM tasks
            WHERE created_at >= NOW() - ($1 || ' days')::INTERVAL
              AND status IN ('completed', 'failed')
            GROUP BY dt
            ORDER BY dt
        """, str(days))

    return [
        TrendPoint(date=str(r["dt"]), count=r["cnt"], tickets=r["tickets"])
        for r in rows
    ]


@router.get("/users", response_model=list[UserRank])
async def get_user_rankings(
    days: int = Query(30, ge=1, le=365),
    admin: UserInfo = Depends(require_admin),
):
    """用户排行 [FR-012]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                u.id as user_id, u.ones_email, u.display_name,
                COUNT(t.id) as task_count,
                COALESCE(SUM(t.ticket_count), 0) as ticket_count,
                COALESCE(AVG(t.total_duration), 0) as avg_duration
            FROM users u
            JOIN tasks t ON t.user_id = u.id
            WHERE t.created_at >= NOW() - ($1 || ' days')::INTERVAL
              AND t.status IN ('completed', 'failed')
            GROUP BY u.id, u.ones_email, u.display_name
            ORDER BY task_count DESC
        """, str(days))

    return [
        UserRank(
            user_id=r["user_id"], email=r["ones_email"],
            display_name=r["display_name"] or "",
            task_count=r["task_count"], ticket_count=r["ticket_count"],
            avg_duration=float(r["avg_duration"]),
        )
        for r in rows
    ]


@router.get("/users/{user_id}/detail")
async def get_user_detail(
    user_id: int,
    days: int = Query(30, ge=1, le=365),
    admin: UserInfo = Depends(require_admin),
):
    """用户使用明细 [FR-012]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        tasks = await conn.fetch("""
            SELECT t.id, t.ticket_count, t.success_count, t.failed_count,
                   t.total_duration, t.created_at, t.status, s.name as server_name
            FROM tasks t
            JOIN servers s ON s.id = t.server_id
            WHERE t.user_id=$1 AND t.created_at >= NOW() - ($2 || ' days')::INTERVAL
            ORDER BY t.created_at DESC
        """, user_id, str(days))

        result = []
        for t in tasks:
            tickets = await conn.fetch(
                "SELECT ticket_id, ticket_title, note, status, duration, result_summary FROM task_tickets WHERE task_id=$1 ORDER BY seq_order",
                t["id"],
            )
            result.append({
                "task_id": t["id"],
                "server_name": t["server_name"],
                "ticket_count": t["ticket_count"],
                "success_count": t["success_count"],
                "failed_count": t["failed_count"],
                "total_duration": t["total_duration"],
                "status": t["status"],
                "created_at": str(t["created_at"]),
                "tickets": [
                    {"ticket_id": tt["ticket_id"], "ticket_title": tt["ticket_title"] or "",
                     "note": tt["note"] or "", "result_summary": tt["result_summary"] or "",
                     "status": tt["status"], "duration": tt["duration"]}
                    for tt in tickets
                ],
            })

    return result


@router.get("/users/{user_id}/trends")
async def get_user_trends(
    user_id: int,
    days: int = Query(90, ge=1, le=365),
    granularity: str = Query("day"),
    admin: UserInfo = Depends(require_admin),
):
    """用户使用频次趋势 [FR-022]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        trunc = {"week": "week", "month": "month"}.get(granularity, "day")
        rows = await conn.fetch(f"""
            SELECT
                DATE_TRUNC('{trunc}', created_at)::DATE as dt,
                COUNT(*) as task_count,
                COALESCE(SUM(ticket_count), 0) as ticket_count
            FROM tasks
            WHERE user_id=$1
              AND created_at >= NOW() - ($2 || ' days')::INTERVAL
              AND status IN ('completed', 'failed')
            GROUP BY dt
            ORDER BY dt
        """, user_id, str(days))

    return [
        {"date": str(r["dt"]), "task_count": r["task_count"], "ticket_count": r["ticket_count"]}
        for r in rows
    ]


@router.get("/evaluations/stats")
async def get_eval_stats(
    days: int = Query(30, ge=1, le=365),
    admin: UserInfo = Depends(require_admin),
):
    """评价统计 [FR-013]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN passed THEN 1 ELSE 0 END) as passed_count,
                SUM(CASE WHEN NOT passed THEN 1 ELSE 0 END) as failed_count
            FROM task_evaluations
            WHERE evaluated_at >= NOW() - ($1 || ' days')::INTERVAL
        """, str(days))

        trend = await conn.fetch("""
            SELECT
                DATE_TRUNC('day', evaluated_at)::DATE as dt,
                COUNT(*) as total,
                SUM(CASE WHEN passed THEN 1 ELSE 0 END) as passed
            FROM task_evaluations
            WHERE evaluated_at >= NOW() - ($1 || ' days')::INTERVAL
            GROUP BY dt ORDER BY dt
        """, str(days))

    total = row["total"] or 0
    passed = row["passed_count"] or 0
    return {
        "total_evaluations": total,
        "passed_count": passed,
        "failed_count": row["failed_count"] or 0,
        "pass_rate": passed / total if total > 0 else 0,
        "trend": [
            {"date": str(t["dt"]), "total": t["total"], "passed": t["passed"]}
            for t in trend
        ],
    }


@router.get("/export")
async def export_data(
    days: int = Query(30, ge=1, le=365),
    admin: UserInfo = Depends(require_admin),
):
    """Excel 导出 [FR-012]"""
    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl 未安装")

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT u.ones_email, u.display_name,
                   t.id as task_id, t.ticket_count, t.success_count,
                   t.total_duration, t.status, t.created_at,
                   s.name as server_name
            FROM tasks t
            JOIN users u ON u.id = t.user_id
            JOIN servers s ON s.id = t.server_id
            WHERE t.created_at >= NOW() - ($1 || ' days')::INTERVAL
            ORDER BY t.created_at DESC
        """, str(days))

    wb = Workbook()
    ws = wb.active
    ws.title = "任务统计"
    ws.append(["用户", "姓名", "任务ID", "服务器", "工单数", "成功数", "耗时(秒)", "状态", "提交时间"])
    for r in rows:
        ws.append([
            r["ones_email"], r["display_name"], r["task_id"],
            r["server_name"], r["ticket_count"], r["success_count"],
            r["total_duration"], r["status"], str(r["created_at"]),
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ones_ai_export.xlsx"},
    )


# ---- 外部服务配置 API [FR-014] ----

@router.get("/configs", response_model=list[ExternalConfigItem])
async def get_configs(admin: UserInfo = Depends(require_admin)):
    """获取外部服务配置"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM external_configs ORDER BY config_key")

    result = []
    for r in rows:
        value = r["config_value"] or ""
        if r["is_encrypted"] and value:
            value = "********"  # 加密字段不返回明文
        result.append(ExternalConfigItem(
            config_key=r["config_key"],
            config_value=value,
            is_encrypted=r["is_encrypted"],
            description=r["description"] or "",
        ))
    return result


@router.post("/configs")
async def update_configs(req: ConfigUpdateRequest, admin: UserInfo = Depends(require_admin)):
    """更新外部服务配置 [FR-014]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        for cfg in req.configs:
            value = cfg.config_value
            if cfg.is_encrypted and value and value != "********":
                value = encrypt_password(value)

            await conn.execute("""
                INSERT INTO external_configs (config_key, config_value, is_encrypted, description, updated_by, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (config_key) DO UPDATE SET
                    config_value = CASE WHEN $2 = '********' THEN external_configs.config_value ELSE $2 END,
                    is_encrypted = $3,
                    description = $4,
                    updated_by = $5,
                    updated_at = NOW()
            """, cfg.config_key, value, cfg.is_encrypted, cfg.description, admin.id)

    return {"success": True}
