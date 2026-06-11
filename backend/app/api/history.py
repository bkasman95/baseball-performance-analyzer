"""User-facing analysis history endpoint.

  GET /api/me/history?limit=50&offset=0  — list this user's queries, newest first
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.analysis_history import AnalysisHistory
from app.models.user import User


router = APIRouter(prefix="/me", tags=["me"])


class HistoryRow(BaseModel):
    id: int
    player_id: int
    player_name: str | None
    season: int
    status: str
    cache_hit: bool
    job_id: str | None
    created_at: str
    completed_at: str | None
    duration_ms: int | None
    response_size_bytes: int | None
    error: str | None


class HistoryResponse(BaseModel):
    rows: list[HistoryRow]
    total: int
    limit: int
    offset: int


# A `running` row older than this is almost certainly a job that died with
# the API process; we surface it as `stale` so the UI can render it greyed.
_STALE_AFTER = timedelta(minutes=30)


def _view(r: AnalysisHistory) -> HistoryRow:
    status = r.status
    if status == "running" and (datetime.utcnow() - r.created_at) > _STALE_AFTER:
        status = "stale"
    return HistoryRow(
        id=r.id,
        player_id=r.player_id,
        player_name=r.player_name,
        season=r.season,
        status=status,
        cache_hit=r.cache_hit,
        job_id=r.job_id,
        created_at=r.created_at.isoformat() + "Z",
        completed_at=(r.completed_at.isoformat() + "Z") if r.completed_at else None,
        duration_ms=r.duration_ms,
        response_size_bytes=r.response_size_bytes,
        error=r.error,
    )


@router.get("/history", response_model=HistoryResponse)
def list_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HistoryResponse:
    total = db.execute(
        select(func.count(AnalysisHistory.id)).where(AnalysisHistory.user_id == user.id)
    ).scalar_one()
    rows = db.execute(
        select(AnalysisHistory)
        .where(AnalysisHistory.user_id == user.id)
        .order_by(AnalysisHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return HistoryResponse(
        rows=[_view(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )
