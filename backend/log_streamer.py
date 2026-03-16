# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — WebSocket 日志流
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §4.6 日志流模块
关联需求: FR-006
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt

from config import settings
from database import get_pool
from task_executor import subscribe_logs, unsubscribe_logs

logger = logging.getLogger("ones-ai.ws")
router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/tasks/{task_id}/logs")
async def task_log_stream(websocket: WebSocket, task_id: int, token: str = Query("")):
    """
    WebSocket 日志流端点
    连接: ws://host/ws/tasks/{task_id}/logs?token=<JWT>
    """
    # Token 验证
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = int(payload.get("sub", 0))
        role = payload.get("role", "user")
    except (JWTError, Exception):
        await websocket.close(code=4001, reason="Token 无效")
        return

    # 检查权限
    pool = await get_pool()
    async with pool.acquire() as conn:
        task = await conn.fetchrow("SELECT user_id FROM tasks WHERE id=$1", task_id)
        if not task:
            await websocket.close(code=4004, reason="任务不存在")
            return
        if task["user_id"] != user_id and role != "admin":
            await websocket.close(code=4003, reason="无权限")
            return

    await websocket.accept()

    # 发送历史日志
    async with pool.acquire() as conn:
        logs = await conn.fetch(
            "SELECT content, log_type, timestamp FROM task_logs WHERE task_id=$1 ORDER BY id",
            task_id,
        )
    for log in logs:
        await websocket.send_json({
            "type": "log",
            "content": log["content"],
            "log_type": log["log_type"],
            "timestamp": str(log["timestamp"]),
        })

    # 订阅实时日志
    subscribe_logs(task_id, websocket)

    try:
        while True:
            # 保持连接，等待客户端消息（心跳）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe_logs(task_id, websocket)
