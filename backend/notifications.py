# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 企微通知模块
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §4.8 通知模块
关联需求: FR-009
"""

import logging
import httpx
from config import settings
from database import get_pool

logger = logging.getLogger("ones-ai.notify")


async def _get_wecom_access_token() -> str:
    """获取企微 access_token"""
    if not settings.WECOM_CORP_ID or not settings.WECOM_SECRET:
        return ""
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={settings.WECOM_CORP_ID}&corpsecret={settings.WECOM_SECRET}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        data = resp.json()
        return data.get("access_token", "")


async def send_wecom_message(user_email: str, content: str) -> bool:
    """
    发送企微应用消息

    Args:
        user_email: 用户企微邮箱（用于匹配用户）
        content: 消息内容
    """
    # 方案一: Webhook（简单方案）
    if settings.WECOM_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    settings.WECOM_WEBHOOK_URL,
                    json={
                        "msgtype": "markdown",
                        "markdown": {"content": content},
                    },
                )
                return resp.status_code == 200
        except Exception as e:
            logger.warning(f"企微 Webhook 发送失败: {e}")
            return False

    # 方案二: 应用消息
    token = await _get_wecom_access_token()
    if not token:
        logger.warning("无法获取企微 access_token，跳过通知")
        return False

    # 通过邮箱获取 userid
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # 查找用户
            resp = await client.get(
                f"https://qyapi.weixin.qq.com/cgi-bin/user/get_userid_by_email?access_token={token}",
                params={"email": user_email, "email_type": 1},
            )
            user_data = resp.json()
            userid = user_data.get("userid", "")
            if not userid:
                logger.warning(f"未找到企微用户: {user_email}")
                return False

            # 发送消息
            resp = await client.post(
                f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
                json={
                    "touser": userid,
                    "msgtype": "markdown",
                    "agentid": settings.WECOM_AGENT_ID,
                    "markdown": {"content": content},
                },
            )
            result = resp.json()
            return result.get("errcode") == 0
    except Exception as e:
        logger.warning(f"企微消息发送失败: {e}")
        return False


async def send_task_notification(task_id: int):
    """任务完成后发送通知 [FR-009]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        task = await conn.fetchrow("""
            SELECT t.*, u.ones_email, u.display_name
            FROM tasks t JOIN users u ON u.id = t.user_id
            WHERE t.id=$1
        """, task_id)
        if not task or task["notification_sent"]:
            return

        # 构建通知内容
        platform_url = f"http://172.60.1.35:9611/tasks/{task_id}"
        content = f"""## 📋 ones-AI 任务完成通知

**任务 ID**: #{task_id}
**提交时间**: {task['submitted_at']}
**完成时间**: {task['completed_at']}

### 📊 结果统计
> 工单总数: **{task['ticket_count']}**
> ✅ 成功: **{task['success_count']}**
> ❌ 失败: **{task['failed_count']}**
> ⏱ 总耗时: **{task['total_duration']:.0f}** 秒

🔗 [查看详情]({platform_url})"""

        success = await send_wecom_message(task["ones_email"], content)

        # 记录通知状态
        await conn.execute("""
            INSERT INTO notification_logs (task_id, user_id, channel, status, content)
            VALUES ($1, $2, 'wecom', $3, $4)
        """, task_id, task["user_id"], "sent" if success else "failed", content)

        await conn.execute(
            "UPDATE tasks SET notification_sent=TRUE WHERE id=$1", task_id
        )
