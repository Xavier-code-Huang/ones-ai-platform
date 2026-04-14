# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — ONES 系统 API 客户端
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §4.1 认证模块
关联需求: FR-001 (ONES 账号登录)
"""

import logging
import httpx

from config import settings

logger = logging.getLogger("ones-ai.ones")


class OnesClientError(Exception):
    """ONES API 错误"""
    def __init__(self, message: str, code: int = 0):
        self.message = message
        self.code = code
        super().__init__(message)


async def verify_ones_login(email: str, password: str) -> dict:
    """
    通过 ONES 原生 API 验证用户账号密码。

    Returns:
        { "uuid": "...", "token": "...", "name": "..." }

    Raises:
        OnesClientError: 登录失败
    """
    login_url = f"{settings.ONES_API_BASE_URL}/project/api/project/auth/login"
    logger.info(f"ONES 登录验证: email={email}")

    try:
        async with httpx.AsyncClient(verify=False, timeout=8) as client:
            resp = await client.post(
                login_url,
                json={"email": email, "password": password},
                headers={"Content-Type": "application/json; charset=utf-8"},
            )

            if resp.status_code == 200:
                data = resp.json()
                user = data.get("user", {})
                if user.get("uuid"):
                    logger.info(f"ONES 登录成功: {user.get('name', email)}")
                    return {
                        "uuid": user["uuid"],
                        "token": user.get("token", ""),
                        "name": user.get("name", ""),
                    }
                else:
                    raise OnesClientError("ONES 返回数据异常: 缺少 user.uuid")
            elif resp.status_code == 401:
                raise OnesClientError("账号密码错误", code=401)
            elif resp.status_code == 404:
                raise OnesClientError("账号不存在", code=404)
            else:
                raise OnesClientError(
                    f"ONES API 错误: HTTP {resp.status_code}", code=resp.status_code
                )
    except httpx.TimeoutException:
        raise OnesClientError("ONES API 请求超时")
    except httpx.ConnectError:
        raise OnesClientError("无法连接 ONES 服务")


async def query_tickets(numbers: list[int]) -> list[dict]:
    """
    通过 ONES API 网关查询工单列表 [FR-014 使用网关]

    Args:
        numbers: 工单编号列表

    Returns:
        工单信息列表
    """
    url = f"{settings.ONES_API_GATEWAY}/api/ones/v3/ones/task/list"
    logger.info(f"查询工单: numbers={numbers}")

    try:
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            resp = await client.post(
                url,
                json={"numbers": numbers, "limit": 200},
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", [])
            else:
                logger.warning(f"查询工单失败: HTTP {resp.status_code}")
                return []
    except Exception as e:
        logger.warning(f"查询工单异常: {e}")
        return []


