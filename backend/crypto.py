# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — AES-256-GCM 加密工具
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §4.2 安全模块
关联需求: FR-003, NFR-001
复用来源: lango-remote/backend/crypto.py
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import settings


def _get_key() -> bytes:
    """获取 AES 密钥（32 字节）"""
    key_hex = settings.CRYPTO_KEY
    if len(key_hex) == 32:
        return key_hex.encode("utf-8")
    elif len(key_hex) == 64:
        return bytes.fromhex(key_hex)
    else:
        raise ValueError(
            f"CRYPTO_KEY 长度错误（期望 32 字符或 64 hex），当前: {len(key_hex)}"
        )


def encrypt_password(plain_text: str) -> str:
    """
    AES-256-GCM 加密密码
    Returns: base64 编码的 "nonce:ciphertext" 字符串
    """
    if not plain_text:
        return ""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce
    ciphertext = aesgcm.encrypt(nonce, plain_text.encode("utf-8"), None)
    combined = nonce + ciphertext
    return base64.b64encode(combined).decode("utf-8")


def decrypt_password(encrypted: str) -> str:
    """
    AES-256-GCM 解密密码
    Input: base64 编码的 "nonce+ciphertext" 字符串
    """
    if not encrypted:
        return ""
    key = _get_key()
    aesgcm = AESGCM(key)
    combined = base64.b64decode(encrypted)
    nonce = combined[:12]
    ciphertext = combined[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
