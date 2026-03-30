# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 准确度评测 API
@Version: 1.0.0
@Date: 2026-03-30
"""

import logging
from fastapi import APIRouter, Query
from database import get_pool

logger = logging.getLogger("ones-ai.accuracy-api")

router = APIRouter(prefix="/api/accuracy", tags=["准确度评测"])


@router.get("/summary")
async def get_accuracy_summary():
    """获取准确度统计摘要"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 总评测数
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_effective = true) as effective,
                COUNT(*) FILTER (WHERE is_effective = false AND skip_reason = '') as ineffective,
                COUNT(*) FILTER (WHERE skip_reason != '' AND skip_reason IS NOT NULL) as skipped,
                ROUND(AVG(total_score) FILTER (WHERE skip_reason = '' OR skip_reason IS NULL), 1) as avg_score,
                ROUND(AVG(score_file_match) FILTER (WHERE skip_reason = '' OR skip_reason IS NULL), 1) as avg_file,
                ROUND(AVG(score_root_cause) FILTER (WHERE skip_reason = '' OR skip_reason IS NULL), 1) as avg_root,
                ROUND(AVG(score_fix_similar) FILTER (WHERE skip_reason = '' OR skip_reason IS NULL), 1) as avg_fix,
                ROUND(AVG(score_actionable) FILTER (WHERE skip_reason = '' OR skip_reason IS NULL), 1) as avg_action,
                ROUND(AVG(score_consistency) FILTER (WHERE skip_reason = '' OR skip_reason IS NULL), 1) as avg_consist
            FROM accuracy_evaluations
        """)

        # 待评测数
        pending = await conn.fetchval("""
            SELECT COUNT(*) FROM task_tickets tt
            LEFT JOIN accuracy_evaluations ae ON ae.task_ticket_id = tt.id
            WHERE tt.status = 'completed'
              AND ae.id IS NULL
              AND tt.result_report IS NOT NULL
              AND tt.result_report != ''
        """)

        total_tickets = await conn.fetchval(
            "SELECT COUNT(DISTINCT ticket_id) FROM task_tickets WHERE status='completed'"
        )

    evaluated = (stats["total"] or 0) - (stats["skipped"] or 0)
    effective = stats["effective"] or 0
    rate = f"{effective / evaluated * 100:.1f}%" if evaluated > 0 else "N/A"

    return {
        "accuracy_rate": rate,
        "total_evaluated": evaluated,
        "effective_count": effective,
        "ineffective_count": stats["ineffective"] or 0,
        "skipped_count": stats["skipped"] or 0,
        "pending_count": pending or 0,
        "total_completed_tickets": total_tickets or 0,
        "avg_score": float(stats["avg_score"] or 0),
        "dimension_avg": {
            "file_match": float(stats["avg_file"] or 0),
            "root_cause": float(stats["avg_root"] or 0),
            "fix_similar": float(stats["avg_fix"] or 0),
            "actionable": float(stats["avg_action"] or 0),
            "consistency": float(stats["avg_consist"] or 0),
        },
    }


@router.get("/tickets")
async def get_accuracy_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    effective_only: bool = Query(False),
):
    """获取评测详情列表"""
    pool = await get_pool()
    offset = (page - 1) * page_size

    where = ""
    if effective_only:
        where = "AND ae.is_effective = true"

    async with pool.acquire() as conn:
        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM accuracy_evaluations ae
            WHERE (ae.skip_reason = '' OR ae.skip_reason IS NULL) {where}
        """)

        rows = await conn.fetch(f"""
            SELECT ae.*, tt.ticket_title
            FROM accuracy_evaluations ae
            JOIN task_tickets tt ON tt.id = ae.task_ticket_id
            WHERE (ae.skip_reason = '' OR ae.skip_reason IS NULL) {where}
            ORDER BY ae.total_score DESC, ae.evaluated_at DESC
            LIMIT $1 OFFSET $2
        """, page_size, offset)

    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "ticket_id": r["ticket_id"],
            "ticket_title": r["ticket_title"] or "",
            "gerrit_change_url": r["gerrit_change_url"],
            "gerrit_diff_summary": r["gerrit_diff_summary"],
            "scores": {
                "file_match": r["score_file_match"],
                "root_cause": r["score_root_cause"],
                "fix_similar": r["score_fix_similar"],
                "actionable": r["score_actionable"],
                "consistency": r["score_consistency"],
                "total": r["total_score"],
            },
            "is_effective": r["is_effective"],
            "reasoning": r["llm_reasoning"],
            "evaluated_at": r["evaluated_at"].isoformat() if r["evaluated_at"] else "",
        })

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.post("/evaluate/{task_ticket_id}")
async def evaluate_single(task_ticket_id: int):
    """评测单个工单"""
    pool = await get_pool()
    from accuracy_engine import AccuracyEngine
    engine = AccuracyEngine(pool)
    result = await engine.evaluate_ticket(task_ticket_id)
    await engine.save_result(result)
    return {
        "ticket_id": result.ticket_id,
        "total_score": result.total_score,
        "is_effective": result.is_effective,
        "reasoning": result.reasoning,
        "skip_reason": result.skip_reason,
    }


@router.post("/batch")
async def batch_evaluate(limit: int = Query(50, ge=1, le=500)):
    """批量评测"""
    pool = await get_pool()
    from accuracy_engine import AccuracyEngine
    engine = AccuracyEngine(pool)
    stats = await engine.batch_evaluate(limit=limit)
    return stats
