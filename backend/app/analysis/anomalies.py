"""Stage A — anomaly detection.

Three modes:
  A1. Year-over-year robust z-scores (player history + league context).
  A2. In-season changepoints via `ruptures` PELT on rolling outcome series.
  A3. Multivariate Isolation Forest on the driver-vector profile.

All findings carry a confidence label that respects the sample-size
guardrails in metrics.SAMPLE.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Literal

import numpy as np
import pandas as pd

from app.analysis.metrics import (
    Metric,
    Role,
    SAMPLE,
    confidence_for_sample,
    label_change,
    outcomes_for,
    drivers_for,
)


log = logging.getLogger(__name__)


AnomalyKind = Literal["year_over_year", "changepoint", "multivariate"]
Severity = Literal["low", "medium", "high"]
Confidence = Literal["low", "high"]


# ---------------------------------------------------------------------------
# Anomaly record
# ---------------------------------------------------------------------------

@dataclass
class Anomaly:
    metric: str
    kind: AnomalyKind
    season: int | None
    before: float | None
    after: float | None
    delta: float | None
    z_score: float | None
    severity: Severity
    direction: Literal["improvement", "regression", "change"]
    confidence: Confidence
    period: str | None = None       # human-readable time frame: "2023 → 2024" or "mid-2024"
    before_period: str | None = None  # e.g. "2023"
    after_period: str | None = None   # e.g. "2024"
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "kind": self.kind,
            "season": self.season,
            "before": self.before,
            "after": self.after,
            "delta": self.delta,
            "z_score": self.z_score,
            "severity": self.severity,
            "direction": self.direction,
            "confidence": self.confidence,
            "period": self.period,
            "before_period": self.before_period,
            "after_period": self.after_period,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Robust stats — median/MAD-based z so one wild season doesn't dominate
# ---------------------------------------------------------------------------

_MAD_TO_SD = 1.4826  # consistency constant: MAD * 1.4826 ≈ sigma for normal data


def robust_z(value: float, series: Iterable[float]) -> float | None:
    """Robust z-score of `value` against the distribution `series`.

    Returns None when MAD is zero (no spread → can't z-score) or series is empty.
    """
    arr = np.asarray([x for x in series if x is not None and not np.isnan(x)], dtype=float)
    if arr.size == 0:
        return None
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    if mad == 0:
        return None
    return (value - med) / (_MAD_TO_SD * mad)


def _severity_from_z(z: float) -> Severity:
    az = abs(z)
    if az >= 3.0:
        return "high"
    if az >= 2.0:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# A1 — Year-over-year anomalies on outcome metrics
# ---------------------------------------------------------------------------

def _player_sample_for_season(role: Role, row: pd.Series) -> tuple[float | None, float | None, int | None]:
    """Extract (PA, IP, pitches) from a FanGraphs row, missing fields → None."""
    def g(col: str) -> float | None:
        if col in row.index and not pd.isna(row[col]):
            try:
                return float(row[col])
            except (TypeError, ValueError):
                return None
        return None
    return g("PA"), g("IP"), g("Pitches")


def detect_yoy_anomalies(
    role: Role,
    player_seasons: pd.DataFrame,
    *,
    league_panels: dict[int, pd.DataFrame] | None = None,
    min_z: float = 2.0,
    min_relative_delta: float = 0.10,
) -> list[Anomaly]:
    """Year-over-year anomaly detection.

    `player_seasons` must have one row per season for THIS player, plus a
    `__season` column (int) added by the data layer.

    `league_panels` (optional) maps season -> league-wide DataFrame for that
    season; used to z-score against the league for the comparison season.

    A finding is emitted when the YoY change is large in BOTH absolute
    z-score terms AND relative-to-baseline terms.
    """
    if player_seasons.empty or "__season" not in player_seasons.columns:
        return []

    df = player_seasons.sort_values("__season").reset_index(drop=True)
    if len(df) < 2:
        return []

    anomalies: list[Anomaly] = []

    for metric in outcomes_for(role):
        col = metric.column_in(df)
        if col is None:
            continue

        # Robust baseline from the player's OWN history (all but the most recent season).
        history = df[col].iloc[:-1].dropna().tolist()
        if len(history) < 2:
            # Fall back to comparing only against immediate prior season.
            history = df[col].iloc[:-1].dropna().tolist()

        latest_row = df.iloc[-1]
        latest = metric.value_in(latest_row)
        prior_row = df.iloc[-2]
        prior = metric.value_in(prior_row)
        if latest is None or prior is None:
            continue

        delta = latest - prior
        rel = abs(delta) / abs(prior) if prior not in (0, None) else float("inf")

        # Player-history z
        z_player = robust_z(latest, history) if history else None

        # League z (against the latest season's league distribution)
        z_league = None
        if league_panels:
            season = int(latest_row["__season"]) if pd.notna(latest_row["__season"]) else None
            if season is not None and season in league_panels:
                league_df = league_panels[season]
                if col in league_df.columns:
                    z_league = robust_z(latest, league_df[col].dropna().tolist())

        # Use whichever z is larger in magnitude (i.e., more anomalous against
        # either the player or the league).
        candidates = [z for z in (z_player, z_league) if z is not None]
        if not candidates:
            continue
        z = max(candidates, key=abs)

        if abs(z) < min_z and rel < min_relative_delta:
            continue
        if abs(z) < min_z * 0.6 and rel < min_relative_delta:
            continue
        if abs(z) < min_z and rel < min_relative_delta * 2:
            continue

        pa, ip, pitches = _player_sample_for_season(role, latest_row)
        confidence = confidence_for_sample(role, pa=pa, ip=ip, pitches=int(pitches) if pitches else None)

        latest_season = (
            int(latest_row["__season"]) if pd.notna(latest_row.get("__season")) else None
        )
        prior_season = (
            int(prior_row["__season"]) if pd.notna(prior_row.get("__season")) else None
        )
        before_period = str(prior_season) if prior_season is not None else None
        after_period = str(latest_season) if latest_season is not None else None
        period = (
            f"{before_period} → {after_period}"
            if before_period and after_period
            else None
        )

        anomalies.append(
            Anomaly(
                metric=metric.name,
                kind="year_over_year",
                season=latest_season,
                before=prior,
                after=latest,
                delta=delta,
                z_score=float(z),
                severity=_severity_from_z(z),
                direction=label_change(metric, prior, latest),
                confidence=confidence,
                period=period,
                before_period=before_period,
                after_period=after_period,
                detail={
                    "z_player": z_player,
                    "z_league": z_league,
                    "relative_delta": rel,
                    "history_n": len(history),
                    "column": col,
                },
            )
        )
    return anomalies


# ---------------------------------------------------------------------------
# A2 — In-season changepoints (PELT via `ruptures`)
# ---------------------------------------------------------------------------

def detect_changepoints(
    series: pd.Series,
    *,
    pen: float = 3.0,
    min_size: int | None = None,
) -> list[int]:
    """Return integer indices where the level of `series` shifts.

    `series` should be a numeric pd.Series indexed by game date or event order.
    Returns indices of detected changepoints (excluding the trailing endpoint
    that ruptures always emits).
    """
    arr = pd.Series(series).dropna().to_numpy(dtype=float)
    if min_size is None:
        min_size = SAMPLE.min_rolling_window
    if arr.size < max(2 * min_size, 10):
        return []

    try:
        import ruptures as rpt
    except ImportError:
        log.warning("ruptures not installed; skipping changepoint detection")
        return []

    algo = rpt.Pelt(model="rbf", min_size=min_size).fit(arr.reshape(-1, 1))
    # ruptures returns the END of each segment; drop the last (== len(arr)).
    bkps = algo.predict(pen=pen)
    return [int(b) for b in bkps if b < arr.size]


def rolling_outcome_series(
    statcast_df: pd.DataFrame,
    metric_col: str,
    *,
    window: int = 30,
) -> pd.Series:
    """Compute a rolling per-event mean of `metric_col`, ordered by date.

    Generic enough to work for pitcher (estimated_woba_using_speedangle) or
    hitter outcomes. Assumes `statcast_df` has a `game_date` column.
    """
    if statcast_df.empty or metric_col not in statcast_df.columns:
        return pd.Series(dtype=float)
    df = statcast_df.dropna(subset=[metric_col]).copy()
    if "game_date" in df.columns:
        df = df.sort_values("game_date")
    return df[metric_col].astype(float).rolling(window=window, min_periods=window).mean()


def detect_in_season_anomalies(
    role: Role,
    statcast_df: pd.DataFrame,
    *,
    metric_col_for_outcome: dict[str, str] | None = None,
    window: int = 30,
) -> list[Anomaly]:
    """Run PELT changepoint detection on rolling Statcast outcome series.

    The mapping `metric_col_for_outcome` lets callers point each outcome at
    the right Statcast column (e.g. wOBA → "estimated_woba_using_speedangle").
    """
    if statcast_df.empty:
        return []

    # Reasonable defaults that work on Statcast schemas.
    defaults_pitcher = {
        "wOBA": "estimated_woba_using_speedangle",
        "HardHit%": "launch_speed",  # rolling mean exit velo as a proxy for hard contact trend
    }
    defaults_hitter = {
        "wOBA": "estimated_woba_using_speedangle",
        "EV": "launch_speed",
    }
    mapping = metric_col_for_outcome or (defaults_pitcher if role == "pitcher" else defaults_hitter)

    # Build a parallel game_date series so we can map changepoint indices
    # back to actual dates for human-readable period labels.
    df_sorted = statcast_df.copy()
    if "game_date" in df_sorted.columns:
        df_sorted = df_sorted.sort_values("game_date")

    anomalies: list[Anomaly] = []
    for outcome_name, col in mapping.items():
        series = rolling_outcome_series(statcast_df, col, window=window)
        if series.empty:
            continue
        bkps = detect_changepoints(series)
        if not bkps:
            continue

        # Parallel ordered series of dates (after the same dropna+sort) so we
        # can label the changepoint with a real date.
        dates = None
        if "game_date" in df_sorted.columns:
            dates = (
                df_sorted.dropna(subset=[col])
                .sort_values("game_date")["game_date"]
                .reset_index(drop=True)
            )

        # For each break, compute pre/post means and z against the surrounding window.
        s = series.dropna().reset_index(drop=True)
        for bk in bkps:
            if bk <= 0 or bk >= len(s):
                continue
            pre = s.iloc[max(0, bk - window):bk]
            post = s.iloc[bk:min(len(s), bk + window)]
            if len(pre) < 5 or len(post) < 5:
                continue
            before = float(pre.mean())
            after = float(post.mean())
            delta = after - before
            z = robust_z(after, pre.tolist())
            if z is None:
                continue
            if abs(z) < 2.0:
                continue

            # Map outcome to direction. We use the league-side metric registry.
            metric = next((m for m in outcomes_for(role) if m.name == outcome_name), None)
            if metric is None:
                continue

            season = _season_of(statcast_df)
            changepoint_date = None
            before_period = None
            after_period = None
            period = None
            if dates is not None and bk < len(dates):
                try:
                    changepoint_date = str(pd.to_datetime(dates.iloc[bk]).date())
                    pre_start = pd.to_datetime(dates.iloc[max(0, bk - window)]).date()
                    pre_end   = pd.to_datetime(dates.iloc[bk - 1]).date()
                    post_start = pd.to_datetime(dates.iloc[bk]).date()
                    post_end   = pd.to_datetime(dates.iloc[min(len(dates) - 1, bk + window - 1)]).date()
                    before_period = f"{pre_start} – {pre_end}"
                    after_period  = f"{post_start} – {post_end}"
                    period = f"Within {season} season — shift on {changepoint_date}"
                except Exception:
                    pass
            if period is None and season is not None:
                period = f"Within {season} season — mid-season shift"

            anomalies.append(
                Anomaly(
                    metric=outcome_name,
                    kind="changepoint",
                    season=season,
                    before=before,
                    after=after,
                    delta=delta,
                    z_score=z,
                    severity=_severity_from_z(z),
                    direction=label_change(metric, before, after),
                    confidence="high" if len(s) >= SAMPLE.min_rolling_window * 3 else "low",
                    period=period,
                    before_period=before_period,
                    after_period=after_period,
                    detail={
                        "changepoint_index": int(bk),
                        "changepoint_date": changepoint_date,
                        "window": window,
                        "statcast_column": col,
                        "n_events": int(len(s)),
                    },
                )
            )
    return anomalies


def _season_of(df: pd.DataFrame) -> int | None:
    if "game_date" not in df.columns or df.empty:
        return None
    try:
        return int(pd.to_datetime(df["game_date"]).dt.year.iloc[0])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# A3 — Multivariate Isolation Forest on driver-vector profile
# ---------------------------------------------------------------------------

def detect_multivariate_anomaly(
    role: Role,
    league_panel: pd.DataFrame,
    player_row: pd.Series,
    *,
    contamination: float = 0.05,
) -> Anomaly | None:
    """Fit IsolationForest on the league panel of driver metrics, score this
    player. A high anomaly score means the player's overall profile is
    unusual even if no single headline metric tripped a threshold.
    """
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        log.warning("scikit-learn not installed; skipping multivariate anomaly")
        return None

    drivers = drivers_for(role)
    cols: list[str] = []
    for d in drivers:
        c = d.column_in(league_panel)
        if c is not None:
            cols.append(c)
    if len(cols) < 5:
        return None

    panel = league_panel[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(panel) < 30:
        return None

    # Player's vector
    player_vec_list = []
    for c in cols:
        v = player_row.get(c)
        if v is None or pd.isna(v):
            return None
        try:
            player_vec_list.append(float(v))
        except (TypeError, ValueError):
            return None

    iso = IsolationForest(contamination=contamination, random_state=42, n_estimators=200)
    iso.fit(panel.to_numpy())
    score = float(iso.score_samples(np.array(player_vec_list).reshape(1, -1))[0])
    # lower score == more anomalous; flip sign for intuitiveness.
    anomaly_score = -score

    # Heuristic mapping to severity.
    if anomaly_score >= 0.7:
        severity: Severity = "high"
    elif anomaly_score >= 0.55:
        severity = "medium"
    else:
        severity = "low"

    # Best-effort season from the row; multivariate doesn't have an explicit
    # before/after but we can still tag which season's profile we scored.
    profile_season: int | None = None
    if "__season" in player_row.index and not pd.isna(player_row["__season"]):
        try:
            profile_season = int(player_row["__season"])
        except (TypeError, ValueError):
            profile_season = None

    return Anomaly(
        metric="profile",
        kind="multivariate",
        season=profile_season,
        before=None,
        after=None,
        delta=None,
        z_score=None,
        severity=severity,
        direction="change",
        confidence="high" if len(panel) >= 100 else "low",
        period=f"Full {profile_season} season profile vs league" if profile_season else "Profile vs league",
        detail={
            "anomaly_score": anomaly_score,
            "iforest_raw_score": score,
            "features": cols,
            "panel_size": int(len(panel)),
            "contamination": contamination,
        },
    )
