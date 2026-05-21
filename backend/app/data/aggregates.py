"""Season-level FanGraphs aggregates for hitters and pitchers.

These are the inputs to the year-over-year anomaly layer. One row per
(player, season). pybaseball's `batting_stats` / `pitching_stats` return
~300 columns per row; we cache the full thing per season and filter on read.
"""

from __future__ import annotations

import logging
from typing import Iterable, Literal

import pandas as pd

from app.data.cache import read_through_cache
from app.data.pybaseball_setup import setup_pybaseball
from app.data.retry import with_retry, classify_pybaseball_error


log = logging.getLogger(__name__)

Role = Literal["hitter", "pitcher", "batting", "pitching"]


def _normalize_role(role: Role) -> str:
    return "batting" if role in ("hitter", "batting") else "pitching"


# ---------------------------------------------------------------------------
# League-wide season pulls (cached per season)
# ---------------------------------------------------------------------------

@with_retry
def _fetch_batting(season: int) -> pd.DataFrame:
    setup_pybaseball()
    from pybaseball import batting_stats

    try:
        # qual=0 keeps everyone — we'll apply sample-size guardrails per-player downstream.
        df = batting_stats(season, season, qual=0)
    except Exception as e:
        raise classify_pybaseball_error(e) from e
    return df


@with_retry
def _fetch_pitching(season: int) -> pd.DataFrame:
    setup_pybaseball()
    from pybaseball import pitching_stats

    try:
        df = pitching_stats(season, season, qual=0)
    except Exception as e:
        raise classify_pybaseball_error(e) from e
    return df


def get_league_season(season: int, role: Role, *, force_refresh: bool = False) -> pd.DataFrame:
    r = _normalize_role(role)
    key = f"{r}_stats:{season}"
    fetch = _fetch_batting if r == "batting" else _fetch_pitching
    return read_through_cache(key, lambda: fetch(season), force_refresh=force_refresh)


# ---------------------------------------------------------------------------
# Per-player aggregate slice
# ---------------------------------------------------------------------------

def _id_columns(df: pd.DataFrame) -> list[str]:
    # FanGraphs returns the MLBAM id under a few possible names depending on version.
    candidates = ["IDfg", "IDfg.1", "key_mlbam", "MLBAMID", "mlbamid", "playerid"]
    return [c for c in candidates if c in df.columns]


def _filter_player(df: pd.DataFrame, mlbam_id: int) -> pd.DataFrame:
    # pybaseball joins MLBAM into the FG table when possible. Try several columns.
    for col in ("MLBAMID", "mlbamid", "key_mlbam"):
        if col in df.columns:
            sub = df[df[col].astype("Int64") == mlbam_id]
            if not sub.empty:
                return sub
    # Fallback: filter by name only as a last resort — caller should pass mlbam_id reliably.
    return df.iloc[0:0]


def get_season_aggregates(
    mlbam_id: int,
    role: Role,
    seasons: Iterable[int],
    *,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return one row per season for the given player, FanGraphs columns intact.

    Tolerant per-season: if a season's league panel can't be fetched (block,
    network, 404), that season is skipped and a warning logged. Returns an
    empty DataFrame if EVERY season fails — the analysis layer detects that
    and reports it in the analysis report's notes.
    """
    frames: list[pd.DataFrame] = []
    for season in seasons:
        try:
            league = get_league_season(season, role, force_refresh=force_refresh)
        except Exception as e:
            log.warning("league_season fetch failed for %s/%s: %s", role, season, e)
            continue
        if league.empty:
            continue
        sub = _filter_player(league, mlbam_id).copy()
        if not sub.empty:
            sub["__season"] = season
            frames.append(sub)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _seasons_player_appears_in(mlbam_id: int, seasons: Iterable[int], role: Role) -> bool:
    for season in seasons:
        try:
            df = get_league_season(season, role)
        except Exception:
            continue
        if df.empty:
            continue
        if not _filter_player(df, mlbam_id).empty:
            return True
    return False
