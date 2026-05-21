"""Season-level aggregates for hitters and pitchers.

Three layered sources, in priority order:

  1. **Baseball Savant leaderboards** (primary) — MLB's official per-season
     metrics: xERA, xBA, xSLG, xwOBA, Barrel%, HardHit%, EV, pitch arsenal,
     swing decisions. These are computed by Savant with park / league
     factors we can't replicate. See `savant_leaderboards.py`.

  2. **Pitch-data derivations** (gap-filler) — the metrics MLB doesn't
     publish on a leaderboard (FIP, WHIP, HR/9, BABIP, CSW%, OBP, etc.).
     Computed from cached pitch-level Statcast, with exact formulas. See
     `savant_aggregates.py`.

  3. **FanGraphs `batting_stats` / `pitching_stats`** (fallback) — only used
     if BOTH Savant paths fail for a given season. FanGraphs blocks many
     cloud IP ranges so this rarely succeeds in production, but it's free
     insurance for local development.

Each season ends up as one row in the returned DataFrame, with columns that
match what the metric catalog expects (see `app/analysis/metrics.py`).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, Literal

import pandas as pd

from app.data.cache import read_through_cache
from app.data.pybaseball_setup import setup_pybaseball
from app.data.retry import with_retry, classify_pybaseball_error


log = logging.getLogger(__name__)


# Each season's row build does 1 pitch-data fetch + parallel leaderboard
# fetches. Running multiple seasons concurrently lets us collapse a 6-season
# analysis from sum-of-latencies down to roughly max-of-latencies.
_SEASON_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="season-fan")

Role = Literal["hitter", "pitcher", "batting", "pitching"]


def _normalize_role(role: Role) -> str:
    return "batting" if role in ("hitter", "batting") else "pitching"


# ---------------------------------------------------------------------------
# FanGraphs fallback (rarely used in prod; FG blocks most cloud IPs)
# ---------------------------------------------------------------------------

@with_retry
def _fetch_batting(season: int) -> pd.DataFrame:
    setup_pybaseball()
    from pybaseball import batting_stats

    try:
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


def _filter_player(df: pd.DataFrame, mlbam_id: int) -> pd.DataFrame:
    for col in ("MLBAMID", "mlbamid", "key_mlbam"):
        if col in df.columns:
            sub = df[df[col].astype("Int64") == mlbam_id]
            if not sub.empty:
                return sub
    return df.iloc[0:0]


# ---------------------------------------------------------------------------
# Main entry point — assemble season rows from all three sources
# ---------------------------------------------------------------------------

def get_season_aggregates(
    mlbam_id: int,
    role: Role,
    seasons: Iterable[int],
    *,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return one row per season for the given player.

    Each row is built by layering, in this order (later layers win on key
    collisions): pitch-derived gaps → Savant leaderboards → FanGraphs.
    Savant leaderboards are authoritative for everything they publish.
    """
    from app.data.savant_aggregates import pitcher_gaps_from_pitches, hitter_gaps_from_pitches
    from app.data.savant_leaderboards import assemble_pitcher_season, assemble_hitter_season
    from app.data.statcast import get_statcast

    norm = "pitcher" if role in ("pitcher", "pitching") else "hitter"
    assemble_leaderboard = assemble_pitcher_season if norm == "pitcher" else assemble_hitter_season
    derive_gaps = pitcher_gaps_from_pitches if norm == "pitcher" else hitter_gaps_from_pitches

    season_list = list(seasons)

    def _build_row(season: int) -> dict | None:
        # Layer 1: pitch-derived (BABIP, FIP, WHIP, OBP, etc.)
        try:
            sc = get_statcast(mlbam_id, norm, season, force_refresh=force_refresh)
        except Exception as e:
            log.warning("statcast pitch fetch failed for %s/%s/%s: %s", mlbam_id, norm, season, e)
            sc = pd.DataFrame()
        gaps = derive_gaps(sc) if not sc.empty else {}

        # Layer 2: Savant leaderboards (xERA, xwOBA, Barrel%, HardHit%, …).
        # `assemble_leaderboard` fetches its 6 (pitcher) / 3 (hitter)
        # endpoints concurrently via its own pool.
        try:
            lb = assemble_leaderboard(mlbam_id, season, force_refresh=force_refresh)
        except Exception as e:
            log.warning("savant leaderboard assembly failed for %s/%s: %s", mlbam_id, season, e)
            lb = {}

        # Merge: later wins. Leaderboards override pitch-derived for any
        # metric they both publish (the leaderboard is authoritative).
        row: dict = {**gaps, **lb}
        k_pct = row.get("K%")
        bb_pct = row.get("BB%")
        if k_pct is not None and bb_pct is not None:
            row["K-BB%"] = float(k_pct) - float(bb_pct)

        if not row:
            return None
        row["__season"] = season
        return row

    # Fan seasons out across the pool — wall time becomes ~max(season) rather
    # than sum(season). Within each season the leaderboards already run in
    # parallel, so we stay polite to Savant by capping the pool small.
    futures = [_SEASON_POOL.submit(_build_row, s) for s in season_list]
    rows = [r for f in futures if (r := f.result()) is not None]

    savant_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    seasons_covered = set(savant_df["__season"].astype(int).tolist()) if not savant_df.empty else set()

    # Layer 3: FanGraphs fallback for seasons Savant couldn't cover at all.
    fg_frames: list[pd.DataFrame] = []
    for season in season_list:
        if season in seasons_covered:
            continue
        try:
            league = get_league_season(season, role, force_refresh=force_refresh)
        except Exception as e:
            log.warning("FG league_season fetch failed for %s/%s: %s", role, season, e)
            continue
        if league.empty:
            continue
        sub = _filter_player(league, mlbam_id).copy()
        if not sub.empty:
            sub["__season"] = season
            fg_frames.append(sub)

    pieces = [df for df in (savant_df, *fg_frames) if not df.empty]
    if not pieces:
        return pd.DataFrame()
    return pd.concat(pieces, ignore_index=True, sort=False)
