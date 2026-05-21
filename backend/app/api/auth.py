"""Auth route stubs.

Real implementation arrives in Phase 5 — JWT issuance, password hashing,
and dependency-based route protection. For now the routes exist so the
frontend can stub against them and 503s are unambiguous.
"""

from fastapi import APIRouter, HTTPException, status


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login() -> dict:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="auth not implemented yet (Phase 5)",
    )


@router.post("/logout")
def logout() -> dict:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="auth not implemented yet (Phase 5)",
    )
