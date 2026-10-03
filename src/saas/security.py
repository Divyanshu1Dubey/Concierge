"""Security primitives: passwords, JWT, secrets, and simple encryption."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from saas.config import get_settings

pwd_ctx = CryptContext(schemes=["argon2"], deprecated="auto")
settings = get_settings()


def hash_password(raw: str) -> str:
    return pwd_ctx.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_ctx.verify(raw, hashed)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes or settings.jwt_expires_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("invalid token") from exc


def redact(text: str | None) -> str:
    if not text:
        return ""
    return text[:4] + "****" if len(text) > 4 else "****"


def _key_bytes() -> bytes:
    raw = settings.encryption_key.get_secret_value()
    return hashlib.sha256(raw.encode()).digest()


def encrypt_value(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    key = _key_bytes()
    nonce = secrets.token_bytes(12)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return f"{nonce.hex()}:{ciphertext.hex()}"


def decrypt_value(token: str | None) -> str | None:
    if not token:
        return None
    key = _key_bytes()
    nonce_hex, cipher_hex = token.split(":", 1)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(bytes.fromhex(nonce_hex), bytes.fromhex(cipher_hex), None)
    return plaintext.decode()
