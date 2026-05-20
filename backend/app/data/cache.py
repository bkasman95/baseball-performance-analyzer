"""Parquet cache + Postgres index for baseball data pulls.

Every fetch from pybaseball/Savant goes through `read_through_cache`. The
on-disk file is the source of truth for the data; the Postgres `cache_entries`
row is just an index for "what do we have and when was it fetched."
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models.cache_entry import CacheEntry


log = logging.getLogger(__name__)

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(key: str) -> str:
    # Keep keys human-readable on disk, hash collisions away with a short suffix.
    base = _SAFE.sub("_", key)[:120]
    digest = hashlib.sha1(key.encode()).hexdigest()[:8]
    return f"{base}__{digest}.parquet"


def cache_root() -> Path:
    root = Path(get_settings().cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path_for(key: str) -> Path:
    return cache_root() / _safe_filename(key)


def cache_lookup(key: str) -> Path | None:
    with SessionLocal() as db:
        entry = db.execute(select(CacheEntry).where(CacheEntry.key == key)).scalar_one_or_none()
        if entry is None:
            return None
        path = Path(entry.path)
        return path if path.exists() else None


def cache_write(key: str, df: pd.DataFrame) -> Path:
    path = _path_for(key)
    df.to_parquet(path, index=False)
    with SessionLocal() as db:
        existing = db.execute(select(CacheEntry).where(CacheEntry.key == key)).scalar_one_or_none()
        if existing is None:
            db.add(CacheEntry(key=key, path=str(path), row_count=len(df), fetched_at=datetime.utcnow()))
        else:
            existing.path = str(path)
            existing.row_count = len(df)
            existing.fetched_at = datetime.utcnow()
        db.commit()
    return path


def read_through_cache(
    key: str,
    fetch: Callable[[], pd.DataFrame],
    *,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return a DataFrame for `key`, fetching+persisting on cache miss."""
    if not force_refresh:
        path = cache_lookup(key)
        if path is not None:
            try:
                log.debug("cache hit: %s -> %s", key, path)
                return pd.read_parquet(path)
            except Exception as e:
                log.warning("cache read failed for %s, refetching: %s", key, e)

    log.info("cache miss: fetching %s", key)
    df = fetch()
    if df is None:
        df = pd.DataFrame()
    cache_write(key, df)
    return df


def invalidate(key_prefix: str) -> int:
    """Delete cache entries whose key starts with `key_prefix`. Returns count."""
    removed = 0
    with SessionLocal() as db:
        rows = db.execute(select(CacheEntry).where(CacheEntry.key.like(f"{key_prefix}%"))).scalars().all()
        for r in rows:
            try:
                os.remove(r.path)
            except FileNotFoundError:
                pass
            db.delete(r)
            removed += 1
        db.commit()
    return removed
