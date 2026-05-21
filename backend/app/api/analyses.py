"""Saved-analysis endpoints — POST /api/analyses/save, GET /api/analyses."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.saved_analysis import SavedAnalysis
from app.models.user import User


router = APIRouter(prefix="/analyses", tags=["analyses"])


class SaveAnalysisRequest(BaseModel):
    player_id: int
    season: int
    player_name: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=2000)


class SavedAnalysisView(BaseModel):
    id: int
    player_id: int
    season: int
    player_name: str | None = None
    title: str | None = None
    note: str | None = None
    created_at: str


def _view(s: SavedAnalysis) -> SavedAnalysisView:
    return SavedAnalysisView(
        id=s.id,
        player_id=s.player_id,
        season=s.season,
        player_name=s.player_name,
        title=s.title,
        note=s.note,
        created_at=s.created_at.isoformat() + "Z",
    )


@router.get("", response_model=list[SavedAnalysisView])
def list_saved(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavedAnalysisView]:
    rows = db.execute(
        select(SavedAnalysis)
        .where(SavedAnalysis.user_id == user.id)
        .order_by(SavedAnalysis.created_at.desc())
    ).scalars().all()
    return [_view(r) for r in rows]


@router.post("/save", response_model=SavedAnalysisView, status_code=status.HTTP_201_CREATED)
def save(
    body: SaveAnalysisRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedAnalysisView:
    saved = SavedAnalysis(
        user_id=user.id,
        player_id=body.player_id,
        season=body.season,
        player_name=body.player_name,
        title=body.title,
        note=body.note,
        created_at=datetime.utcnow(),
    )
    db.add(saved)
    try:
        db.commit()
    except IntegrityError:
        # Already saved this (player, season) — return the existing row instead
        # of erroring so the UI's "save" button is idempotent.
        db.rollback()
        existing = db.execute(
            select(SavedAnalysis).where(
                SavedAnalysis.user_id == user.id,
                SavedAnalysis.player_id == body.player_id,
                SavedAnalysis.season == body.season,
            )
        ).scalar_one()
        return _view(existing)
    db.refresh(saved)
    return _view(saved)


@router.delete("/{saved_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    saved_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(SavedAnalysis, saved_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="not found")
    db.delete(row)
    db.commit()
