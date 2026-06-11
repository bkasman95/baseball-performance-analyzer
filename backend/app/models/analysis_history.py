"""Per-user analysis history.

One row is inserted every time a user hits `GET /api/players/{id}/analysis`.
The row records request metadata (player, season, timestamp), correlates to
the underlying job, and gets updated to "complete" / "failed" with timing
and payload size once the job finishes.

Distinct from `saved_analyses`: that's a user-curated bookmark list. This
table is an audit log of every query, including ones the user never saved.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AnalysisHistory(Base):
    __tablename__ = "analysis_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    player_id: Mapped[int] = mapped_column(Integer, index=True)
    player_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    season: Mapped[int] = mapped_column(Integer)
    # "running" | "complete" | "failed". `running` rows get patched when the
    # underlying job finishes; if the API process restarts mid-job, they stay
    # `running` forever — the list endpoint flags those as stale on read.
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
