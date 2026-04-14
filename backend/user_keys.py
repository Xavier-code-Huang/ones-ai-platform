# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 用户 API Key 管理模块
@Version: 1.7.0
@Date: 2026-04-13

关联设计文档: §3.1 user_keys.py
关联需求: FR-ME-002 (用户 API Key 管理)
"""

import logging
from typing import Optional

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user, UserInfo
from crypto import encrypt_password, decrypt_password
from database import get_pool

logger = logging.getLogger("ones-ai.user_keys")
router = APIRouter(prefix="/api/user/keys", tags=["用户 API Key 管理"])


# ---- Pydantic 模型 ----

class AddKeyRequest(BaseModel):
    provider: str       # 'anthropic' | 'openai'
    api_key: str        # 明文 Key（只在添加时传输）
    label: str = ""


class UpdateKeyRequest(BaseModel):
    label: Optional[str] = None
    is_default: Optional[bool] = None


class KeyInfo(BaseModel):
    id: int
    provider: str
    key_preview: str    # "sk-ant-...Xk4Z"
    label: str
    is_default: bool
    created_at: str


class ValidateResult(BaseModel):
    valid: bool
    message: str


# ---- 工具函数 ----

def _build_key_preview(api_key: str) -> str:
    """生成 Key 掩码预览：前缀 + ... + 后 4 位"""
    if len(api_key) <= 8:
        return api_key[:2] + "..." + api_key[-2:] if len(api_key) > 4 else "****"
    # 提取前缀部分（如 sk-ant-api03-, sk-proj-, sk- 等）
    prefix = ""
    if api_key.startswith("sk-ant-"):
        prefix = "sk-ant-"
    elif api_key.startswith("sk-proj-"):
        prefix = "sk-proj-"
    elif api_key.startswith("sk-"):
        prefix = "sk-"
    else:
        prefix = api_key[:6]
    suffix = api_key[-4:]
    return f"{prefix}...{suffix}"


def _extract_key_suffix(api_key: str) -> str:
    """提取 Key 后 4 位"""
    return api_key[-4:] if len(api_key) >= 4 else api_key


def _preview_from_suffix(provider: str, key_suffix: str) -> str:
    """从 provider + key_suffix 构建掩码预览（用于列表/更新场景）"""
    suffix = key_suffix or "****"
    if provider == "anthropic":
        return f"sk-ant-...{suffix}"
    elif provider == "openai":
        return f"sk-...{suffix}"
    return f"...{suffix}"


# ---- API 端点 ----

@router.post("", response_model=KeyInfo)
async def add_key(req: AddKeyRequest, user: UserInfo = Depends(get_current_user)):
    """添加新 API Key [FR-ME-002, AC-002-1, AC-002-2]"""
    # 校验 provider
    if req.provider not in ("anthropic", "openai"):
        raise HTTPException(status_code=400, detail="provider 必须为 anthropic 或 openai")
    if not req.api_key or not req.api_key.strip():
        raise HTTPException(status_code=400, detail="api_key 不能为空")

    api_key = req.api_key.strip()
    encrypted = encrypt_password(api_key)
    key_suffix = _extract_key_suffix(api_key)
    key_preview = _build_key_preview(api_key)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # 检查是否是该 provider 下第一个 Key，如果是则自动设为默认
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM user_api_keys WHERE user_id=$1 AND provider=$2",
            user.id, req.provider,
        )
        is_default = count == 0  # 第一个 Key 自动设为默认

        row = await conn.fetchrow(
            """INSERT INTO user_api_keys (user_id, provider, api_key_encrypted, key_suffix, label, is_default)
               VALUES ($1, $2, $3, $4, $5, $6)
               RETURNING id, created_at""",
            user.id, req.provider, encrypted, key_suffix, req.label.strip(), is_default,
        )

    logger.info(f"用户 {user.id} 添加 {req.provider} Key (id={row['id']}, suffix={key_suffix})")
    return KeyInfo(
        id=row["id"],
        provider=req.provider,
        key_preview=key_preview,
        label=req.label.strip(),
        is_default=is_default,
        created_at=str(row["created_at"]),
    )


@router.get("", response_model=list[KeyInfo])
async def list_keys(
    provider: Optional[str] = None,
    user: UserInfo = Depends(get_current_user),
):
    """列出当前用户所有 Key（掩码展示）[FR-ME-002, AC-002-6]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if provider:
            rows = await conn.fetch(
                """SELECT id, provider, key_suffix, label, is_default, created_at
                   FROM user_api_keys
                   WHERE user_id=$1 AND provider=$2
                   ORDER BY provider, is_default DESC, created_at DESC""",
                user.id, provider,
            )
        else:
            rows = await conn.fetch(
                """SELECT id, provider, key_suffix, label, is_default, created_at
                   FROM user_api_keys
                   WHERE user_id=$1
                   ORDER BY provider, is_default DESC, created_at DESC""",
                user.id,
            )

    result = []
    for r in rows:
        result.append(KeyInfo(
            id=r["id"],
            provider=r["provider"],
            key_preview=_preview_from_suffix(r["provider"], r["key_suffix"]),
            label=r["label"] or "",
            is_default=r["is_default"],
            created_at=str(r["created_at"]),
        ))
    return result


@router.put("/{key_id}", response_model=KeyInfo)
async def update_key(
    key_id: int,
    req: UpdateKeyRequest,
    user: UserInfo = Depends(get_current_user),
):
    """更新标签 / 设为默认 [FR-ME-002, AC-002-4]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 校验 Key 归属
        row = await conn.fetchrow(
            """SELECT id, provider, key_suffix, label, is_default, created_at
               FROM user_api_keys WHERE id=$1 AND user_id=$2""",
            key_id, user.id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Key 不存在或无权操作")

        provider = row["provider"]
        label = row["label"]
        is_default = row["is_default"]

        # 更新标签
        if req.label is not None:
            label = req.label.strip()
            await conn.execute(
                "UPDATE user_api_keys SET label=$1, updated_at=NOW() WHERE id=$2",
                label, key_id,
            )

        # 设为默认（同 provider 下互斥）
        if req.is_default is True:
            async with conn.transaction():
                # 先将同用户同 Provider 的所有 Key is_default=FALSE
                await conn.execute(
                    "UPDATE user_api_keys SET is_default=FALSE, updated_at=NOW() WHERE user_id=$1 AND provider=$2",
                    user.id, provider,
                )
                # 再设目标为 TRUE
                await conn.execute(
                    "UPDATE user_api_keys SET is_default=TRUE, updated_at=NOW() WHERE id=$1",
                    key_id,
                )
            is_default = True

        preview = _preview_from_suffix(provider, row["key_suffix"])

    logger.info(f"用户 {user.id} 更新 Key {key_id} (label={label}, is_default={is_default})")
    return KeyInfo(
        id=row["id"],
        provider=provider,
        key_preview=preview,
        label=label,
        is_default=is_default,
        created_at=str(row["created_at"]),
    )


@router.delete("/{key_id}")
async def delete_key(key_id: int, user: UserInfo = Depends(get_current_user)):
    """删除 Key（检查进行中任务引用）[FR-ME-002, AC-002-5]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 校验 Key 归属
        row = await conn.fetchrow(
            "SELECT id, provider FROM user_api_keys WHERE id=$1 AND user_id=$2",
            key_id, user.id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Key 不存在或无权操作")

        # 检查是否有进行中的任务引用该 Key
        active_count = await conn.fetchval(
            """SELECT COUNT(*) FROM tasks
               WHERE api_key_id=$1 AND status IN ('pending', 'running')""",
            key_id,
        )
        if active_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"该 Key 正被 {active_count} 个进行中的任务使用，无法删除",
            )

        await conn.execute("DELETE FROM user_api_keys WHERE id=$1", key_id)

    logger.info(f"用户 {user.id} 删除 Key {key_id}")
    return {"message": "已删除", "id": key_id}


@router.post("/{key_id}/validate", response_model=ValidateResult)
async def validate_key(key_id: int, user: UserInfo = Depends(get_current_user)):
    """验证已保存的 Key 有效性 [FR-ME-002, AC-002-8]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, provider, api_key_encrypted FROM user_api_keys WHERE id=$1 AND user_id=$2",
            key_id, user.id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Key 不存在或无权操作")

    provider = row["provider"]
    api_key = decrypt_password(row["api_key_encrypted"])

    try:
        if provider == "anthropic":
            valid, message = await _validate_anthropic_key(api_key)
        elif provider == "openai":
            valid, message = await _validate_openai_key(api_key)
        else:
            valid, message = False, f"不支持的 Provider: {provider}"
    except Exception as e:
        logger.warning(f"验证 Key {key_id} 异常: {e}")
        valid, message = False, f"验证请求失败: {str(e)}"

    logger.info(f"用户 {user.id} 验证 Key {key_id} ({provider}): valid={valid}")
    return ValidateResult(valid=valid, message=message)


class ValidateKeyDirectRequest(BaseModel):
    provider: str
    api_key: str


@router.post("/validate-direct", response_model=ValidateResult)
async def validate_key_direct(req: ValidateKeyDirectRequest, user: UserInfo = Depends(get_current_user)):
    """直接验证明文 Key（不入库），用于添加前预验证"""
    if req.provider not in ("anthropic", "openai"):
        raise HTTPException(status_code=400, detail="provider 必须为 anthropic 或 openai")
    if not req.api_key or not req.api_key.strip():
        raise HTTPException(status_code=400, detail="api_key 不能为空")

    try:
        if req.provider == "anthropic":
            valid, message = await _validate_anthropic_key(req.api_key.strip())
        elif req.provider == "openai":
            valid, message = await _validate_openai_key(req.api_key.strip())
        else:
            valid, message = False, f"不支持的 Provider: {req.provider}"
    except Exception as e:
        logger.warning(f"直接验证 Key 异常: {e}")
        valid, message = False, f"验证请求失败: {str(e)}"

    return ValidateResult(valid=valid, message=message)


async def _validate_anthropic_key(api_key: str) -> tuple[bool, str]:
    """验证 Anthropic Key — GET /v1/models with X-Api-Key + anthropic-version header"""
    headers = {
        "X-Api-Key": api_key,
        "anthropic-version": "2023-06-01",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.anthropic.com/v1/models",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 200:
                return True, "Key 有效"
            elif resp.status == 401:
                return False, "Key 无效或已过期"
            elif resp.status == 403:
                return False, "Key 权限不足"
            else:
                body = await resp.text()
                return False, f"验证失败 (HTTP {resp.status}): {body[:200]}"


async def _validate_openai_key(api_key: str) -> tuple[bool, str]:
    """验证 OpenAI Key — GET /v1/models with Bearer token"""
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.openai.com/v1/models",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 200:
                return True, "Key 有效"
            elif resp.status == 401:
                return False, "Key 无效或已过期"
            elif resp.status == 403:
                return False, "Key 权限不足"
            else:
                body = await resp.text()
                return False, f"验证失败 (HTTP {resp.status}): {body[:200]}"
