"""Direct Baseball Savant leaderboard CSV fetcher.

Bypasses pybaseball's wrappers, which decode every response as UTF-8 — Savant
returns latin-1 (because player names like "José" / "Núñez" use single-byte
extended-ASCII), so pybaseball's reads blow up with `UnicodeDecodeError` and
then our retry layer wastes 16 seconds backing off per failed fetch.

We do our own httpx calls with encoding fallback (utf-8 → latin-1) so the
data layer succeeds on the first attempt.

If a leaderboard disappears or its params change, the analysis layer must
degrade gracefully — never crash.
"""

from __future__ import annotations

import io
import logging
from typing import Literal

import httpx
import pandas as pd

from app.data.retry import with_retry, TransientFetchError


log = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT = httpx.Timeout(30.0)


SavantBoard = Literal[
    "bat-tracking",
    "arm-angles",
    "pitcher-expected",
    "batter-expected",
    "pitcher-exitvelo",
    "batter-exitvelo",
    "pitcher-percentile",
    "batter-percentile",
    "pitcher-arsenal-usage",
    "pitcher-arsenal-speed",
    "pitcher-arsenal-spin",
    "pitcher-arsenal-stats",
]


# Each value is a URL template with `{season}` (and sometimes `{min}` already
# baked in). minPA / minBBE / minP defaults are kept low so partial-season
# pulls (early in a current year) still return useful data.
_LEADERBOARD_URLS: dict[SavantBoard, str] = {
    "bat-tracking": (
        "https://baseballsavant.mlb.com/leaderboard/bat-tracking"
        "?attackZone=&batSide=&contactType=&count=&dateType=&detailtype=&endDate=&firstBatter=&"
        "hand=&isHardHit=&minSwings=q&minGroupSwings=1&pitchHand=&pitchType=&seasonType=regular&"
        "season={season}&team=&type=batter&csv=true"
    ),
    "arm-angles": (
        "https://baseballsavant.mlb.com/leaderboard/pitcher-arm-angles"
        "?perspective=batter&season={season}&team=&min=q&pitch_hand=&csv=true"
    ),
    "pitcher-expected": (
        "https://baseballsavant.mlb.com/leaderboard/expected_statistics"
        "?type=pitcher&year={season}&position=&team=&min=10&csv=true"
    ),
    "batter-expected": (
        "https://baseballsavant.mlb.com/leaderboard/expected_statistics"
        "?type=batter&year={season}&position=&team=&min=10&csv=true"
    ),
    "pitcher-exitvelo": (
        "https://baseballsavant.mlb.com/leaderboard/statcast"
        "?type=pitcher&year={season}&position=&team=&min=10&csv=true"
    ),
    "batter-exitvelo": (
        "https://baseballsavant.mlb.com/leaderboard/statcast"
        "?type=batter&year={season}&position=&team=&min=10&csv=true"
    ),
    "pitcher-percentile": (
        "https://baseballsavant.mlb.com/leaderboard/percentile-rankings"
        "?type=pitcher&year={season}&position=&team=&csv=true"
    ),
    "batter-percentile": (
        "https://baseballsavant.mlb.com/leaderboard/percentile-rankings"
        "?type=batter&year={season}&position=&team=&csv=true"
    ),
    "pitcher-arsenal-usage": (
        "https://baseballsavant.mlb.com/leaderboard/pitch-arsenals"
        "?year={season}&min=50&type=n_&hand=&csv=true"
    ),
    "pitcher-arsenal-speed": (
        "https://baseballsavant.mlb.com/leaderboard/pitch-arsenals"
        "?year={season}&min=50&type=avg_speed&hand=&csv=true"
    ),
    "pitcher-arsenal-spin": (
        "https://baseballsavant.mlb.com/leaderboard/pitch-arsenals"
        "?year={season}&min=50&type=avg_spin&hand=&csv=true"
    ),
    "pitcher-arsenal-stats": (
        "https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats"
        "?type=pitcher&pitchType=&year={season}&team=&min=25&csv=true"
    ),
}


@with_retry
def _http_get(url: str) -> bytes:
    """GET with retry on 5xx / 429 / network errors. 4xx is a permanent fail
    (we want to surface that quickly, not back off and retry)."""
    try:
        with httpx.Client(headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT) as client:
            resp = client.get(url)
        if resp.status_code in (429,) or 500 <= resp.status_code < 600:
            raise TransientFetchError(f"Savant {resp.status_code} for {url}")
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPError as e:
        raise TransientFetchError(f"Savant HTTP error: {e}") from e


def _parse_csv_bytes(raw: bytes) -> pd.DataFrame:
    """Parse CSV bytes with encoding fallback. Savant mixes utf-8 and
    latin-1 across endpoints / seasons (names with accents)."""
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=encoding)
        except UnicodeDecodeError:
            continue
    # Final fallback: latin-1 never raises, so this only fires on non-CSV
    # responses (HTML error pages, etc.). Let the caller handle the empty df.
    return pd.read_csv(io.BytesIO(raw), encoding="latin-1", encoding_errors="replace")


def fetch_savant_leaderboard(board: SavantBoard, season: int) -> pd.DataFrame:
    """Pull a Savant CSV leaderboard. Returns empty DataFrame on hard failure."""
    if board not in _LEADERBOARD_URLS:
        raise ValueError(f"unknown Savant board: {board}")
    url = _LEADERBOARD_URLS[board].format(season=season)
    try:
        raw = _http_get(url)
    except TransientFetchError as e:
        log.warning("Savant fetch failed for %s/%s after retries: %s", board, season, e)
        return pd.DataFrame()
    try:
        df = _parse_csv_bytes(raw)
    except Exception as e:
        log.warning("Savant CSV parse failed for %s/%s: %s", board, season, e)
        return pd.DataFrame()
    df.columns = df.columns.str.strip()
    return df
