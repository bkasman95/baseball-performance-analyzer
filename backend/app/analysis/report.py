"""Stage C — report assembly + natural-language summary.

`build_report(player, role, season, ...)` is the single entry point used by
the API. It calls the data layer, runs Stage A then Stage B, and returns a
structured `AnalysisReport` ready for JSON serialization.

The NL summaries are TEMPLATE-generated from the computed numbers, so the
phrasing is deterministic — not free-form invention.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import pandas as pd

from app.analysis import anomalies as A
from app.analysis import attribution as B
from app.analysis.metrics import (
    Metric,
    Role,
    SAMPLE,
    confidence_for_sample,
    get_metric,
    label_change,
    outcomes_for,
)


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report data classes
# ---------------------------------------------------------------------------

@dataclass
class AnomalyFinding:
    """One anomaly + its ranked probable causes + NL summary."""
    anomaly: A.Anomaly
    probable_causes: list[B.ProbableCause]
    summary: str

    def to_dict(self) -> dict:
        return {
            **self.anomaly.to_dict(),
            "probable_causes": [c.to_dict() for c in self.probable_causes],
            "summary": self.summary,
        }


@dataclass
class AnalysisReport:
    player_id: int
    role: Role
    season: int
    seasons_analyzed: list[int]
    findings: list[AnomalyFinding] = field(default_factory=list)
    multivariate: dict | None = None
    headline: str = ""
    generated_at: str = ""
    sample: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "player_id": self.player_id,
            "role": self.role,
            "season": self.season,
            "seasons_analyzed": self.seasons_analyzed,
            "findings": [f.to_dict() for f in self.findings],
            "multivariate": self.multivariate,
            "headline": self.headline,
            "generated_at": self.generated_at,
            "sample": self.sample,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# NL summary templates
# ---------------------------------------------------------------------------

def _fmt(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.3f}" if abs(v) < 100 else f"{v:.2f}"


def _summarize_finding(role: Role, anomaly: A.Anomaly, causes: list[B.ProbableCause]) -> str:
    metric = get_metric(role, anomaly.metric)
    if metric is None:
        return ""
    direction_word = anomaly.direction
    direction_phrase = {
        "improvement": "improved",
        "regression": "got worse",
        "change": "changed notably",
    }.get(direction_word, "changed")

    if anomaly.kind == "year_over_year":
        head = (
            f"{anomaly.metric} {direction_phrase} from {_fmt(anomaly.before)} to "
            f"{_fmt(anomaly.after)} year over year"
        )
    elif anomaly.kind == "changepoint":
        head = (
            f"{anomaly.metric} {direction_phrase} mid-season, shifting from "
            f"{_fmt(anomaly.before)} to {_fmt(anomaly.after)} after the changepoint"
        )
    else:
        head = f"{anomaly.metric} shifted notably"

    if not causes:
        return head + "."

    top = causes[:3]
    parts = []
    for c in top:
        parts.append(f"{c.driver} ({_fmt(c.before)} → {_fmt(c.after)})")
    drivers_str = ", ".join(parts)
    confidence_note = "" if anomaly.confidence == "high" else " (low-confidence: small sample)"

    return (
        f"{head}. The most likely drivers are {drivers_str}{confidence_note}."
    )


def _headline(role: Role, findings: list[AnomalyFinding]) -> str:
    if not findings:
        return "No significant outcome anomalies detected this season."
    # Highlight the highest-severity, most-recent finding.
    sev_rank = {"high": 3, "medium": 2, "low": 1}
    f = max(findings, key=lambda x: (sev_rank.get(x.anomaly.severity, 0), x.anomaly.season or 0))
    return f.summary


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_report(
    *,
    player_id: int,
    role: Role,
    season: int,
    seasons_window: int = 6,
    fetch_seasons=None,
    fetch_statcast=None,
    fetch_league_panel=None,
) -> AnalysisReport:
    """Build an analysis report for `player_id` ending at `season`.

    The `fetch_*` callables let the API/tests inject data-layer functions
    without coupling this module to `app.data`. In normal use, the API layer
    passes the real `app.data.*` functions.

    Signatures the callables must satisfy:
      fetch_seasons(player_id, role, list[int]) -> pd.DataFrame  (one row per season)
      fetch_statcast(player_id, role, season)   -> pd.DataFrame  (pitch-level)
      fetch_league_panel(role, season)          -> pd.DataFrame  (league-wide season)
    """
    if fetch_seasons is None or fetch_statcast is None or fetch_league_panel is None:
        # Lazy default to the data layer so tests can stub without importing it.
        from app.data import get_season_aggregates, get_statcast, get_leaderboard  # noqa: F401
        from app.data.aggregates import get_league_season

        fetch_seasons = fetch_seasons or (lambda pid, r, seasons: get_season_aggregates(pid, r, seasons))
        fetch_statcast = fetch_statcast or (lambda pid, r, s: get_statcast(pid, r, s))
        fetch_league_panel = fetch_league_panel or (lambda r, s: get_league_season(s, r))

    seasons = list(range(season - seasons_window + 1, season + 1))
    notes: list[str] = []

    # The data layer SHOULD already be tolerant (per-season failures skipped
    # internally), but wrap defensively: a hard exception here would surface
    # as a failed job and a confusing "Analysis failed" toast in the UI when
    # the more honest answer is "couldn't reach FanGraphs."
    try:
        seasons_df = fetch_seasons(player_id, role, seasons)
    except Exception as e:
        log.warning("fetch_seasons failed for player %s: %s", player_id, e)
        seasons_df = pd.DataFrame()
        notes.append(f"player_seasons_unavailable:{type(e).__name__}")

    if seasons_df is None or seasons_df.empty:
        if "empty_player_seasons" not in notes:
            notes.append("empty_player_seasons")
        return AnalysisReport(
            player_id=player_id,
            role=role,
            season=season,
            seasons_analyzed=seasons,
            findings=[],
            headline=(
                "Season-level data is unavailable for this player right now — "
                "FanGraphs is blocking our requests from this host. "
                "(Statcast pitch-level analysis is shown below if available.)"
            ),
            generated_at=datetime.utcnow().isoformat() + "Z",
            sample={},
            notes=notes,
        )

    # Build league panels for each season we have (used for league z-scores + SHAP).
    league_panels: dict[int, pd.DataFrame] = {}
    for s in seasons:
        try:
            panel = fetch_league_panel(role, s)
            if panel is not None and not panel.empty:
                league_panels[s] = panel
        except Exception as e:
            notes.append(f"league_panel_unavailable:{s}:{type(e).__name__}")

    # ----- Stage A: anomalies -----
    yoy = A.detect_yoy_anomalies(role, seasons_df, league_panels=league_panels)

    # In-season anomalies require pitch-level data; skip silently on failure.
    try:
        statcast = fetch_statcast(player_id, role, season)
    except Exception as e:
        statcast = pd.DataFrame()
        notes.append(f"statcast_unavailable:{type(e).__name__}")

    in_season = A.detect_in_season_anomalies(role, statcast)

    # Multivariate profile anomaly (latest season vs league).
    multivariate_anomaly = None
    latest_panel = league_panels.get(season)
    if latest_panel is not None and not seasons_df.empty:
        latest_player_row = seasons_df.sort_values("__season").iloc[-1]
        multivariate_anomaly = A.detect_multivariate_anomaly(role, latest_panel, latest_player_row)

    # ----- Stage B: attribution -----
    prior_row = seasons_df.sort_values("__season").iloc[-2] if len(seasons_df) >= 2 else None
    latest_row = seasons_df.sort_values("__season").iloc[-1] if len(seasons_df) >= 1 else None

    findings: list[AnomalyFinding] = []
    for an in yoy + in_season:
        causes: list[B.ProbableCause] = []
        if an.kind == "year_over_year" and prior_row is not None and latest_row is not None:
            causes = B.rank_probable_causes(
                role, an, prior_row, latest_row, league_panel=latest_panel,
            )
        elif an.kind == "changepoint" and prior_row is not None and latest_row is not None:
            # For changepoints we use the same season-level rows for driver context.
            # A future iteration can split statcast pre/post the changepoint.
            causes = B.rank_probable_causes(
                role, an, prior_row, latest_row, league_panel=latest_panel,
            )

        summary = _summarize_finding(role, an, causes)
        findings.append(AnomalyFinding(anomaly=an, probable_causes=causes, summary=summary))

    # ----- Sample-size context -----
    sample: dict = {}
    if latest_row is not None:
        for col in ("PA", "IP", "Pitches"):
            if col in latest_row.index and not pd.isna(latest_row[col]):
                try:
                    sample[col] = float(latest_row[col])
                except (TypeError, ValueError):
                    pass

    # ----- Headline -----
    headline = _headline(role, findings)

    return AnalysisReport(
        player_id=player_id,
        role=role,
        season=season,
        seasons_analyzed=seasons,
        findings=sorted(findings, key=lambda f: (
            -{"high": 3, "medium": 2, "low": 1}.get(f.anomaly.severity, 0),
            -abs(f.anomaly.z_score or 0),
        )),
        multivariate=multivariate_anomaly.to_dict() if multivariate_anomaly else None,
        headline=headline,
        generated_at=datetime.utcnow().isoformat() + "Z",
        sample=sample,
        notes=notes,
    )
