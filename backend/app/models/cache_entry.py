from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CacheEntry(Base):
    """Index of Parquet files persisted by the data layer.

    `key` is a deterministic string built from the fetch parameters (e.g.
    "batting_stats:2024" or "statcast_pitcher:660271:2024"). `path` is the
    on-disk Parquet location relative to the cache root.
    """

    __tablename__ = "cache_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    path: Mapped[str] = mapped_column(String(1024))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_cache_entries_fetched_at", "fetched_at"),
    )
