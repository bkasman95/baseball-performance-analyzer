"""Auth routes.

  POST /api/auth/login    — OAuth2 password form, returns a Bearer JWT
  POST /api/auth/logout   — client-side discard (stateless tokens); 200 OK
  GET  /api/auth/me       — returns the current user's profile
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.jwt import create_access_token
from app.auth.passwords import verify_password
from app.db import get_db
from app.models.user import User


router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: "UserView"


class UserView(BaseModel):
    id: int
    email: str
    display_name: str | None = None


TokenResponse.model_rebuild()


@router.post("/login", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """OAuth2 password flow.

    The standard OAuth2PasswordRequestForm reads `username` and `password`
    fields. We treat `username` as the email so the spec's "email + password"
    UX works without a custom schema.
    """
    email = form.username.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(form.password, user.password_hash):
        # Deliberately vague — don't leak whether the email exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, exp = create_access_token(user_id=user.id)
    return TokenResponse(
        access_token=token,
        expires_at=exp.isoformat(),
        user=UserView(id=user.id, email=user.email, display_name=user.display_name),
    )


@router.post("/logout")
def logout(_: User = Depends(get_current_user)) -> dict:
    """Stateless logout — the client just discards its token.

    Returns 200 so clients can wire a "logged out" UI; protected so an
    unauthenticated caller doesn't get a misleading success.
    """
    return {"status": "logged_out"}


@router.get("/me", response_model=UserView)
def me(user: User = Depends(get_current_user)) -> UserView:
    return UserView(id=user.id, email=user.email, display_name=user.display_name)
