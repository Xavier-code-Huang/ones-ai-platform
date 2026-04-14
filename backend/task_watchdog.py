# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 全局工单卡死防护 Watchdog
@Version: 1.0.0
@Date: 2026-03-26

关联设计文档: design.md §3.2
关联需求: FR-111 (14.4, 14.5)

定时扫描数据库，清理孤立的 running 工单和任务：
- 工单 running 超过 3 小时 → 强制标记 failed
- 任务 running 超过 4 小时 → 强制标记 failed
- 启动时清理历史遗留的孤立工单 (14.5)
"""

import asyncio
import logging
from datetime import datetime, timezone

from database import get_pool

logger = logging.getLogger("ones-ai.watchdog")

# 配置
SCAN_INTERVAL = 300      # 每 5 分钟扫描一次
TICKET_MAX_RUNNING = 3   # 工单最长 running 时间（小时）
TASK_MAX_RUNNING = 4     # 任务最长 running 时间（小时）


async def _cleanup_orphan_tickets():
    """清理孤立的 running 工单 [14.4 + 14.5]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 查找 running 超时的工单
        orphaned = await conn.fetch("""
            SELECT tt.id, tt.ticket_id, tt.task_id, tt.started_at
            FROM task_tickets tt
            WHERE tt.status = 'running'
              AND tt.started_at < NOW() - $1 * INTERVAL '1 hour'
        """, TICKET_MAX_RUNNING)

        if orphaned:
            logger.warning(f"Watchdog: 发现 {len(orphaned)} 个超时 running 工单")
            for row in orphaned:
                hours = (datetime.now(timezone.utc) - row["started_at"].replace(tzinfo=timezone.utc)).total_seconds() / 3600
                error_msg = f"Watchdog: 工单 {row['ticket_id']} 已 running {hours:.1f}h，强制标记为 failed"
                logger.warning(error_msg)

                await conn.execute("""
                    UPDATE task_tickets SET
                        status='failed',
                        error_message=COALESCE(error_message, '') || $1,
                        completed_at=NOW()
                    WHERE id=$2 AND status='running'
                """, f"\n[Watchdog] 超时强制终止 ({hours:.1f}h)", row["id"])

                # 清理该工单的剩余 phases
                await conn.execute("""
                    UPDATE task_ticket_phases SET
                        status='failed', completed_at=NOW(),
                        message='Watchdog 超时清理'
                    WHERE task_ticket_id=$1 AND status IN ('pending', 'active')
                """, row["id"])

                # 写入日志
                await conn.execute("""
                    INSERT INTO task_logs (task_id, task_ticket_id, log_type, content)
                    VALUES ($1, $2, 'system', $3)
                """, row["task_id"], row["id"], error_msg)

        return len(orphaned) if orphaned else 0


async def _cleanup_orphan_tasks():
    """清理孤立的 running 任务"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        orphaned = await conn.fetch("""
            SELECT id FROM tasks
            WHERE status = 'running'
              AND started_at < NOW() - $1 * INTERVAL '1 hour'
        """, TASK_MAX_RUNNING)

        if orphaned:
            logger.warning(f"Watchdog: 发现 {len(orphaned)} 个超时 running 任务")
            for row in orphaned:
                task_id = row["id"]
                # 将该任务下所有仍为 pending 的工单标 cancelled
                await conn.execute("""
                    UPDATE task_tickets SET status='cancelled', completed_at=NOW()
                    WHERE task_id=$1 AND status='pending'
                """, task_id)
                # 将该任务下仍为 running 的工单标 failed
                await conn.execute("""
                    UPDATE task_tickets SET status='failed',
                        error_message=COALESCE(error_message, '') || '\n[Watchdog] 任务超时清理',
                        completed_at=NOW()
                    WHERE task_id=$1 AND status='running'
                """, task_id)
                # 更新任务统计
                stats = await conn.fetchrow("""
                    SELECT
                        count(*) FILTER (WHERE status='completed') as done,
                        count(*) FILTER (WHERE status='failed') as fail
                    FROM task_tickets WHERE task_id=$1
                """, task_id)
                await conn.execute("""
                    UPDATE tasks SET status='failed',
                        success_count=$1, failed_count=$2, completed_at=NOW()
                    WHERE id=$3
                """, stats["done"], stats["fail"], task_id)

                logger.warning(f"Watchdog: 任务 {task_id} 已强制标记完成")

        return len(orphaned) if orphaned else 0


async def watchdog_loop():
    """Watchdog 主循环"""
    logger.info("Watchdog 启动，扫描间隔 %ds", SCAN_INTERVAL)

    # 启动时立即清理一次历史遗留 [14.5]
    try:
        tc = await _cleanup_orphan_tickets()
        tk = await _cleanup_orphan_tasks()
        if tc or tk:
            logger.info(f"Watchdog 启动清理: {tc} 个孤立工单, {tk} 个孤立任务")
    except Exception as e:
        logger.error(f"Watchdog 启动清理失败: {e}")

    while True:
        await asyncio.sleep(SCAN_INTERVAL)
        try:
            tc = await _cleanup_orphan_tickets()
            tk = await _cleanup_orphan_tasks()
            if tc or tk:
                logger.info(f"Watchdog 扫描: 清理 {tc} 个工单, {tk} 个任务")
        except Exception as e:
            logger.error(f"Watchdog 扫描异常: {e}")
