# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — Gerrit REST API 客户端
@Version: 1.0.0
@Date: 2026-03-30

用于从 Gerrit 获取代码提交信息，支持准确度评测系统。
"""

import asyncio
import aiohttp
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ones-ai.gerrit")


@dataclass
class GerritChange:
    """Gerrit Change 数据模型"""
    change_id: str = ""
    number: int = 0
    project: str = ""
    branch: str = ""
    subject: str = ""
    status: str = ""
    insertions: int = 0
    deletions: int = 0
    created: str = ""
    updated: str = ""
    submitted: str = ""
    owner_id: int = 0
    current_revision: str = ""
    files: dict = field(default_factory=dict)        # {path: {lines_inserted, lines_deleted, ...}}
    commit_message: str = ""
    commit_author: str = ""
    diff_content: str = ""                            # 完整 patch 文本


@dataclass
class GerritConfig:
    """Gerrit 实例配置"""
    name: str
    base_url: str
    username: str
    password: str   # HTTP Token 或 HTTP 密码


# 预定义的 Gerrit 实例
GERRIT_INSTANCES = [
    GerritConfig(
        name="Gerrit-182",
        base_url="http://192.168.1.182:8081",
        username="huangyixiang",
        password="Mlj3rOox8fMHcVtmfGn2gAqzEdOAgApyGEeSVqltqw",
    ),
    # 194 暂不可用（Apache 反代 /a/ 路径 404）
    # GerritConfig(
    #     name="Gerrit-194",
    #     base_url="http://192.168.1.194:8092",
    #     username="huangyixiang",
    #     password="nRKgzhPhL5XWqlzLlAN7ZFsqfXDW1WXWnSy3MnVbFw",
    # ),
]


class GerritClient:
    """
    Gerrit REST API 客户端（异步）

    支持:
    - 按工单号搜索关联的 Change
    - 获取 Change 的文件列表
    - 获取 Change 的 diff/patch
    """

    def __init__(self, config: GerritConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.auth = aiohttp.BasicAuth(config.username, config.password)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(
                auth=self.auth,
                timeout=timeout,
                headers={"Accept": "application/json"},
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get(self, path: str, params: dict = None) -> any:
        """发起 GET 请求，自动处理 Gerrit XSSI 前缀"""
        session = await self._get_session()
        url = f"{self.base_url}/a{path}"
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(f"Gerrit {url} -> {resp.status}: {text[:200]}")
                    return None
                text = await resp.text()
                # 去掉 Gerrit v3 的 XSSI 前缀 )]}'
                if text.startswith(")]}'"):
                    text = text[4:].strip()
                return json.loads(text)
        except asyncio.TimeoutError:
            logger.warning(f"Gerrit {url} 超时")
            return None
        except Exception as e:
            logger.error(f"Gerrit {url} 异常: {e}")
            return None

    async def search_by_ticket(self, ticket_id: str, limit: int = 5) -> list[GerritChange]:
        """
        通过 ONES 工单号搜索关联的 Gerrit Change

        工单号映射: ONES-670582 -> 在 Gerrit 中以 STORY-670582 / BUG-670582 出现
        搜索策略: 用纯数字部分做 message 搜索
        """
        # 提取纯数字部分
        num = re.sub(r"^ONES-", "", ticket_id)

        data = await self._get("/changes/", params={
            "q": f"message:{num}",
            "n": str(limit),
            "o": ["CURRENT_REVISION", "CURRENT_FILES", "CURRENT_COMMIT"],
        })

        if not data:
            return []

        changes = []
        for item in data:
            c = GerritChange(
                change_id=item.get("change_id", ""),
                number=item.get("_number", 0),
                project=item.get("project", ""),
                branch=item.get("branch", ""),
                subject=item.get("subject", ""),
                status=item.get("status", ""),
                insertions=item.get("insertions", 0),
                deletions=item.get("deletions", 0),
                created=item.get("created", ""),
                updated=item.get("updated", ""),
                submitted=item.get("submitted", ""),
                owner_id=item.get("owner", {}).get("_account_id", 0),
                current_revision=item.get("current_revision", ""),
            )

            # 提取文件列表
            revisions = item.get("revisions", {})
            if c.current_revision and c.current_revision in revisions:
                rev = revisions[c.current_revision]
                c.files = rev.get("files", {})
                # 提取 commit message
                commit_info = rev.get("commit", {})
                c.commit_message = commit_info.get("message", "")
                c.commit_author = commit_info.get("author", {}).get("name", "")

            changes.append(c)

        return changes

    async def get_patch(self, change_number: int) -> str:
        """获取 Change 的完整 patch (base64 encoded)"""
        session = await self._get_session()
        url = f"{self.base_url}/a/changes/{change_number}/revisions/current/patch"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return ""
                import base64
                text = await resp.text()
                # patch 返回 base64 编码
                if text.startswith(")]}'"):
                    text = text[4:].strip()
                try:
                    return base64.b64decode(text).decode("utf-8", errors="replace")
                except Exception:
                    return text
        except Exception as e:
            logger.error(f"获取 patch 失败: {e}")
            return ""

    async def get_file_diff(self, change_number: int, file_path: str) -> str:
        """获取单个文件的 diff"""
        import urllib.parse
        encoded_path = urllib.parse.quote(file_path, safe="")
        data = await self._get(f"/changes/{change_number}/revisions/current/files/{encoded_path}/diff")
        if not data:
            return ""
        # 拼接 diff 文本
        lines = []
        for section in data.get("content", []):
            if "ab" in section:  # 未修改行
                pass
            if "a" in section:   # 删除行
                for line in section["a"]:
                    lines.append(f"- {line}")
            if "b" in section:   # 新增行
                for line in section["b"]:
                    lines.append(f"+ {line}")
        return "\n".join(lines)


async def search_all_instances(ticket_id: str) -> list[GerritChange]:
    """在所有 Gerrit 实例中搜索工单"""
    all_changes = []
    for config in GERRIT_INSTANCES:
        client = GerritClient(config)
        try:
            changes = await client.search_by_ticket(ticket_id)
            for c in changes:
                c.diff_content = f"[{config.name}]"  # 标记来源
            all_changes.extend(changes)
        except Exception as e:
            logger.warning(f"{config.name} 搜索失败: {e}")
        finally:
            await client.close()
    return all_changes
