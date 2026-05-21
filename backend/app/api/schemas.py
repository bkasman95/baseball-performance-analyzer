"""Pydantic response models for the API.

The analysis report is intentionally typed loosely (`dict`) so adding fields
to AnalysisReport.to_dict() in the analysis engine doesn't force a schema
migration here.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


# ---- Players ---------------------------------------------------------------

class PlayerCard(BaseModel):
    mlbam_id: int
    fangraphs_id: int | None = None
    full_name: str
    first_name: str
    last_name: str
    role: Literal["pitcher", "hitter", "two_way", "unknown"]
    debut_year: int | None = None
    last_year: int | None = None


class PlayerSearchResponse(BaseModel):
    query: str
    results: list[PlayerCard]


class PlayerProfile(BaseModel):
    mlbam_id: int
    full_name: str
    first_name: str
    last_name: str
    role: Literal["pitcher", "hitter", "two_way", "unknown"]
    debut_year: int | None = None
    last_year: int | None = None
    seasons_available: list[int]
    photo_url: str | None = None


# ---- Analysis --------------------------------------------------------------

class AnalysisAccepted(BaseModel):
    status: Literal["accepted"] = "accepted"
    job_id: str
    job_status: Literal["pending", "running", "complete", "failed"]
    status_url: str
    message: str


# ---- Jobs ------------------------------------------------------------------

class JobView(BaseModel):
    id: str
    key: str
    kind: str
    status: Literal["pending", "running", "complete", "failed"]
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    progress: float = 0.0
    error: str | None = None
    result: Any = None
    meta: dict = {}


# ---- Timeseries ------------------------------------------------------------

class TimeseriesPoint(BaseModel):
    x: str | int | float    # season number or game_date ISO string
    y: float | None


class TimeseriesResponse(BaseModel):
    player_id: int
    metric: str
    grain: Literal["season", "rolling"]
    points: list[TimeseriesPoint]
    notes: list[str] = []


# ---- Refresh ---------------------------------------------------------------

class RefreshResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    player_id: int
    invalidated_keys: int
    job_id: str | None = None
    message: str
