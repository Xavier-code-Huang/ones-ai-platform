# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — SSH 连接池
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §4.3 服务器管理模块
关联需求: FR-003, FR-005
复用来源: lango-remote/backend/ssh_pool.py
"""

import asyncio
import logging
from typing import Optional

import asyncssh

from config import settings

logger = logging.getLogger("ones-ai.ssh")

# 连接池缓存: key = "host:port:username"
_connections: dict[str, asyncssh.SSHClientConnection] = {}
_lock = asyncio.Lock()


def _make_key(host: str, port: int, username: str) -> str:
    return f"{host}:{port}:{username}"


async def get_ssh_connection(
    host: str,
    port: int,
    username: str,
    password: str,
) -> asyncssh.SSHClientConnection:
    """获取或创建 SSH 连接"""
    key = _make_key(host, port, username)
    async with _lock:
        conn = _connections.get(key)
        if conn and _is_alive(conn):
            return conn

        # 创建新连接
        try:
            conn = await asyncio.wait_for(
                asyncssh.connect(
                    host,
                    port=port,
                    username=username,
                    password=password,
                    known_hosts=None,
                ),
                timeout=settings.SSH_CONNECT_TIMEOUT,
            )
            _connections[key] = conn
            logger.info(f"SSH 连接已建立: {username}@{host}:{port}")
            return conn
        except asyncio.TimeoutError:
            raise ConnectionError(f"SSH 连接超时: {host}:{port}")
        except asyncssh.PermissionDenied:
            raise PermissionError(f"SSH 认证失败: {username}@{host}:{port}")
        except Exception as e:
            raise ConnectionError(f"SSH 连接失败: {e}")


async def verify_ssh_credential(
    host: str, port: int, username: str, password: str
) -> dict:
    """
    验证 SSH 凭证有效性

    Returns:
        {"success": True, "has_ones_ai": bool, "message": str}
    """
    try:
        conn = await get_ssh_connection(host, port, username, password)
        # 测试连接
        result = await conn.run("echo ok", timeout=5)
        if result.stdout.strip() != "ok":
            return {"success": False, "has_ones_ai": False, "message": "连接测试失败"}

        # 检查 ones_task_runner 是否可用
        check = await conn.run(
            "test -f /opt/lango/ones_task_runner/ones_task_runner.py && echo yes || echo no",
            timeout=5,
        )
        has_ones_ai = check.stdout.strip() == "yes"

        return {
            "success": True,
            "has_ones_ai": has_ones_ai,
            "message": "验证成功" + ("" if has_ones_ai else " (ones-AI 未安装)"),
        }
    except PermissionError:
        return {"success": False, "has_ones_ai": False, "message": "账号密码错误"}
    except ConnectionError as e:
        return {"success": False, "has_ones_ai": False, "message": str(e)}
    except Exception as e:
        return {"success": False, "has_ones_ai": False, "message": f"验证失败: {e}"}


def _is_alive(conn: asyncssh.SSHClientConnection) -> bool:
    """检查 SSH 连接是否存活（兼容不同版本 asyncssh）"""
    try:
        if hasattr(conn, 'is_closed'):
            return not conn.is_closed()
        # 旧版 asyncssh 没有 is_closed，检查内部属性
        if hasattr(conn, '_transport'):
            return conn._transport is not None and not conn._transport.is_closing()
        return True  # 无法判断，假设存活
    except Exception:
        return False


async def close_all_connections():
    """关闭所有 SSH 连接"""
    async with _lock:
        for key, conn in _connections.items():
            try:
                conn.close()
            except Exception:
                pass
        _connections.clear()
        logger.info("所有 SSH 连接已关闭")
