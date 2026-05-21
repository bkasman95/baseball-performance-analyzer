"""JWT encode / decode for session tokens.

Tokens carry `sub` (the user id as a string) and `exp`. Anything else the
caller wants to stash goes into `extra` — kept minimal so token size stays
small and PII doesn't leak into logs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.config import get_settings


class InvalidTokenError(Exception):
    pass


def create_access_token(*, user_id: int, extra: dict[str, Any] | None = None) -> tuple[str, datetime]:
    """Return (token, expires_at_utc)."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, exp


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise InvalidTokenError(str(e)) from e
