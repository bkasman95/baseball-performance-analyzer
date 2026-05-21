"""Saved-analysis routes — stubs (Phase 5).

Will store per-user references to (player, season, generated_at) so the
small group of users can curate a set of interesting findings.
"""

from fastapi import APIRouter, HTTPException, status


router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.get("")
def list_saved() -> dict:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="saved analyses arrive in Phase 5 (depends on auth)",
    )


@router.post("/save")
def save_analysis() -> dict:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="saved analyses arrive in Phase 5 (depends on auth)",
    )
