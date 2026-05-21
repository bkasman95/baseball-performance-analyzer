"""League-wide leaderboards and percentiles for context/baselines.

Used by the analysis layer to z-score a player against the league for the
same season, and to surface league-relative percentiles in the UI.
"""

from __future__ import annotations

import logging
from typing import Literal

import pandas as pd

from app.data.cache import read_through_cache
from app.data.pybaseball_setup import setup_pybaseball
from app.data.retry import with_retry, classify_pybaseball_error
from app.data.savant import fetch_savant_leaderboard, SavantBoard


log = logging.getLogger(__name__)

LeaderboardKind = Literal[
    "pitcher_expected",
    "batter_expected",
    "pitcher_percentile",
    "batter_percentile",
    "pitcher_arsenal",
    "bat_tracking",     # Savant direct
    "arm_angles",       # Savant direct
]


@with_retry
def _fetch_pybaseball_board(kind: LeaderboardKind, season: int) -> pd.DataFrame:
    setup_pybaseball()
    import pybaseball as pb

    try:
        if kind == "pitcher_expected":
            return pb.statcast_pitcher_expected_stats(year=season)
        if kind == "batter_expected":
            return pb.statcast_batter_expected_stats(year=season)
        if kind == "pitcher_percentile":
            return pb.statcast_pitcher_percentile_ranks(year=season)
        if kind == "batter_percentile":
            return pb.statcast_batter_percentile_ranks(year=season)
        if kind == "pitcher_arsenal":
            return pb.statcast_pitcher_arsenal_stats(year=season)
    except Exception as e:
        raise classify_pybaseball_error(e) from e
    return pd.DataFrame()


_SAVANT_KIND_TO_BOARD: dict[str, SavantBoard] = {
    "bat_tracking": "bat-tracking",
    "arm_angles": "arm-angles",
}


def get_leaderboard(
    kind: LeaderboardKind,
    season: int,
    *,
    force_refresh: bool = False,
) -> pd.DataFrame:
    key = f"leaderboard:{kind}:{season}"
    if kind in _SAVANT_KIND_TO_BOARD:
        board = _SAVANT_KIND_TO_BOARD[kind]
        return read_through_cache(
            key,
            lambda: fetch_savant_leaderboard(board, season),
            force_refresh=force_refresh,
        )
    return read_through_cache(
        key,
        lambda: _fetch_pybaseball_board(kind, season),
        force_refresh=force_refresh,
    )
