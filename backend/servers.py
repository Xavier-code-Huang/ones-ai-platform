# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 服务器管理 API
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §4.3 服务器管理模块
关联需求: FR-002, FR-003
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user, require_admin, UserInfo
from crypto import encrypt_password, decrypt_password
from database import get_pool
from ssh_pool import verify_ssh_credential

logger = logging.getLogger("ones-ai.servers")
router = APIRouter(prefix="/api/servers", tags=["服务器管理"])


# ---- Pydantic 模型 ----

class ServerInfo(BaseModel):
    id: int
    name: str
    host: str
    ssh_port: int
    description: str
    status: str
    has_ones_ai: bool
    credential_count: int = 0
    has_my_credential: bool = False


class CredentialInfo(BaseModel):
    id: int
    ssh_username: str
    alias: str
    is_verified: bool
    verified_at: Optional[str] = None


class VerifyCredentialRequest(BaseModel):
    ssh_username: str
    ssh_password: str
    alias: str = ""


class AddServerRequest(BaseModel):
    name: str
    host: str
    ssh_port: int = 22
    description: str = ""


# ---- API 端点 ----

@router.get("", response_model=list[ServerInfo])
async def list_servers(user: UserInfo = Depends(get_current_user)):
    """获取所有服务器列表（含当前用户凭证状态）[FR-002]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT s.*,
                   COALESCE(c.cred_count, 0) as credential_count,
                   COALESCE(mc.my_count, 0) > 0 as has_my_credential
            FROM servers s
            LEFT JOIN (
                SELECT server_id, COUNT(*) as cred_count
                FROM user_server_credentials
                GROUP BY server_id
            ) c ON c.server_id = s.id
            LEFT JOIN (
                SELECT server_id, COUNT(*) as my_count
                FROM user_server_credentials
                WHERE user_id = $1 AND is_verified = TRUE
                GROUP BY server_id
            ) mc ON mc.server_id = s.id
            ORDER BY s.name
        """, user.id)

    return [
        ServerInfo(
            id=r["id"],
            name=r["name"],
            host=r["host"],
            ssh_port=r["ssh_port"],
            description=r["description"] or "",
            status=r["status"],
            has_ones_ai=r["has_ones_ai"],
            credential_count=r["credential_count"],
            has_my_credential=r["has_my_credential"],
        )
        for r in rows
    ]


@router.post("/{server_id}/verify")
async def verify_credential(
    server_id: int,
    req: VerifyCredentialRequest,
    user: UserInfo = Depends(get_current_user),
):
    """验证并绑定 SSH 凭证 [FR-003]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        server = await conn.fetchrow("SELECT * FROM servers WHERE id=$1", server_id)
        if not server:
            raise HTTPException(status_code=404, detail="服务器不存在")

        # SSH 验证
        result = await verify_ssh_credential(
            server["host"], server["ssh_port"], req.ssh_username, req.ssh_password
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])

        # 凭证加密存储
        encrypted_pw = encrypt_password(req.ssh_password)
        await conn.execute("""
            INSERT INTO user_server_credentials
                (user_id, server_id, ssh_username, ssh_password_encrypted, is_verified, verified_at, alias)
            VALUES ($1, $2, $3, $4, TRUE, NOW(), $5)
        """, user.id, server_id, req.ssh_username, encrypted_pw, req.alias)

        # 更新服务器 ones-AI 状态
        if result.get("has_ones_ai") is not None:
            await conn.execute(
                "UPDATE servers SET has_ones_ai=$1, status='online', last_health_at=NOW() WHERE id=$2",
                result["has_ones_ai"], server_id,
            )

    return {"success": True, "message": result["message"], "has_ones_ai": result.get("has_ones_ai", False)}


@router.get("/{server_id}/credentials", response_model=list[CredentialInfo])
async def list_credentials(
    server_id: int,
    user: UserInfo = Depends(get_current_user),
):
    """获取当前用户在此服务器的凭证列表 [FR-003]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, ssh_username, alias, is_verified, verified_at
            FROM user_server_credentials
            WHERE user_id=$1 AND server_id=$2
            ORDER BY created_at
        """, user.id, server_id)

    return [
        CredentialInfo(
            id=r["id"],
            ssh_username=r["ssh_username"],
            alias=r["alias"] or "",
            is_verified=r["is_verified"],
            verified_at=str(r["verified_at"]) if r["verified_at"] else None,
        )
        for r in rows
    ]


@router.delete("/{server_id}/credentials/{cred_id}")
async def delete_credential(
    server_id: int,
    cred_id: int,
    user: UserInfo = Depends(get_current_user),
):
    """删除凭证 [FR-003]"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM user_server_credentials WHERE id=$1 AND user_id=$2 AND server_id=$3",
            cred_id, user.id, server_id,
        )
    return {"success": True}


@router.post("", response_model=ServerInfo)
async def add_server(req: AddServerRequest, user: UserInfo = Depends(require_admin)):
    """添加服务器（管理员）"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO servers (name, host, ssh_port, description)
            VALUES ($1, $2, $3, $4) RETURNING *
        """, req.name, req.host, req.ssh_port, req.description)

    return ServerInfo(
        id=row["id"], name=row["name"], host=row["host"],
        ssh_port=row["ssh_port"], description=row["description"] or "",
        status=row["status"], has_ones_ai=row["has_ones_ai"],
    )


@router.post("/{server_id}/health")
async def check_health(server_id: int, user: UserInfo = Depends(get_current_user)):
    """手动触发服务器健康检查"""
    import asyncio
    import asyncssh

    pool = await get_pool()
    async with pool.acquire() as conn:
        server = await conn.fetchrow("SELECT * FROM servers WHERE id=$1", server_id)
        if not server:
            raise HTTPException(status_code=404, detail="服务器不存在")

        try:
            conn_ssh = await asyncio.wait_for(
                asyncssh.connect(server["host"], port=server["ssh_port"], known_hosts=None,
                                 username="root", password=""),
                timeout=5,
            )
            status_val = "online"
            conn_ssh.close()
        except Exception:
            # 无法匿名连接但端口可达也算 online
            import socket
            try:
                s = socket.create_connection((server["host"], server["ssh_port"]), timeout=5)
                s.close()
                status_val = "online"
            except Exception:
                status_val = "offline"

        await conn.execute(
            "UPDATE servers SET status=$1, last_health_at=NOW() WHERE id=$2",
            status_val, server_id,
        )

    return {"status": status_val}
