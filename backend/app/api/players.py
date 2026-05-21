"""Player-centric endpoints (§7).

  GET  /api/players/search?q=
  GET  /api/players/{id}/profile
  GET  /api/players/{id}/analysis?season=YYYY        — async, 200 cached or 202 + job_id
  GET  /api/players/{id}/metrics/timeseries?...      — raw series for charts
  POST /api/players/{id}/refresh                     — force cache invalidate + rebuild
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Response

# NOTE: heavy ML imports (app.analysis -> scikit-learn / shap / ruptures) are
# resolved lazily inside the analysis paths below. Keeping them off the cold
# import path lets the API stay under tight memory ceilings (e.g. Render's
# 512 MB free tier) for search / profile / timeseries traffic.
from app.auth.dependencies import get_current_user
from app.api.schemas import (
    AnalysisAccepted,
    PlayerCard,
    PlayerProfile,
    PlayerSearchResponse,
    RefreshResponse,
    TimeseriesPoint,
    TimeseriesResponse,
)
from app.config import get_settings
from app.data import (
    get_season_aggregates,
    get_statcast,
    search_players,
)
from app.data.aggregates import get_league_season
from app.data.cache import invalidate
from app.data.players import get_player_by_mlbam
from app.jobs.registry import get_registry


log = logging.getLogger(__name__)

router = APIRouter(prefix="/players", tags=["players"], dependencies=[Depends(get_current_user)])


# ---------------------------------------------------------------------------
# Search + profile
# ---------------------------------------------------------------------------

@router.get("/search", response_model=PlayerSearchResponse)
def search(
    q: str = Query(..., min_length=2, description="Player name fragment"),
    limit: int = Query(10, ge=1, le=25),
    active_only: bool = Query(True, description="Restrict to players active in the last 2 seasons"),
) -> PlayerSearchResponse:
    try:
        results = search_players(q, limit=limit, active_only=active_only)
    except Exception as e:
        log.exception("search_players failed")
        raise HTTPException(status_code=503, detail=f"player search unavailable: {e}")
    return PlayerSearchResponse(
        query=q,
        results=[PlayerCard(**_player_card(p)) for p in results],
    )


def _player_card(p) -> dict:
    d = p.to_dict() if hasattr(p, "to_dict") else p
    return {
        "mlbam_id": d["mlbam_id"],
        "fangraphs_id": d.get("fangraphs_id"),
        "full_name": d.get("full_name") or f"{d['first_name']} {d['last_name']}",
        "first_name": d["first_name"],
        "last_name": d["last_name"],
        "role": d.get("role", "unknown"),
        "debut_year": d.get("debut_year"),
        "last_year": d.get("last_year"),
    }


_PHOTO_URL_TEMPLATE = (
    "https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png"
    "/w_213,q_auto:best/v1/people/{mlbam_id}/headshot/67/current"
)


@router.get("/{mlbam_id}/profile", response_model=PlayerProfile)
def profile(mlbam_id: int) -> PlayerProfile:
    # Skip role detection here — that fetches multi-season FanGraphs panels
    # and is slow on a cold cache. The analysis job resolves the role.
    p = get_player_by_mlbam(mlbam_id, with_role_detection=False)
    if p is None:
        raise HTTPException(status_code=404, detail=f"player not found: {mlbam_id}")

    # Available seasons: anything between debut/last that has a cached row,
    # else just the [debut..last] range. Avoid hitting the network here —
    # this endpoint must stay fast.
    seasons: list[int] = []
    if p.debut_year is not None and p.last_year is not None:
        seasons = list(range(int(p.debut_year), int(p.last_year) + 1))

    return PlayerProfile(
        mlbam_id=p.mlbam_id,
        full_name=p.full_name,
        first_name=p.first_name,
        last_name=p.last_name,
        role=p.role,
        debut_year=p.debut_year,
        last_year=p.last_year,
        seasons_available=seasons,
        photo_url=_PHOTO_URL_TEMPLATE.format(mlbam_id=p.mlbam_id),
    )


# ---------------------------------------------------------------------------
# Analysis (async)
# ---------------------------------------------------------------------------

def _analysis_key(mlbam_id: int, season: int) -> str:
    return f"analysis:{mlbam_id}:{season}"


def _run_analysis(mlbam_id: int, role: str, season: int, seasons_window: int) -> dict:
    """Wrapper that the job runner invokes. Returns a JSON-able dict."""
    # Lazy import so sklearn / shap / ruptures only load when an analysis
    # actually runs — not during cold-start of every API worker.
    from app.analysis import build_report

    report = build_report(
        player_id=mlbam_id,
        role=role,                # type: ignore[arg-type]
        season=season,
        seasons_window=seasons_window,
    )
    return report.to_dict()


def _run_analysis_with_role_detection(mlbam_id: int, season: int, seasons_window: int) -> dict:
    """Detect role THEN run the analysis, all inside the background job.

    Keeps the HTTP request that initiated this job non-blocking even on a
    cold cache where role detection has to fetch FanGraphs panels.
    """
    p = get_player_by_mlbam(mlbam_id, with_role_detection=True)
    role = "hitter"
    if p is not None and p.role in ("pitcher", "hitter"):
        role = p.role
    # two_way / unknown still default to hitter; the report degrades gracefully
    # when batting/pitching aggregates are missing.
    return _run_analysis(mlbam_id, role, season, seasons_window)


@router.get("/{mlbam_id}/analysis")
def get_analysis(
    mlbam_id: int,
    response: Response,
    season: int | None = Query(None, description="Defaults to last season the player appeared"),
    seasons_window: int | None = Query(None, ge=2, le=15),
) -> dict:
    """Run (or fetch) the full analysis report.

    Behavior:
      * If a completed job for (player, season) sits in the registry, return
        its result with HTTP 200.
      * Else submit a new job and return HTTP 202 with a `job_id` and
        `status_url` to poll.
      * If a job for the same key is already in flight, the registry returns
        that one — the client never starts duplicates.
    """
    settings = get_settings()
    # Fast lookup — role detection happens inside the background job so this
    # HTTP request never blocks on FanGraphs network calls.
    p = get_player_by_mlbam(mlbam_id, with_role_detection=False)
    if p is None:
        raise HTTPException(status_code=404, detail=f"player not found: {mlbam_id}")

    if season is None:
        season = p.last_year or datetime.utcnow().year

    sw = seasons_window or settings.default_season_window
    # Key does NOT include role: role is determined inside the job, but the
    # (player, season) pair is what makes work duplicative across requests.
    key = _analysis_key(mlbam_id, season)
    registry = get_registry()

    existing = registry.get_by_key(key)
    if existing is not None and existing.status == "complete":
        return {"status": "ok", "report": existing.result, "job_id": existing.id}

    job = registry.submit(
        key=key,
        kind="analysis",
        fn=lambda: _run_analysis_with_role_detection(mlbam_id, season, sw),
        meta={"player_id": mlbam_id, "season": season, "seasons_window": sw},
    )

    response.status_code = 202
    return AnalysisAccepted(
        job_id=job.id,
        job_status=job.status,
        status_url=f"/api/jobs/{job.id}",
        message="analysis running; poll status_url",
    ).model_dump()


# ---------------------------------------------------------------------------
# Timeseries
# ---------------------------------------------------------------------------

@router.get("/{mlbam_id}/metrics/timeseries", response_model=TimeseriesResponse)
def metric_timeseries(
    mlbam_id: int,
    metric: str = Query(..., description="Canonical metric name from the catalog, e.g. 'ERA'"),
    grain: Literal["season", "rolling"] = Query("season"),
    season: int | None = Query(None, description="Required when grain=rolling"),
    window: int = Query(30, ge=5, le=200, description="Rolling window size when grain=rolling"),
    seasons_window: int = Query(6, ge=2, le=15),
) -> TimeseriesResponse:
    p = get_player_by_mlbam(mlbam_id, with_role_detection=False)
    if p is None:
        raise HTTPException(status_code=404, detail=f"player not found: {mlbam_id}")
    role = p.role if p.role in ("pitcher", "hitter") else "hitter"

    # Lazy import — keeps the analysis metric catalog (and indirectly the
    # heavier analysis chain) off the cold import path.
    from app.analysis.metrics import get_metric

    m = get_metric(role, metric)
    if m is None:
        raise HTTPException(status_code=400, detail=f"unknown metric '{metric}' for {role}")

    notes: list[str] = []
    points: list[TimeseriesPoint] = []

    if grain == "season":
        end = season or (p.last_year or datetime.utcnow().year)
        seasons = list(range(end - seasons_window + 1, end + 1))
        try:
            df = get_season_aggregates(mlbam_id, role, seasons)  # type: ignore[arg-type]
        except Exception as e:
            log.warning("season aggregates fetch failed for %s: %s", mlbam_id, e)
            df = pd.DataFrame()

        if df.empty or "__season" not in df.columns:
            notes.append("no_season_data")
        else:
            col = m.column_in(df)
            if col is None:
                notes.append(f"metric_column_missing:{metric}")
            else:
                for _, row in df.sort_values("__season").iterrows():
                    season_val = int(row["__season"])
                    y = m.value_in(row)
                    points.append(TimeseriesPoint(x=season_val, y=y))

    else:  # rolling
        if season is None:
            raise HTTPException(status_code=400, detail="season is required when grain=rolling")
        try:
            sc = get_statcast(mlbam_id, role, season)  # type: ignore[arg-type]
        except Exception as e:
            log.warning("statcast fetch failed for %s/%s: %s", mlbam_id, season, e)
            sc = pd.DataFrame()

        statcast_col = _rolling_proxy_column(role, metric)
        if statcast_col is None:
            notes.append("no_rolling_proxy_for_metric")
        elif sc.empty or statcast_col not in sc.columns:
            notes.append("no_statcast_data")
        else:
            sc = sc.dropna(subset=[statcast_col]).copy()
            if "game_date" in sc.columns:
                sc = sc.sort_values("game_date")
            roll = sc[statcast_col].astype(float).rolling(window=window, min_periods=window).mean()
            for date_val, y in zip(
                sc["game_date"].astype(str) if "game_date" in sc.columns else range(len(roll)),
                roll,
            ):
                if pd.isna(y):
                    continue
                points.append(TimeseriesPoint(x=date_val, y=float(y)))

    return TimeseriesResponse(
        player_id=mlbam_id,
        metric=metric,
        grain=grain,
        points=points,
        notes=notes,
    )


def _rolling_proxy_column(role: str, metric: str) -> str | None:
    """Best-effort mapping from canonical metric name to the Statcast column
    we can roll on. We don't cover every metric — only the ones for which
    a pitch-level proxy makes sense.
    """
    common = {
        "wOBA": "estimated_woba_using_speedangle",
        "EV": "launch_speed",
        "HardHit%": "launch_speed",
    }
    pitcher = {**common, "FB_velocity": "release_speed"}
    hitter = {**common}
    return (pitcher if role == "pitcher" else hitter).get(metric)


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

@router.post("/{mlbam_id}/refresh", response_model=RefreshResponse)
def refresh(
    mlbam_id: int,
    season: int | None = Query(None, description="If given, only invalidate this season"),
) -> RefreshResponse:
    p = get_player_by_mlbam(mlbam_id, with_role_detection=False)
    if p is None:
        raise HTTPException(status_code=404, detail=f"player not found: {mlbam_id}")
    role = p.role if p.role in ("pitcher", "hitter") else "hitter"

    if season is not None:
        prefix = f"statcast_{role}:{mlbam_id}:{season}"
        removed = invalidate(prefix)
    else:
        removed = invalidate(f"statcast_{role}:{mlbam_id}:")

    # Kick a fresh analysis off in the background so the next read is warm.
    job_id = None
    if season is not None:
        registry = get_registry()
        key = _analysis_key(mlbam_id, season)
        sw = get_settings().default_season_window
        job = registry.submit(
            key=key,
            kind="analysis",
            fn=lambda: _run_analysis_with_role_detection(mlbam_id, season, sw),
            meta={"player_id": mlbam_id, "season": season, "trigger": "refresh"},
        )
        job_id = job.id

    return RefreshResponse(
        player_id=mlbam_id,
        invalidated_keys=removed,
        job_id=job_id,
        message=f"invalidated {removed} cache entries" + (f"; rebuild job {job_id}" if job_id else ""),
    )
