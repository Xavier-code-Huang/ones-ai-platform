# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 外部团队日志上报 API
@Version: 1.0.0
@Date: 2026-03-24

外部团队可以通过 API Key 上报日志数据，管理员可以查看统计。
"""

import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel

from auth import require_admin, UserInfo
from database import get_pool

logger = logging.getLogger("ones-ai.external")
router = APIRouter(tags=["外部团队"])


# ---- Pydantic 模型 ----

class LogEntry(BaseModel):
    member_name: str
    ticket_id: str = ""
    action_type: str = "process"
    status: str = "completed"
    duration: float = 0
    summary: str = ""


class ReportRequest(BaseModel):
    logs: list[LogEntry]


class TeamCreate(BaseModel):
    team_name: str
    description: str = ""
    contact_email: str = ""


class TeamInfo(BaseModel):
    id: int
    team_name: str
    description: str
    contact_email: str
    api_key: str = ""
    is_active: bool
    created_at: str
    total_logs: int = 0
    total_members: int = 0


class TeamStats(BaseModel):
    team_id: int
    team_name: str
    total_logs: int
    total_members: int
    success_count: int
    failed_count: int
    avg_duration: float
    recent_logs: int  # 近7天


class MemberStats(BaseModel):
    member_name: str
    log_count: int
    success_count: int
    avg_duration: float


class TrendPoint(BaseModel):
    date: str
    count: int


# ---- 外部上报 API (API Key 认证) ----

@router.post("/api/external/report")
async def report_logs(req: ReportRequest, x_api_key: str = Header(..., alias="X-API-Key")):
    """外部团队上报日志"""
    if not req.logs:
        raise HTTPException(400, "日志列表不能为空")
    if len(req.logs) > 100:
        raise HTTPException(400, "单次上报不超过 100 条")

    pool = await get_pool()
    async with pool.acquire() as conn:
        team = await conn.fetchrow(
            "SELECT id, team_name FROM external_teams WHERE api_key=$1 AND is_active=TRUE",
            x_api_key
        )
        if not team:
            raise HTTPException(403, "无效的 API Key 或团队已禁用")

        team_id = team["id"]
        inserted = 0
        for log in req.logs:
            await conn.execute("""
                INSERT INTO external_logs (team_id, member_name, ticket_id, action_type, status, duration, summary)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, team_id, log.member_name, log.ticket_id, log.action_type, log.status, log.duration, log.summary)

            # 自动注册成员
            await conn.execute("""
                INSERT INTO external_team_members (team_id, member_name)
                VALUES ($1, $2)
                ON CONFLICT (team_id, member_name) DO NOTHING
            """, team_id, log.member_name)
            inserted += 1

    logger.info(f"外部日志上报成功: team={team['team_name']}, count={inserted}")
    return {"success": True, "inserted": inserted, "team": team["team_name"]}


# ---- 管理员 API ----

@router.get("/api/admin/external-teams", response_model=list[TeamInfo])
async def list_teams(admin: UserInfo = Depends(require_admin)):
    """获取所有外部团队列表"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT et.*,
                   COALESCE(lc.total_logs, 0) as total_logs,
                   COALESCE(mc.total_members, 0) as total_members
            FROM external_teams et
            LEFT JOIN (
                SELECT team_id, COUNT(*) as total_logs
                FROM external_logs GROUP BY team_id
            ) lc ON lc.team_id = et.id
            LEFT JOIN (
                SELECT team_id, COUNT(*) as total_members
                FROM external_team_members GROUP BY team_id
            ) mc ON mc.team_id = et.id
            ORDER BY et.created_at DESC
        """)
    return [TeamInfo(
        id=r["id"], team_name=r["team_name"], description=r["description"] or "",
        contact_email=r["contact_email"] or "", api_key=r["api_key"],
        is_active=r["is_active"], created_at=str(r["created_at"]),
        total_logs=r["total_logs"], total_members=r["total_members"],
    ) for r in rows]


@router.post("/api/admin/external-teams", response_model=TeamInfo)
async def create_team(req: TeamCreate, admin: UserInfo = Depends(require_admin)):
    """注册新外部团队"""
    if not req.team_name.strip():
        raise HTTPException(400, "团队名称不能为空")

    api_key = secrets.token_hex(32)
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow("""
                INSERT INTO external_teams (team_name, api_key, description, contact_email)
                VALUES ($1, $2, $3, $4)
                RETURNING *
            """, req.team_name.strip(), api_key, req.description, req.contact_email)
        except Exception as e:
            if "unique" in str(e).lower():
                raise HTTPException(400, f"团队名 '{req.team_name}' 已存在")
            raise

    logger.info(f"创建外部团队: {req.team_name}")
    return TeamInfo(
        id=row["id"], team_name=row["team_name"], description=row["description"] or "",
        contact_email=row["contact_email"] or "", api_key=row["api_key"],
        is_active=row["is_active"], created_at=str(row["created_at"]),
    )


@router.delete("/api/admin/external-teams/{team_id}")
async def delete_team(team_id: int, admin: UserInfo = Depends(require_admin)):
    """删除外部团队"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        r = await conn.execute("DELETE FROM external_teams WHERE id=$1", team_id)
        if r == "DELETE 0":
            raise HTTPException(404, "团队不存在")
    return {"success": True}


@router.get("/api/admin/external-teams/{team_id}/stats")
async def get_team_stats(
    team_id: int,
    days: int = Query(30, ge=1, le=365),
    admin: UserInfo = Depends(require_admin),
):
    """获取单个团队的详细统计"""
    pool = await get_pool()
    since = datetime.utcnow() - timedelta(days=days)
    async with pool.acquire() as conn:
        team = await conn.fetchrow("SELECT * FROM external_teams WHERE id=$1", team_id)
        if not team:
            raise HTTPException(404, "团队不存在")

        # 总览统计
        overview = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status='completed') as success,
                COUNT(*) FILTER (WHERE status='failed') as failed,
                COALESCE(AVG(duration), 0) as avg_duration
            FROM external_logs
            WHERE team_id=$1 AND reported_at >= $2
        """, team_id, since)

        # 成员统计
        members = await conn.fetch("""
            SELECT member_name,
                   COUNT(*) as log_count,
                   COUNT(*) FILTER (WHERE status='completed') as success_count,
                   COALESCE(AVG(duration), 0) as avg_duration
            FROM external_logs
            WHERE team_id=$1 AND reported_at >= $2
            GROUP BY member_name
            ORDER BY log_count DESC
        """, team_id, since)

        # 趋势数据（按天）
        trends = await conn.fetch("""
            SELECT DATE(reported_at) as date, COUNT(*) as count
            FROM external_logs
            WHERE team_id=$1 AND reported_at >= $2
            GROUP BY DATE(reported_at)
            ORDER BY date
        """, team_id, since)

    return {
        "team": {
            "id": team["id"],
            "team_name": team["team_name"],
            "description": team["description"] or "",
            "contact_email": team["contact_email"] or "",
            "created_at": str(team["created_at"]),
        },
        "overview": {
            "total": overview["total"],
            "success": overview["success"],
            "failed": overview["failed"],
            "avg_duration": round(float(overview["avg_duration"]), 1),
            "success_rate": round(overview["success"] / max(overview["total"], 1) * 100, 1),
        },
        "members": [
            {
                "member_name": m["member_name"],
                "log_count": m["log_count"],
                "success_count": m["success_count"],
                "avg_duration": round(float(m["avg_duration"]), 1),
            }
            for m in members
        ],
        "trends": [
            {"date": str(t["date"]), "count": t["count"]}
            for t in trends
        ],
    }


@router.get("/api/admin/external-overview")
async def get_external_overview(
    days: int = Query(30, ge=1, le=365),
    admin: UserInfo = Depends(require_admin),
):
    """所有外部团队汇总统计"""
    pool = await get_pool()
    since = datetime.utcnow() - timedelta(days=days)
    async with pool.acquire() as conn:
        teams = await conn.fetch("""
            SELECT et.id, et.team_name,
                   COALESCE(s.total, 0) as total_logs,
                   COALESCE(s.success, 0) as success_count,
                   COALESCE(m.cnt, 0) as member_count
            FROM external_teams et
            LEFT JOIN (
                SELECT team_id, COUNT(*) as total,
                       COUNT(*) FILTER (WHERE status='completed') as success
                FROM external_logs WHERE reported_at >= $1
                GROUP BY team_id
            ) s ON s.team_id = et.id
            LEFT JOIN (
                SELECT team_id, COUNT(*) as cnt
                FROM external_team_members
                GROUP BY team_id
            ) m ON m.team_id = et.id
            WHERE et.is_active = TRUE
            ORDER BY total_logs DESC
        """, since)

    return [
        {
            "team_id": t["id"],
            "team_name": t["team_name"],
            "total_logs": t["total_logs"],
            "success_count": t["success_count"],
            "member_count": t["member_count"],
        }
        for t in teams
    ]
