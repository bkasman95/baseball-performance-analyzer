"""FastAPI auth dependency.

Routes that depend on `get_current_user` require a valid Bearer token;
missing or bad tokens yield 401.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.jwt import InvalidTokenError, decode_token
from app.db import get_db
from app.models.user import User


# auto_error=False so we can produce our own 401 with a clear message.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _unauthorized(detail: str = "not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise _unauthorized("missing bearer token")
    try:
        payload = decode_token(token)
    except InvalidTokenError as e:
        raise _unauthorized(f"invalid token: {e}")

    sub = payload.get("sub")
    if not sub:
        raise _unauthorized("malformed token (no sub)")

    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise _unauthorized("malformed token (non-int sub)")

    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized("user no longer exists")
    return user
