"""Direct Baseball Savant leaderboard CSV fetcher.

For newer metrics (bat tracking 2024+, pitcher arm angle 2023+) that
pybaseball may not yet wrap. Savant exposes CSV exports off its leaderboard
endpoints; URL params change occasionally, so this module isolates them.

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

_USER_AGENT = "DiamondScope/0.1 (private analytics; respectful caching+throttling)"
_TIMEOUT = httpx.Timeout(30.0)


SavantBoard = Literal["bat-tracking", "arm-angles"]


_LEADERBOARD_URLS: dict[SavantBoard, str] = {
    # Verify at build time — these params drift. Keep the structure (csv=true) stable.
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
}


@with_retry
def _http_get(url: str) -> bytes:
    try:
        with httpx.Client(headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT) as client:
            resp = client.get(url)
        if resp.status_code in (403, 429) or 500 <= resp.status_code < 600:
            raise TransientFetchError(f"Savant {resp.status_code} for {url}")
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPError as e:
        raise TransientFetchError(f"Savant HTTP error: {e}") from e


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
        return pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        log.warning("Savant CSV parse failed for %s/%s: %s", board, season, e)
        return pd.DataFrame()
