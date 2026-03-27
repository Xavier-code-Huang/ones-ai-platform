# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — AI 工单预分析
@Version: 1.0.0
@Date: 2026-03-26

关联设计文档: design.md §FR-110
关联需求: FR-110 AI 工单预分析
"""

import json
import logging
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user, UserInfo
from config import settings
from ones_client import query_tickets
from crypto import decrypt_password
from ssh_pool import get_ssh_connection
from database import get_pool

logger = logging.getLogger("ones-ai.preview")
router = APIRouter(prefix="/api/tasks", tags=["AI 预分析"])


# ---- Pydantic 模型 ----

class PreviewTicketInput(BaseModel):
    ticket_id: str
    code_directory: str = ""


class PreviewRequest(BaseModel):
    tickets: list[PreviewTicketInput]
    server_id: int = 0
    credential_id: int = 0


class PreviewResult(BaseModel):
    ticket_id: str
    title: str = ""
    description: str = ""
    problem_type: str = ""
    suggested_prompt: str = ""
    error: str = ""


# ---- AI 调用 ----

PREVIEW_SYSTEM_PROMPT = """你是一个资深 Android/系统级代码缺陷分析专家。
你将收到 ONES 工单信息和代码目录结构，请分析问题并生成一段精准的 AI 修复提示词。

要求：
1. 分析工单标题和描述，判断问题类型（bug/性能/兼容性/功能/其他）
2. 结合代码目录结构（如有），推断可能涉及的模块和文件
3. 生成 100-300 字的提示词，要求：
   - 清晰描述问题现象
   - 指出可能的根因方向
   - 给出修复思路建议
   - 如果能推断涉及文件，列出可能的修改文件路径

请严格返回以下 JSON 格式（不要包含 markdown 代码块标记）：
{"type": "问题类型", "prompt": "推荐提示词"}"""


async def _call_ai(user_prompt: str) -> dict:
    """
    调用 AI 模型生成预分析结果。
    使用 Anthropic 兼容格式（AI_BASE_URL 指向兼容网关）。
    """
    if not settings.AI_API_KEY:
        logger.warning("AI_API_KEY 未配置，跳过 AI 分析")
        return {"type": "", "prompt": ""}

    url = f"{settings.AI_BASE_URL}/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": settings.AI_API_KEY,
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": settings.AI_OPUS_MODEL,  # GLM-5
        "max_tokens": 1024,
        "system": PREVIEW_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    try:
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                # Anthropic 格式: content[0].text
                text = ""
                content = data.get("content", [])
                if content and isinstance(content, list):
                    text = content[0].get("text", "")

                # 尝试解析 JSON
                # 去掉可能的 markdown 代码块
                text = text.strip()
                if text.startswith("```"):
                    text = re.sub(r'^```\w*\n?', '', text)
                    text = re.sub(r'\n?```$', '', text)
                    text = text.strip()

                try:
                    result = json.loads(text)
                    return {
                        "type": result.get("type", ""),
                        "prompt": result.get("prompt", ""),
                    }
                except json.JSONDecodeError:
                    # AI 未返回有效 JSON，将原始文本作为提示词
                    return {"type": "分析", "prompt": text[:500]}
            else:
                logger.warning(f"AI 调用失败: HTTP {resp.status_code} - {resp.text[:200]}")
                return {"type": "", "prompt": ""}
    except Exception as e:
        logger.warning(f"AI 调用异常: {e}")
        return {"type": "", "prompt": ""}


async def _scan_code_directory(
    host: str, port: int, username: str, password: str,
    code_directory: str,
) -> str:
    """SSH 到服务器快速扫描代码目录结构，获取上下文信息。"""
    if not code_directory:
        return ""

    try:
        ssh_conn = await get_ssh_connection(host, port, username, password)

        # 快速获取：目录结构(2层) + 最近5条 git log
        scan_cmd = (
            f"cd '{code_directory}' 2>/dev/null && "
            f"echo '=== DIRECTORY ===' && "
            f"find . -maxdepth 2 -type d | head -50 && "
            f"echo '=== GIT_LOG ===' && "
            f"git log --oneline -5 2>/dev/null || echo '(no git)' && "
            f"echo '=== README ===' && "
            f"head -30 README* 2>/dev/null || echo '(no readme)'"
        )

        proc = await ssh_conn.create_process(scan_cmd)
        proc.stdin.write_eof()
        output = ""
        async for line in proc.stdout:
            output += line
        import asyncio
        await asyncio.wait_for(proc.wait(), timeout=10)
        return output[:3000]  # 限制上下文大小

    except Exception as e:
        logger.warning(f"代码目录扫描失败: {e}")
        return ""


# ---- API 端点 ----

@router.post("/preview", response_model=list[PreviewResult])
async def preview_tickets(
    req: PreviewRequest,
    user: UserInfo = Depends(get_current_user),
):
    """
    AI 工单预分析 [FR-110]

    流程:
    1. 解析工单号 → 调用 ONES API 获取标题/描述
    2. (可选) SSH 扫描代码目录获取上下文
    3. 调用 AI (GLM-5) 生成推荐提示词
    4. 返回分析结果
    """
    if not req.tickets:
        raise HTTPException(400, "至少需要一个工单号")

    # 提取纯数字用于 ONES 查询
    numbers = []
    ticket_map = {}  # number -> ticket_id 原始值
    for t in req.tickets:
        tid = t.ticket_id.strip()
        # 提取数字部分
        match = re.search(r"(\d+)", tid)
        if match:
            num = int(match.group(1))
            numbers.append(num)
            ticket_map[num] = tid

    # 1. 查询 ONES 工单信息
    ones_data = {}
    if numbers:
        try:
            raw = await query_tickets(numbers)
            for item in raw:
                num = item.get("number")
                if num:
                    ones_data[num] = {
                        "title": item.get("name", ""),
                        "desc": item.get("desc", item.get("description", "")),
                    }
        except Exception as e:
            logger.warning(f"ONES 查询失败: {e}")

    # 2. (可选) 扫描代码目录
    code_context = ""
    if req.server_id and req.credential_id:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                cred = await conn.fetchrow("""
                    SELECT usc.ssh_username, usc.ssh_password_encrypted,
                           s.host, s.ssh_port
                    FROM user_server_credentials usc
                    JOIN servers s ON s.id = usc.server_id
                    WHERE usc.id=$1 AND usc.user_id=$2
                """, req.credential_id, user.id)

            if cred:
                ssh_password = decrypt_password(cred["ssh_password_encrypted"])
                # 只扫第一个有代码目录的工单
                first_dir = next((t.code_directory for t in req.tickets if t.code_directory), "")
                if first_dir:
                    code_context = await _scan_code_directory(
                        cred["host"], cred["ssh_port"],
                        cred["ssh_username"], ssh_password,
                        first_dir,
                    )
        except Exception as e:
            logger.warning(f"代码目录扫描失败: {e}")

    # 3. 逐工单调用 AI
    results = []
    for t in req.tickets:
        tid = t.ticket_id.strip()
        match = re.search(r"(\d+)", tid)
        num = int(match.group(1)) if match else 0

        ticket_info = ones_data.get(num, {})
        title = ticket_info.get("title", "")
        desc = ticket_info.get("desc", "")

        if not title and not desc:
            # ONES 查不到，返回空结果但不报错
            results.append(PreviewResult(
                ticket_id=tid,
                title="",
                description="",
                problem_type="",
                suggested_prompt="",
                error="未能从 ONES 获取工单信息",
            ))
            continue

        # 构建 AI 输入
        user_prompt = f"工单号: {tid}\n标题: {title}\n描述: {desc[:2000]}"
        if code_context:
            user_prompt += f"\n\n代码目录结构:\n{code_context}"
        if t.code_directory:
            user_prompt += f"\n\n代码路径: {t.code_directory}"

        ai_result = await _call_ai(user_prompt)

        results.append(PreviewResult(
            ticket_id=tid,
            title=title,
            description=desc[:500],
            problem_type=ai_result.get("type", ""),
            suggested_prompt=ai_result.get("prompt", ""),
        ))

    return results
