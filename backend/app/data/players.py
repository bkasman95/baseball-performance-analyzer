"""Player resolution: fuzzy name -> MLBAM ID, with role detection.

Strategy:
  1. Cache the full pybaseball Chadwick name register once (covers every
     player who has appeared in affiliated ball). Reused for autocomplete.
  2. `resolve_player(name)` does a fuzzy match against that table; if the
     match is ambiguous (multiple plausible candidates), return all of them.
  3. Role (hitter vs pitcher) is inferred by checking which leaderboard
     (batting_stats vs pitching_stats) lists the player in recent seasons.
     A player can be both; we default to "two_way" in that case.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Literal

import pandas as pd

from app.data.cache import read_through_cache
from app.data.pybaseball_setup import setup_pybaseball
from app.data.retry import with_retry, TransientFetchError


log = logging.getLogger(__name__)

Role = Literal["pitcher", "hitter", "two_way", "unknown"]


@dataclass
class Player:
    mlbam_id: int
    fangraphs_id: int | None
    first_name: str
    last_name: str
    role: Role
    debut_year: int | None
    last_year: int | None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["full_name"] = self.full_name
        return d


# ---------------------------------------------------------------------------
# Chadwick name register (autocomplete table)
# ---------------------------------------------------------------------------

_NAME_TABLE_KEY = "chadwick_name_register"


@with_retry
def _fetch_name_table() -> pd.DataFrame:
    setup_pybaseball()
    from pybaseball import chadwick_register

    try:
        df = chadwick_register()
    except Exception as e:
        raise TransientFetchError(f"chadwick_register failed: {e}") from e

    # Keep only players with an MLBAM id and a debut/last year — that's our universe.
    df = df[df["key_mlbam"].notna()].copy()
    df["key_mlbam"] = df["key_mlbam"].astype(int)
    if "key_fangraphs" in df.columns:
        df["key_fangraphs"] = pd.to_numeric(df["key_fangraphs"], errors="coerce")
    df["name_first"] = df["name_first"].fillna("").astype(str)
    df["name_last"] = df["name_last"].fillna("").astype(str)
    df["mlb_played_first"] = pd.to_numeric(df.get("mlb_played_first"), errors="coerce")
    df["mlb_played_last"] = pd.to_numeric(df.get("mlb_played_last"), errors="coerce")
    return df


def get_name_table(force_refresh: bool = False) -> pd.DataFrame:
    return read_through_cache(_NAME_TABLE_KEY, _fetch_name_table, force_refresh=force_refresh)


# ---------------------------------------------------------------------------
# Search + resolve
# ---------------------------------------------------------------------------

def _score(query: str, first: str, last: str, full: str) -> float:
    """Cheap similarity score, no extra deps. Higher = better."""
    q = query.lower().strip()
    f = first.lower()
    l = last.lower()
    fl = full.lower()
    if not q:
        return 0.0
    score = 0.0
    if fl == q:
        score += 100
    if fl.startswith(q):
        score += 40
    if q in fl:
        score += 20
    if l.startswith(q):
        score += 25
    if f.startswith(q):
        score += 10
    # bonus for two-word query matching "first last"
    parts = q.split()
    if len(parts) == 2 and f.startswith(parts[0]) and l.startswith(parts[1]):
        score += 30
    return score


def search_players(query: str, limit: int = 10, *, active_only: bool = True) -> list[Player]:
    """Autocomplete: return top-N players matching the query string."""
    if not query or len(query.strip()) < 2:
        return []
    df = get_name_table()
    if active_only:
        current_year = datetime.utcnow().year
        df = df[df["mlb_played_last"].fillna(0) >= (current_year - 2)]

    df = df.copy()
    df["full"] = (df["name_first"] + " " + df["name_last"]).str.strip()
    df["score"] = df.apply(
        lambda r: _score(query, r["name_first"], r["name_last"], r["full"]),
        axis=1,
    )
    top = df[df["score"] > 0].sort_values(
        ["score", "mlb_played_last"], ascending=[False, False]
    ).head(limit)

    results: list[Player] = []
    for _, r in top.iterrows():
        results.append(
            Player(
                mlbam_id=int(r["key_mlbam"]),
                fangraphs_id=int(r["key_fangraphs"]) if pd.notna(r.get("key_fangraphs")) else None,
                first_name=r["name_first"],
                last_name=r["name_last"],
                role="unknown",  # filled in lazily on resolve
                debut_year=int(r["mlb_played_first"]) if pd.notna(r["mlb_played_first"]) else None,
                last_year=int(r["mlb_played_last"]) if pd.notna(r["mlb_played_last"]) else None,
            )
        )
    return results


def resolve_player(name: str) -> list[Player]:
    """Return matching players for `name`, role-detected.

    Returns multiple players when the name is ambiguous (e.g. "Will Smith").
    Caller decides whether to auto-pick the top result or prompt the user.
    """
    candidates = search_players(name, limit=5)
    return [_attach_role(p) for p in candidates]


def get_player_by_mlbam(mlbam_id: int) -> Player | None:
    df = get_name_table()
    row = df[df["key_mlbam"] == mlbam_id]
    if row.empty:
        return None
    r = row.iloc[0]
    p = Player(
        mlbam_id=int(r["key_mlbam"]),
        fangraphs_id=int(r["key_fangraphs"]) if pd.notna(r.get("key_fangraphs")) else None,
        first_name=r["name_first"],
        last_name=r["name_last"],
        role="unknown",
        debut_year=int(r["mlb_played_first"]) if pd.notna(r["mlb_played_first"]) else None,
        last_year=int(r["mlb_played_last"]) if pd.notna(r["mlb_played_last"]) else None,
    )
    return _attach_role(p)


# ---------------------------------------------------------------------------
# Role detection
# ---------------------------------------------------------------------------

def _attach_role(p: Player) -> Player:
    # Inferred from recent leaderboard membership. Cheap: leaderboards are cached.
    from app.data.aggregates import _seasons_player_appears_in  # local import to avoid cycle

    year = p.last_year or datetime.utcnow().year
    seasons = list(range(max(2015, year - 2), year + 1))
    appears_batting = _seasons_player_appears_in(p.mlbam_id, seasons, "batting")
    appears_pitching = _seasons_player_appears_in(p.mlbam_id, seasons, "pitching")

    if appears_batting and appears_pitching:
        p.role = "two_way"
    elif appears_pitching:
        p.role = "pitcher"
    elif appears_batting:
        p.role = "hitter"
    else:
        p.role = "unknown"
    return p
