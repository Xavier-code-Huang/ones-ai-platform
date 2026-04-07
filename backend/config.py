# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 配置管理
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §6.2 环境变量
关联需求: NFR-004 可维护性
"""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置（支持环境变量覆盖）"""

    # ---- 应用 ----
    APP_NAME: str = "ones-AI Platform"
    APP_VERSION: str = "1.0.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 9610
    DEBUG: bool = False

    # ---- 数据库 ----
    DATABASE_URL: str = "postgresql://onesai:onesai123@localhost:5432/ones_ai_platform"
    DB_POOL_MIN: int = 5
    DB_POOL_MAX: int = 20

    # ---- JWT ----
    JWT_SECRET_KEY: str = "ones-ai-platform-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 72

    # ---- 加密 ----
    CRYPTO_KEY: str = "0123456789abcdef0123456789abcdef"  # 32 字符 AES-256 密钥

    # ---- ONES API ----
    ONES_API_GATEWAY: str = "http://172.60.1.103:9006"
    ONES_API_BASE_URL: str = "https://ones.lango-tech.com:7000"

    # ---- SSH ----
    SSH_CONNECT_TIMEOUT: int = 10
    SSH_POOL_MAX_SIZE: int = 50

    # ---- 企微通知 ----
    WECOM_CORP_ID: str = ""
    WECOM_AGENT_ID: int = 0
    WECOM_SECRET: str = ""
    WECOM_WEBHOOK_URL: str = ""

    # ---- 通知开关 ----
    NOTIFY_WEBHOOK_ENABLED: bool = False
    NOTIFY_EMAIL_ENABLED: bool = False

    # ---- SMTP 邮件 ----
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM_NAME: str = "ones-AI"

    # ---- AI 模型 ----
    AI_BASE_URL: str = "https://open.bigmodel.cn/api/anthropic"
    AI_API_KEY: str = ""  # 智谱 API Key，用于 AI 预分析
    AI_SONNET_MODEL: str = "glm-4.7"
    AI_OPUS_MODEL: str = "glm-5.1"

    # Claude Code 容器默认模型映射（runner + 干预容器共用）
    CLAUDE_HAIKU_MODEL: str = "glm-4.7"
    CLAUDE_SONNET_MODEL: str = "glm-5.1"   # Claude Code 默认使用的模型
    CLAUDE_OPUS_MODEL: str = "glm-5.1"

    # ---- Gerrit 占位 (Phase 2) ----
    GERRIT_HOST_1: str = "__GERRIT_HOST_1__"
    GERRIT_TOKEN_1: str = "__GERRIT_TOKEN_1__"
    GERRIT_USER_1: str = "__GERRIT_USER_1__"
    GERRIT_PASS_1: str = "__GERRIT_PASS_1__"
    GERRIT_HOST_2: str = "__GERRIT_HOST_2__"
    GERRIT_TOKEN_2: str = "__GERRIT_TOKEN_2__"
    GERRIT_USER_2: str = "__GERRIT_USER_2__"
    GERRIT_PASS_2: str = "__GERRIT_PASS_2__"
    GERRIT_HOST_3: str = "__GERRIT_HOST_3__"
    GERRIT_TOKEN_3: str = "__GERRIT_TOKEN_3__"
    GERRIT_USER_3: str = "__GERRIT_USER_3__"
    GERRIT_PASS_3: str = "__GERRIT_PASS_3__"

    # ---- 数据路径 ----
    DATA_DIR: Path = Path("data")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
