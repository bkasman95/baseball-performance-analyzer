"""League-wide leaderboards and percentiles for context/baselines.

Every Savant leaderboard goes through the direct CSV fetcher in `savant.py`
— pybaseball's wrappers force a UTF-8 decode that crashes on Savant's
latin-1 player names, and we don't want our retry layer eating ~16s per
endpoint backing off from a failure that's actually permanent.
"""

from __future__ import annotations

import logging
from typing import Literal

import pandas as pd

from app.data.cache import read_through_cache
from app.data.savant import fetch_savant_leaderboard, SavantBoard


log = logging.getLogger(__name__)

LeaderboardKind = Literal[
    "pitcher_expected",
    "batter_expected",
    "pitcher_exitvelo",
    "batter_exitvelo",
    "pitcher_percentile",
    "batter_percentile",
    "pitcher_arsenal_usage",
    "pitcher_arsenal_speed",
    "pitcher_arsenal_spin",
    "pitcher_arsenal_stats",
    "bat_tracking",
    "arm_angles",
]


# Map our analysis-layer LeaderboardKind to the Savant URL key.
_KIND_TO_BOARD: dict[LeaderboardKind, SavantBoard] = {
    "pitcher_expected":        "pitcher-expected",
    "batter_expected":         "batter-expected",
    "pitcher_exitvelo":        "pitcher-exitvelo",
    "batter_exitvelo":         "batter-exitvelo",
    "pitcher_percentile":      "pitcher-percentile",
    "batter_percentile":       "batter-percentile",
    "pitcher_arsenal_usage":   "pitcher-arsenal-usage",
    "pitcher_arsenal_speed":   "pitcher-arsenal-speed",
    "pitcher_arsenal_spin":    "pitcher-arsenal-spin",
    "pitcher_arsenal_stats":   "pitcher-arsenal-stats",
    "bat_tracking":            "bat-tracking",
    "arm_angles":              "arm-angles",
}


def get_leaderboard(
    kind: LeaderboardKind,
    season: int,
    *,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Fetch and cache the requested league-wide leaderboard for `season`.

    The full league table (~600 players) is cached as a Parquet file under
    `leaderboard:<kind>:<season>`; per-player slicing happens at read time.
    Returns an empty DataFrame on any fetch / parse failure rather than
    raising, so the analysis layer degrades gracefully.
    """
    board = _KIND_TO_BOARD.get(kind)
    if board is None:
        log.warning("unknown leaderboard kind: %s", kind)
        return pd.DataFrame()
    key = f"leaderboard:{kind}:{season}"
    try:
        return read_through_cache(
            key,
            lambda: fetch_savant_leaderboard(board, season),
            force_refresh=force_refresh,
        )
    except Exception as e:
        log.warning("leaderboard fetch failed for %s/%s: %s", kind, season, e)
        return pd.DataFrame()
