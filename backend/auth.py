# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — JWT 认证模块
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §4.1 认证模块, §4.2 安全模块
关联需求: FR-001 (用户认证)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from config import settings
from database import get_pool
from ones_client import verify_ones_login, OnesClientError

logger = logging.getLogger("ones-ai.auth")
router = APIRouter(prefix="/api/auth", tags=["认证"])
security = HTTPBearer()


# ---- Pydantic 模型 ----

class LoginRequest(BaseModel):
    email: str
    password: str


class UserInfo(BaseModel):
    id: int
    ones_email: str
    display_name: str
    role: str


class TokenResponse(BaseModel):
    token: str
    user: UserInfo


# ---- JWT 工具函数 ----

def create_token(user_id: int, email: str, role: str) -> str:
    """生成 JWT Token"""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码 JWT Token"""
    try:
        return jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )


# ---- 依赖注入 ----

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserInfo:
    """FastAPI 依赖: 获取当前登录用户"""
    payload = decode_token(credentials.credentials)
    user_id = int(payload.get("sub", 0))
    if not user_id:
        raise HTTPException(status_code=401, detail="Token 无效")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, ones_email, display_name, role FROM users WHERE id=$1 AND is_active=TRUE",
            user_id,
        )
        if not row:
            raise HTTPException(status_code=401, detail="用户不存在或已禁用")
        return UserInfo(
            id=row["id"],
            ones_email=row["ones_email"],
            display_name=row["display_name"],
            role=row["role"],
        )


async def require_admin(user: UserInfo = Depends(get_current_user)) -> UserInfo:
    """FastAPI 依赖: 要求管理员权限"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ---- API 端点 ----

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """
    用户登录 — 使用 ONES 邮箱 + 密码
    1. 调用 ONES API 验证
    2. 查找/创建本地用户
    3. 生成 JWT 返回
    """
    # 1. ONES 验证
    try:
        ones_user = await verify_ones_login(req.email, req.password)
    except OnesClientError as e:
        raise HTTPException(status_code=401, detail=f"登录失败: {e.message}")

    # 2. 查找或创建本地用户
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, ones_email, display_name, role FROM users WHERE ones_email=$1",
            req.email,
        )
        if row:
            user_id = row["id"]
            display_name = row["display_name"] or ones_user.get("name", "")
            role = row["role"]
            # 更新 display_name 和 last_login
            await conn.execute(
                "UPDATE users SET display_name=$1, last_login_at=NOW(), updated_at=NOW() WHERE id=$2",
                ones_user.get("name", display_name),
                user_id,
            )
        else:
            # 新用户
            display_name = ones_user.get("name", "")
            user_id = await conn.fetchval(
                """INSERT INTO users (ones_email, display_name, role, last_login_at)
                   VALUES ($1, $2, 'user', NOW()) RETURNING id""",
                req.email,
                display_name,
            )
            role = "user"

    # 3. 生成 Token
    token = create_token(user_id, req.email, role)
    logger.info(f"用户登录成功: {req.email} (id={user_id})")

    return TokenResponse(
        token=token,
        user=UserInfo(
            id=user_id,
            ones_email=req.email,
            display_name=display_name,
            role=role,
        ),
    )


@router.get("/me", response_model=UserInfo)
async def get_me(user: UserInfo = Depends(get_current_user)):
    """获取当前用户信息"""
    return user
