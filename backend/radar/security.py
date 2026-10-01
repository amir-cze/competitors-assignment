from __future__ import annotations

import base64
import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, URLSafeTimedSerializer

from radar.config import get_settings

SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14 days


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if settings.encryption_key:
        return Fernet(settings.encryption_key.encode())
    derived = hashlib.sha256(f"radar-encryption:{settings.session_secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def mask_secret(value: str | None, keep: int = 6) -> str | None:
    if not value:
        return None
    return f"{value[:keep]}…{value[-4:]}" if len(value) > keep + 4 else "•" * len(value)


@lru_cache
def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="radar-session")


def sign_session(role: str) -> str:
    return _serializer().dumps({"role": role})


def read_session(token: str | None) -> str | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
    return data.get("role")


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
