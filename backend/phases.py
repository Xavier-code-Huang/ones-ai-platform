# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 工单处理阶段管理
@Version: 1.0.0
@Date: 2026-03-26

关联设计文档: design.md §3.1, §5
关联需求: FR-101, FR-103, FR-104
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from database import get_pool

logger = logging.getLogger("ones-ai.phases")

# ============================================================
#  预定义处理阶段（有序列表）
# ============================================================

PIPELINE_PHASES = [
    {"name": "validating",         "label": "校验工单信息",     "icon": "🔍", "order": 1},
    {"name": "checking_path",      "label": "检查代码路径",     "icon": "📁", "order": 2},
    {"name": "checking_agent_dir", "label": "检查 Agent-Teams", "icon": "📂", "order": 3},
    {"name": "container_starting", "label": "启动容器环境",     "icon": "🐳", "order": 4},
    {"name": "agent_analyzing",    "label": "AI 分析工单",      "icon": "🤖", "order": 5},
    {"name": "agent_modifying",    "label": "AI 修改代码",      "icon": "🔧", "order": 6},
    {"name": "agent_verifying",    "label": "结果验证",         "icon": "✅", "order": 7},
    {"name": "agent_reporting",    "label": "生成报告",         "icon": "📝", "order": 8},
]

# 阶段名到信息的快速查找
PHASE_MAP = {p["name"]: p for p in PIPELINE_PHASES}


async def init_phases(task_ticket_id: int) -> List[Dict[str, Any]]:
    """
    为工单预创建全部 8 个阶段记录（status=pending）。
    在工单开始执行时调用。

    Returns:
        创建的阶段记录列表
    """
    pool = await get_pool()
    phases = []

    async with pool.acquire() as conn:
        for phase in PIPELINE_PHASES:
            row = await conn.fetchrow(
                """
                INSERT INTO task_ticket_phases
                    (task_ticket_id, phase_name, phase_label, phase_order, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT DO NOTHING
                RETURNING id, phase_name, phase_label, phase_order, status, message,
                          started_at, completed_at, duration_ms
                """,
                task_ticket_id,
                phase["name"],
                phase["label"],
                phase["order"],
            )
            if row:
                phases.append(dict(row))

    logger.debug(f"初始化 {len(phases)} 个阶段: task_ticket_id={task_ticket_id}")
    return phases


async def advance_phase(
    task_ticket_id: int,
    phase_name: str,
    status: str,
    message: str = "",
) -> Optional[Dict[str, Any]]:
    """
    推进指定阶段的状态。

    Args:
        task_ticket_id: 工单记录 ID
        phase_name: 阶段标识 (如 'validating', 'agent_analyzing')
        status: 目标状态 ('active', 'completed', 'failed', 'skipped')
        message: 阶段描述/输出摘要

    Returns:
        更新后的阶段记录，或 None（阶段不存在时）
    """
    pool = await get_pool()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        if status == "active":
            row = await conn.fetchrow(
                """
                UPDATE task_ticket_phases
                SET status = 'active', started_at = $3, message = $4
                WHERE task_ticket_id = $1 AND phase_name = $2
                RETURNING *
                """,
                task_ticket_id, phase_name, now, message,
            )
        elif status in ("completed", "failed", "skipped"):
            # 计算持续时间
            row = await conn.fetchrow(
                """
                UPDATE task_ticket_phases
                SET status = $3,
                    completed_at = $4,
                    message = CASE WHEN $5 != '' THEN $5 ELSE message END,
                    duration_ms = CASE
                        WHEN started_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM ($4 - started_at)) * 1000
                        ELSE 0
                    END
                WHERE task_ticket_id = $1 AND phase_name = $2
                RETURNING *
                """,
                task_ticket_id, phase_name, status, now, message,
            )
        else:
            logger.warning(f"未知状态: {status}")
            return None

    if row:
        logger.debug(f"阶段推进: {phase_name} -> {status} (ticket={task_ticket_id})")
        return dict(row)
    else:
        logger.warning(f"阶段不存在: {phase_name} (ticket={task_ticket_id})")
        return None


async def complete_remaining_phases(
    task_ticket_id: int,
    final_status: str = "skipped",
    message: str = "",
):
    """
    将工单的所有仍为 pending 或 active 的阶段标记为指定状态。
    用于工单完成/失败后清理剩余阶段。
    """
    pool = await get_pool()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE task_ticket_phases
            SET status = $2,
                completed_at = COALESCE(completed_at, $3),
                message = CASE WHEN $4 != '' THEN $4 ELSE message END,
                duration_ms = CASE
                    WHEN started_at IS NOT NULL AND completed_at IS NULL
                    THEN EXTRACT(EPOCH FROM ($3 - started_at)) * 1000
                    ELSE COALESCE(duration_ms, 0)
                END
            WHERE task_ticket_id = $1 AND status IN ('pending', 'active')
            """,
            task_ticket_id, final_status, now, message,
        )
    logger.debug(f"清理剩余阶段: ticket={task_ticket_id}, status={final_status}")


async def get_phases(task_ticket_id: int) -> List[Dict[str, Any]]:
    """
    获取工单的所有阶段记录，按 order 排序。

    Returns:
        阶段列表，每项含 phase_name, phase_label, status, message 等
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, task_ticket_id, phase_name, phase_label, phase_order,
                   status, message, started_at, completed_at, duration_ms
            FROM task_ticket_phases
            WHERE task_ticket_id = $1
            ORDER BY phase_order
            """,
            task_ticket_id,
        )

    result = []
    for row in rows:
        d = dict(row)
        # 附加 icon
        phase_info = PHASE_MAP.get(d["phase_name"], {})
        d["icon"] = phase_info.get("icon", "⬜")
        # 序列化时间戳
        for key in ("started_at", "completed_at"):
            if d[key]:
                d[key] = d[key].isoformat()
        result.append(d)

    return result


def format_phase_for_ws(
    phase_name: str,
    status: str,
    message: str,
    ticket_id: str = "",
    ticket_db_id: int = 0,
) -> dict:
    """
    构造 WebSocket phase_change 消息体。
    """
    phase_info = PHASE_MAP.get(phase_name, {"label": phase_name, "icon": "⬜"})
    return {
        "type": "phase_change",
        "ticket_id": ticket_id,
        "ticket_db_id": ticket_db_id,
        "phase": phase_name,
        "phase_label": phase_info["label"],
        "phase_icon": phase_info["icon"],
        "status": status,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
