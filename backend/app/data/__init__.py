"""DiamondScope data layer.

This package is the ONLY module that touches `pybaseball` or Baseball Savant
directly. Everything else (analysis, API) must go through these functions so
caching, retries, and rate-limiting are uniform.
"""

from app.data.players import resolve_player, search_players, Player
from app.data.aggregates import get_season_aggregates
from app.data.statcast import get_statcast
from app.data.leaderboards import get_leaderboard

__all__ = [
    "resolve_player",
    "search_players",
    "Player",
    "get_season_aggregates",
    "get_statcast",
    "get_leaderboard",
]
