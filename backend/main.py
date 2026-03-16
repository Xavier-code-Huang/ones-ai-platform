# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — FastAPI 应用入口
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §1.3 项目结构
"""

import asyncio
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db, close_pool, get_pool
from task_executor import task_worker

# 配置日志
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ones-ai")

# Worker 任务引用
_worker_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _worker_task

    # 启动
    logger.info(f"ones-AI Platform {settings.APP_VERSION} 启动中...")
    await init_db()
    await _init_default_configs()
    _worker_task = asyncio.create_task(task_worker())
    logger.info("✅ 所有服务已启动")

    yield

    # 关闭
    logger.info("正在关闭...")
    if _worker_task:
        _worker_task.cancel()
    await close_pool()
    from ssh_pool import close_all_connections
    await close_all_connections()
    logger.info("✅ 已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from auth import router as auth_router
from servers import router as servers_router
from tasks import router as tasks_router
from log_streamer import router as ws_router
from evaluations import router as eval_router
from admin import router as admin_router

app.include_router(auth_router)
app.include_router(servers_router)
app.include_router(tasks_router)
app.include_router(ws_router)
app.include_router(eval_router)
app.include_router(admin_router)


@app.get("/")
async def root():
    """健康检查"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/api/health")
async def health_check():
    """详细健康检查"""
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "database": db_status,
        "version": settings.APP_VERSION,
    }


async def _init_default_configs():
    """初始化默认外部服务配置项 [FR-014]"""
    default_configs = [
        ("ones_api_gateway", settings.ONES_API_GATEWAY, False, "ONES API 网关地址"),
        ("ones_api_base_url", settings.ONES_API_BASE_URL, False, "ONES 原生 API 地址"),
        ("gerrit_host_1", settings.GERRIT_HOST_1, False, "Gerrit 实例 1 地址"),
        ("gerrit_token_1", settings.GERRIT_TOKEN_1, True, "Gerrit 实例 1 HTTP Token"),
        ("gerrit_user_1", settings.GERRIT_USER_1, True, "Gerrit 实例 1 账号"),
        ("gerrit_pass_1", settings.GERRIT_PASS_1, True, "Gerrit 实例 1 密码"),
        ("gerrit_host_2", settings.GERRIT_HOST_2, False, "Gerrit 实例 2 地址"),
        ("gerrit_token_2", settings.GERRIT_TOKEN_2, True, "Gerrit 实例 2 HTTP Token"),
        ("gerrit_user_2", settings.GERRIT_USER_2, True, "Gerrit 实例 2 账号"),
        ("gerrit_pass_2", settings.GERRIT_PASS_2, True, "Gerrit 实例 2 密码"),
        ("gerrit_host_3", settings.GERRIT_HOST_3, False, "Gerrit 实例 3 地址"),
        ("gerrit_token_3", settings.GERRIT_TOKEN_3, True, "Gerrit 实例 3 HTTP Token"),
        ("gerrit_user_3", settings.GERRIT_USER_3, True, "Gerrit 实例 3 账号"),
        ("gerrit_pass_3", settings.GERRIT_PASS_3, True, "Gerrit 实例 3 密码"),
        ("wecom_corp_id", settings.WECOM_CORP_ID, False, "企业微信 Corp ID"),
        ("wecom_agent_id", str(settings.WECOM_AGENT_ID), False, "企业微信 Agent ID"),
        ("wecom_secret", settings.WECOM_SECRET, True, "企业微信 Secret"),
        ("wecom_webhook_url", settings.WECOM_WEBHOOK_URL, False, "企业微信 Webhook URL"),
    ]

    pool = await get_pool()
    async with pool.acquire() as conn:
        for key, value, encrypted, desc in default_configs:
            await conn.execute("""
                INSERT INTO external_configs (config_key, config_value, is_encrypted, description)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (config_key) DO NOTHING
            """, key, value, encrypted, desc)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
    )
