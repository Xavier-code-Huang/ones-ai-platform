# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — Provider 模型管理模块
@Version: 1.7.0
@Date: 2026-04-13

关联设计文档: §3.2 providers.py
关联需求: FR-ME-003 (动态模型发现), FR-ME-009 (Provider 模型管理 API)
"""

import asyncio
import logging
import time
from typing import Optional

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user, require_admin, UserInfo
from crypto import decrypt_password
from database import get_pool

logger = logging.getLogger("ones-ai.providers")

# ---- 路由 ----
router = APIRouter(tags=["Provider 模型管理"])

# ---- 常量 ----
CACHE_TTL = 3600  # 1 小时

# OpenAI 模型过滤规则
INCLUDE_PREFIXES = ('gpt-4', 'gpt-5', 'o1', 'o3', 'o4', 'codex')
EXCLUDE_KEYWORDS = ('embedding', 'whisper', 'dall-e', 'tts', 'audio', 'realtime', 'search')

# ---- 全局缓存 + 并发锁 ----
_model_cache: dict[str, tuple[list, float]] = {}  # provider -> (models, timestamp)
_discover_lock: dict[str, asyncio.Lock] = {}       # provider -> asyncio.Lock


# ---- Pydantic 模型 ----

class ModelInfo(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: int
    provider: str
    model_id: str
    display_name: str
    description: str = ""
    is_default: bool = False
    is_active: bool = True
    sort_order: int = 0
    source: str = "manual"


class AddModelRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    provider: str
    model_id: str
    display_name: str
    description: str = ""
    is_default: bool = False
    is_active: bool = True
    sort_order: int = 0


def _row_to_model_info(r) -> ModelInfo:
    """将数据库行转换为 ModelInfo（消除重复构造代码）"""
    return ModelInfo(
        id=r["id"],
        provider=r["provider"],
        model_id=r["model_id"],
        display_name=r["display_name"],
        description=r.get("description") or "",
        is_default=r["is_default"],
        is_active=r["is_active"],
        sort_order=r["sort_order"],
        source=r.get("source") or "manual",
    )


# ---- 动态发现函数 ----

async def discover_anthropic_models(api_key: str) -> list[dict]:
    """调用 Anthropic /v1/models 获取可用模型列表 [FR-ME-003, AC-003-1]"""
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
            if resp.status != 200:
                body = await resp.text()
                logger.warning(f"Anthropic /v1/models 失败 (HTTP {resp.status}): {body[:200]}")
                return []
            data = await resp.json()

    models = []
    for m in data.get("data", []):
        models.append({
            "provider": "anthropic",
            "model_id": m["id"],
            "display_name": m.get("display_name", m["id"]),
        })
    logger.info(f"Anthropic 动态发现: {len(models)} 个模型")
    return models


async def discover_openai_models(api_key: str) -> list[dict]:
    """调用 OpenAI /v1/models 获取可用模型列表，过滤编程相关模型 [FR-ME-003, AC-003-2]"""
    headers = {"Authorization": f"Bearer {api_key}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.openai.com/v1/models",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.warning(f"OpenAI /v1/models 失败 (HTTP {resp.status}): {body[:200]}")
                return []
            data = await resp.json()

    models = []
    for m in data.get("data", []):
        model_id = m["id"]
        if any(model_id.startswith(p) for p in INCLUDE_PREFIXES):
            if not any(kw in model_id for kw in EXCLUDE_KEYWORDS):
                models.append({
                    "provider": "openai",
                    "model_id": model_id,
                    "display_name": model_id,
                })
    logger.info(f"OpenAI 动态发现: {len(models)} 个编程相关模型")
    return models


# ---- 缓存 + DB 辅助函数 ----

async def _get_user_default_key(user_id: int, provider: str) -> Optional[str]:
    """获取用户指定 Provider 的默认 Key（解密后明文）"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT api_key_encrypted FROM user_api_keys
               WHERE user_id=$1 AND provider=$2 AND is_default=TRUE
               LIMIT 1""",
            user_id, provider,
        )
        if not row:
            # 没有默认 Key，取最新的一个
            row = await conn.fetchrow(
                """SELECT api_key_encrypted FROM user_api_keys
                   WHERE user_id=$1 AND provider=$2
                   ORDER BY created_at DESC LIMIT 1""",
                user_id, provider,
            )
    if row:
        return decrypt_password(row["api_key_encrypted"])
    return None


async def _upsert_models_to_db(provider: str, models: list[dict]):
    """将发现的模型 UPSERT 到 provider_models 表 (source='discovered')"""
    if not models:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        for m in models:
            await conn.execute(
                """INSERT INTO provider_models (provider, model_id, display_name, source, discovered_at, is_active)
                   VALUES ($1, $2, $3, 'discovered', NOW(), TRUE)
                   ON CONFLICT (provider, model_id)
                   DO UPDATE SET display_name=EXCLUDED.display_name,
                                 discovered_at=NOW(),
                                 updated_at=NOW()""",
                m["provider"], m["model_id"], m["display_name"],
            )
    logger.info(f"UPSERT {len(models)} 个 {provider} 模型到 provider_models 表")


async def _load_models_from_db(provider: str) -> list[dict]:
    """从 provider_models 表加载活跃模型"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, provider, model_id, display_name, description,
                      is_default, is_active, sort_order, source
               FROM provider_models
               WHERE provider=$1 AND is_active=TRUE
               ORDER BY sort_order ASC, model_id ASC""",
            provider,
        )
    return [dict(r) for r in rows]


async def _do_discover(provider: str, api_key: str) -> list[dict]:
    """根据 provider 类型调用对应的发现函数"""
    if provider == "anthropic":
        return await discover_anthropic_models(api_key)
    elif provider == "openai":
        return await discover_openai_models(api_key)
    return []


# ---- 用户侧 API ----

@router.get("/api/providers/models", response_model=list[ModelInfo])
async def get_all_models(user: UserInfo = Depends(get_current_user)):
    """获取所有 Provider 的活跃模型 [FR-ME-009, AC-009-1]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, provider, model_id, display_name, description,
                      is_default, is_active, sort_order, source
               FROM provider_models
               WHERE is_active=TRUE
               ORDER BY provider, sort_order ASC, model_id ASC"""
        )
    return [_row_to_model_info(r) for r in rows]


@router.get("/api/providers/{provider}/models", response_model=list[ModelInfo])
async def get_provider_models(
    provider: str,
    user: UserInfo = Depends(get_current_user),
):
    """获取指定 Provider 的模型（触发动态发现）[FR-ME-009, AC-009-2]

    逻辑:
    1. 检查全局内存缓存 (_model_cache)
    2. 未过期 -> 直接从 DB 返回活跃记录
    3. 过期且 provider 是 anthropic/openai:
       a. 获取 _discover_lock[provider]
       b. 二次检查缓存
       c. 取用户默认 Key 调动态发现
       d. UPSERT 到 provider_models 表
       e. 更新内存缓存
    4. 返回 is_active=TRUE 的记录
    5. 发现失败时仍返回 DB 已有数据（数据库兜底）
    """
    if provider not in ("glm", "anthropic", "openai"):
        raise HTTPException(status_code=400, detail=f"不支持的 Provider: {provider}")

    # GLM 不需要动态发现，直接返回 DB 数据
    if provider == "glm":
        models = await _load_models_from_db(provider)
        return [_row_to_model_info(m) for m in models]

    # Anthropic / OpenAI: 检查缓存
    now = time.time()
    cached = _model_cache.get(provider)
    if cached and (now - cached[1]) < CACHE_TTL:
        # 缓存命中，直接从 DB 返回
        models = await _load_models_from_db(provider)
        return [_row_to_model_info(m) for m in models]

    # 缓存过期，触发动态发现
    if provider not in _discover_lock:
        _discover_lock[provider] = asyncio.Lock()

    async with _discover_lock[provider]:
        # 二次检查缓存（拿到锁后可能已被其他请求刷新，重新取时间）
        now2 = time.time()
        cached = _model_cache.get(provider)
        if cached and (now2 - cached[1]) < CACHE_TTL:
            models = await _load_models_from_db(provider)
            return [_row_to_model_info(m) for m in models]

        # 获取用户默认 Key
        api_key = await _get_user_default_key(user.id, provider)
        discovered = []
        if api_key:
            try:
                discovered = await _do_discover(provider, api_key)
                if discovered:
                    await _upsert_models_to_db(provider, discovered)
                    _model_cache[provider] = (discovered, time.time())
                    logger.info(f"动态发现 {provider}: {len(discovered)} 个模型，已更新缓存")
            except Exception as e:
                logger.warning(f"动态发现 {provider} 失败: {e}，将使用数据库兜底")
        else:
            logger.info(f"用户 {user.id} 无 {provider} Key，跳过动态发现")

    # 无论发现是否成功，都从 DB 返回（数据库兜底）
    models = await _load_models_from_db(provider)
    return [_row_to_model_info(m) for m in models]


# ---- 管理员 API ----

@router.post("/api/admin/providers/models", response_model=ModelInfo)
async def admin_add_model(
    req: AddModelRequest,
    user: UserInfo = Depends(require_admin),
):
    """管理员添加/更新模型 (source='manual') [FR-ME-009, AC-009-3]"""
    if req.provider not in ("glm", "anthropic", "openai"):
        raise HTTPException(status_code=400, detail=f"不支持的 Provider: {req.provider}")
    if not req.model_id or not req.model_id.strip():
        raise HTTPException(status_code=400, detail="model_id 不能为空")
    if not req.display_name or not req.display_name.strip():
        raise HTTPException(status_code=400, detail="display_name 不能为空")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO provider_models
                   (provider, model_id, display_name, description, is_default, is_active, sort_order, source)
               VALUES ($1, $2, $3, $4, $5, $6, $7, 'manual')
               ON CONFLICT (provider, model_id)
               DO UPDATE SET display_name=EXCLUDED.display_name,
                             description=EXCLUDED.description,
                             is_default=EXCLUDED.is_default,
                             is_active=EXCLUDED.is_active,
                             sort_order=EXCLUDED.sort_order,
                             source='manual',
                             updated_at=NOW()
               RETURNING id, provider, model_id, display_name, description,
                         is_default, is_active, sort_order, source""",
            req.provider, req.model_id.strip(), req.display_name.strip(),
            req.description, req.is_default, req.is_active, req.sort_order,
        )

    logger.info(f"管理员 {user.id} 添加/更新模型: {req.provider}/{req.model_id}")
    return _row_to_model_info(row)


@router.delete("/api/admin/providers/models/{model_db_id}")
async def admin_delete_model(
    model_db_id: int,
    user: UserInfo = Depends(require_admin),
):
    """管理员删除模型 [FR-ME-009, AC-009-4]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, provider, model_id FROM provider_models WHERE id=$1",
            model_db_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="模型不存在")

        await conn.execute("DELETE FROM provider_models WHERE id=$1", model_db_id)

    logger.info(f"管理员 {user.id} 删除模型: id={model_db_id} ({row['provider']}/{row['model_id']})")
    return {"message": "已删除", "id": model_db_id}


@router.post("/api/admin/providers/{provider}/discover")
async def admin_trigger_discover(
    provider: str,
    user: UserInfo = Depends(require_admin),
):
    """管理员手动触发模型发现（清除缓存 + 重新调 API）[FR-ME-009, AC-009-5]"""
    if provider not in ("anthropic", "openai"):
        raise HTTPException(status_code=400, detail=f"不支持动态发现的 Provider: {provider}")

    # 清除该 provider 的缓存
    _model_cache.pop(provider, None)

    # 获取管理员自己的 Key 来触发发现
    api_key = await _get_user_default_key(user.id, provider)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"您未配置 {provider} 的 API Key，无法触发模型发现",
        )

    try:
        discovered = await _do_discover(provider, api_key)
        if discovered:
            await _upsert_models_to_db(provider, discovered)
            _model_cache[provider] = (discovered, time.time())
            logger.info(f"管理员 {user.id} 手动触发 {provider} 发现: {len(discovered)} 个模型")
            return {
                "message": f"发现 {len(discovered)} 个 {provider} 模型",
                "count": len(discovered),
                "models": [m["model_id"] for m in discovered],
            }
        else:
            return {"message": f"{provider} 未发现任何模型", "count": 0, "models": []}
    except Exception as e:
        logger.error(f"管理员手动发现 {provider} 失败: {e}")
        raise HTTPException(status_code=500, detail=f"模型发现失败: {str(e)}")
