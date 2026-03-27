# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 多通道通知模块
@Version: 2.0.0
@Date: 2026-03-17

通知通道:
  - Webhook（企微群机器人）: 发送 Markdown 摘要通知
  - Email（SMTP）: 发送 HTML 完整报告

关联设计文档: §4.8 通知模块
关联需求: FR-009
"""

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import httpx
from config import settings
from database import get_pool

logger = logging.getLogger("ones-ai.notify")


# ================================================================
#  Webhook 通知（企微群机器人 / 其他 Webhook）
# ================================================================

def _build_webhook_summary(task: dict, ticket_results: list) -> str:
    """
    构建 Webhook Markdown 摘要（≤4096 字符限制）

    包含: 任务概要 + 结果统计 + 前几个工单摘要 + 详情链接
    """
    platform_url = f"http://172.60.1.35:9626/tasks/{task['id']}"
    submitted = task["submitted_at"].strftime("%m-%d %H:%M") if task.get("submitted_at") else "-"
    completed = task["completed_at"].strftime("%m-%d %H:%M") if task.get("completed_at") else "-"
    duration = f"{task.get('total_duration', 0):.0f}"

    lines = [
        f"## 📋 ones-AI 任务完成通知",
        f"",
        f"**提交人**: {task.get('display_name', task.get('ones_email', '-'))}",
        f"**任务 ID**: #{task['id']}",
        f"**提交时间**: {submitted}",
        f"**完成时间**: {completed}",
        f"",
        f"### 📊 结果统计",
        f"> 工单总数: **{task.get('ticket_count', 0)}**",
        f"> ✅ 成功: **{task.get('success_count', 0)}**",
        f"> ❌ 失败: **{task.get('failed_count', 0)}**",
        f"> ⏱ 耗时: **{duration}** 秒",
    ]

    # 添加前几个工单摘要（控制在 3000 字符内，留 1000 给头尾）
    if ticket_results:
        lines.append("")
        lines.append("### 📝 工单处理摘要")
        char_count = sum(len(l) for l in lines)
        for tr in ticket_results[:15]:  # 最多 15 个
            ticket_num = tr.get("ticket_id", "?")
            status_icon = "✅" if tr.get("status") == "success" else "❌"
            title = tr.get("ticket_title", "") or ""
            conclusion = tr.get("result_conclusion", "") or ""
            summary = (tr.get("summary", "") or "")[:80]
            # 显示格式: ✅ #ONES-668380 [标题] 结论/摘要
            display_text = ""
            if title:
                display_text = f"[{title[:40]}] "
            if conclusion:
                display_text += conclusion[:60]
            elif summary:
                display_text += summary
            line = f"> {status_icon} `#{ticket_num}` {display_text}"
            char_count += len(line) + 1
            if char_count > 3500:
                lines.append(f"> ... 更多工单请查看详情")
                break
            lines.append(line)

    lines.append("")
    lines.append(f"🔗 [查看完整详情]({platform_url})")

    return "\n".join(lines)


async def _send_webhook_notification(task: dict, ticket_results: list) -> bool:
    """发送 Webhook 摘要通知"""
    if not settings.NOTIFY_WEBHOOK_ENABLED:
        return True  # 未启用，视为成功（不记录失败）
    if not settings.WECOM_WEBHOOK_URL:
        logger.warning("Webhook 已启用但未配置 URL，跳过")
        return False

    content = _build_webhook_summary(task, ticket_results)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                settings.WECOM_WEBHOOK_URL,
                json={"msgtype": "markdown", "markdown": {"content": content}},
            )
            data = resp.json()
            if data.get("errcode", -1) == 0:
                logger.info(f"Webhook 通知发送成功 (task={task['id']})")
                return True
            else:
                logger.warning(f"Webhook 发送失败: {data}")
                return False
    except Exception as e:
        logger.warning(f"Webhook 通知异常: {e}")
        return False


# ================================================================
#  邮件通知（SMTP）
# ================================================================

def _build_email_html(task: dict, ticket_results: list) -> str:
    """
    构建 HTML 邮件完整报告（无字数限制）

    包含: 任务概要 + 每个工单的处理结果详情
    """
    platform_url = f"http://172.60.1.35:9626/tasks/{task['id']}"
    submitted = task["submitted_at"].strftime("%Y-%m-%d %H:%M:%S") if task.get("submitted_at") else "-"
    completed = task["completed_at"].strftime("%Y-%m-%d %H:%M:%S") if task.get("completed_at") else "-"
    duration = f"{task.get('total_duration', 0):.1f}"
    status_text = "全部成功 ✅" if task.get("failed_count", 0) == 0 else "部分失败 ⚠️"

    # 工单明细行
    ticket_rows = ""
    for tr in ticket_results:
        ticket_num = tr.get("ticket_id", "?")
        status = tr.get("status", "unknown")
        status_badge = '<span style="color:#22c55e;font-weight:bold">✅ 成功</span>' if status == "success" else '<span style="color:#ef4444;font-weight:bold">❌ 失败</span>'
        title = (tr.get("ticket_title", "") or "-")[:60]
        conclusion = (tr.get("result_conclusion", "") or "")[:100]
        summary = (tr.get("summary", "") or "-")[:200]
        code_dir = tr.get("code_directory", "-") or "-"
        error_msg = (tr.get("error_message", "") or "")[:150]
        error_row = f'<br><span style="color:#ef4444;font-size:12px">错误: {error_msg}</span>' if error_msg else ""
        conclusion_row = f'<br><span style="color:#6366f1;font-size:12px">结论: {conclusion}</span>' if conclusion else ""

        ticket_rows += f"""
        <tr style="border-bottom:1px solid #e5e7eb">
          <td style="padding:10px;font-family:monospace">#{ticket_num}</td>
          <td style="padding:10px">{status_badge}</td>
          <td style="padding:10px;font-size:13px">{title}</td>
          <td style="padding:10px;font-size:13px">{summary}{conclusion_row}{error_row}</td>
        </tr>"""

    html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:800px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.1)">
      <div style="background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;padding:24px 32px">
        <h1 style="margin:0;font-size:22px">🤖 ones-AI 任务完成通知</h1>
        <p style="margin:6px 0 0;opacity:0.9;font-size:14px">任务 #{task['id']} 已处理完毕</p>
      </div>

      <div style="padding:24px 32px">
        <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
          <tr>
            <td style="padding:8px 0;color:#6b7280;width:100px">提交人</td>
            <td style="padding:8px 0;font-weight:600">{task.get('display_name', task.get('ones_email', '-'))}</td>
            <td style="padding:8px 0;color:#6b7280;width:100px">状态</td>
            <td style="padding:8px 0;font-weight:600">{status_text}</td>
          </tr>
          <tr>
            <td style="padding:8px 0;color:#6b7280">提交时间</td>
            <td style="padding:8px 0">{submitted}</td>
            <td style="padding:8px 0;color:#6b7280">完成时间</td>
            <td style="padding:8px 0">{completed}</td>
          </tr>
        </table>

        <div style="display:flex;gap:12px;margin-bottom:24px">
          <div style="flex:1;background:#f0fdf4;border-radius:8px;padding:16px;text-align:center">
            <div style="font-size:28px;font-weight:700;color:#22c55e">{task.get('success_count', 0)}</div>
            <div style="font-size:12px;color:#6b7280;margin-top:4px">成功</div>
          </div>
          <div style="flex:1;background:#fef2f2;border-radius:8px;padding:16px;text-align:center">
            <div style="font-size:28px;font-weight:700;color:#ef4444">{task.get('failed_count', 0)}</div>
            <div style="font-size:12px;color:#6b7280;margin-top:4px">失败</div>
          </div>
          <div style="flex:1;background:#eff6ff;border-radius:8px;padding:16px;text-align:center">
            <div style="font-size:28px;font-weight:700;color:#3b82f6">{duration}s</div>
            <div style="font-size:12px;color:#6b7280;margin-top:4px">总耗时</div>
          </div>
        </div>

        <h3 style="font-size:16px;margin-bottom:12px;border-bottom:2px solid #e5e7eb;padding-bottom:8px">📋 工单处理明细</h3>
        <table style="width:100%;border-collapse:collapse">
          <thead>
            <tr style="background:#f9fafb">
              <th style="padding:10px;text-align:left;font-size:13px;color:#6b7280">工单号</th>
              <th style="padding:10px;text-align:left;font-size:13px;color:#6b7280">状态</th>
              <th style="padding:10px;text-align:left;font-size:13px;color:#6b7280">标题</th>
              <th style="padding:10px;text-align:left;font-size:13px;color:#6b7280">处理摘要</th>
            </tr>
          </thead>
          <tbody>{ticket_rows}</tbody>
        </table>

        <div style="margin-top:24px;text-align:center">
          <a href="{platform_url}" style="display:inline-block;padding:10px 32px;background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;text-decoration:none;border-radius:6px;font-weight:600">查看完整详情</a>
        </div>
      </div>

      <div style="background:#f9fafb;padding:16px 32px;text-align:center;font-size:12px;color:#9ca3af">
        此邮件由 ones-AI 智能工单处理平台自动发送
      </div>
    </div>
    """
    return html


async def _send_email_notification(task: dict, ticket_results: list) -> bool:
    """发送邮件完整报告"""
    if not settings.NOTIFY_EMAIL_ENABLED:
        return True  # 未启用，视为成功
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.warning("邮件通知已启用但 SMTP 未配置，跳过")
        return False

    to_email = task.get("ones_email", "")
    if not to_email:
        logger.warning(f"任务 {task['id']} 无用户邮箱，跳过邮件通知")
        return False

    html = _build_email_html(task, ticket_results)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[ones-AI] 任务 #{task['id']} 处理完成 — {task.get('success_count',0)} 成功 / {task.get('failed_count',0)} 失败"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_USER}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _smtp_send, msg, to_email)
        logger.info(f"邮件通知发送成功 (task={task['id']}, to={to_email})")
        return True
    except Exception as e:
        logger.warning(f"邮件通知发送失败: {e}")
        return False


def _smtp_send(msg: MIMEMultipart, to_email: str):
    """同步 SMTP 发送（在线程池执行）"""
    if settings.SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        server.starttls()
    server.login(settings.SMTP_USER, settings.SMTP_PASS)
    server.sendmail(settings.SMTP_USER, [to_email], msg.as_string())
    server.quit()


# ================================================================
#  统一入口
# ================================================================

async def send_task_notification(task_id: int):
    """
    任务完成后发送通知 [FR-009]

    多通道并发发送，任一失败不影响其他，绝不阻塞调用方。
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 查询任务信息
        task = await conn.fetchrow("""
            SELECT t.*, u.ones_email, u.display_name
            FROM tasks t JOIN users u ON u.id = t.user_id
            WHERE t.id=$1
        """, task_id)
        if not task or task["notification_sent"]:
            return

        task = dict(task)

        # 查询工单处理结果
        rows = await conn.fetch("""
            SELECT ticket_id, code_directory, status,
                   result_summary as summary, error_message,
                   ticket_title, result_conclusion, result_report
            FROM task_tickets WHERE task_id=$1
            ORDER BY id
        """, task_id)
        ticket_results = [dict(r) for r in rows]

        # 并发发送所有启用的通道
        results = await asyncio.gather(
            _send_webhook_notification(task, ticket_results),
            _send_email_notification(task, ticket_results),
            return_exceptions=True,
        )

        # 记录通知结果
        channels = ["webhook", "email"]
        for ch, result in zip(channels, results):
            if isinstance(result, Exception):
                status = "error"
                logger.warning(f"{ch} 通知异常: {result}")
            elif result is True:
                status = "sent"
            else:
                status = "failed"

            # 跳过未启用的通道
            if ch == "webhook" and not settings.NOTIFY_WEBHOOK_ENABLED:
                continue
            if ch == "email" and not settings.NOTIFY_EMAIL_ENABLED:
                continue

            await conn.execute("""
                INSERT INTO notification_logs (task_id, user_id, channel, status, content)
                VALUES ($1, $2, $3, $4, $5)
            """, task_id, task["user_id"], ch, status,
                f"通知{'成功' if status == 'sent' else '失败'}")

        # 标记已通知
        await conn.execute(
            "UPDATE tasks SET notification_sent=TRUE WHERE id=$1", task_id
        )
