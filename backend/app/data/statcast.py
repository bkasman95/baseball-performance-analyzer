"""Pitch-level Statcast data, per player + season.

Cached per (player, season). Statcast data is mutable — prior seasons can be
revised — so callers may pass `force_refresh=True` to bypass the cache.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

import pandas as pd

from app.data.cache import read_through_cache
from app.data.pybaseball_setup import setup_pybaseball
from app.data.retry import with_retry, classify_pybaseball_error


log = logging.getLogger(__name__)

Role = Literal["pitcher", "hitter"]


def _season_window(season: int) -> tuple[str, str]:
    # MLB regular season runs roughly Mar -> Oct. Pull a wide window so we catch
    # spring carryover and playoff games; pybaseball will return what exists.
    return f"{season}-03-01", f"{season}-11-30"


@with_retry
def _fetch_statcast_pitcher(mlbam_id: int, start: str, end: str) -> pd.DataFrame:
    setup_pybaseball()
    from pybaseball import statcast_pitcher

    try:
        return statcast_pitcher(start, end, mlbam_id)
    except Exception as e:
        raise classify_pybaseball_error(e) from e


@with_retry
def _fetch_statcast_batter(mlbam_id: int, start: str, end: str) -> pd.DataFrame:
    setup_pybaseball()
    from pybaseball import statcast_batter

    try:
        return statcast_batter(start, end, mlbam_id)
    except Exception as e:
        raise classify_pybaseball_error(e) from e


def get_statcast(
    mlbam_id: int,
    role: Role,
    season: int,
    *,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return pitch-level Statcast data for a player's season."""
    start, end = _season_window(season)
    key = f"statcast_{role}:{mlbam_id}:{season}"
    fetch = _fetch_statcast_pitcher if role == "pitcher" else _fetch_statcast_batter
    return read_through_cache(key, lambda: fetch(mlbam_id, start, end), force_refresh=force_refresh)


def get_statcast_range(
    mlbam_id: int,
    role: Role,
    start: date | str,
    end: date | str,
    *,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Statcast for an arbitrary date range. Not cached per-call (use sparingly)."""
    s = start.isoformat() if isinstance(start, date) else start
    e = end.isoformat() if isinstance(end, date) else end
    key = f"statcast_{role}:{mlbam_id}:range:{s}_{e}"
    fetch = _fetch_statcast_pitcher if role == "pitcher" else _fetch_statcast_batter
    return read_through_cache(key, lambda: fetch(mlbam_id, s, e), force_refresh=force_refresh)
