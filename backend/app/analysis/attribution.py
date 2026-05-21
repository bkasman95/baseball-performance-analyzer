"""Stage B — driver attribution ("probable causes").

For each detected outcome anomaly, identify which underlying driver metrics
most plausibly explain it. Three signals are combined:

  1. Delta ranking — standardized change in each candidate driver over the
     same period. Largest moves rank highest.
  2. Model-based attribution — train a gradient-boosted regressor on a
     league-season panel predicting the outcome from drivers; compute SHAP
     values and decompose the player's outcome delta into per-driver
     contributions.
  3. Domain rules (§6.3) — boost drivers that domain knowledge says SHOULD
     have moved when this outcome changed, and provide the sentence template.

Output: a ranked `ProbableCause` list per anomaly, each with before/after,
attribution weight, and a plain-language sentence.

Honesty: this is correlational. The function names use "probable" / "likely"
deliberately; the UI must match that wording.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from app.analysis.anomalies import Anomaly
from app.analysis.metrics import (
    Metric,
    Role,
    candidate_drivers,
    drivers_for,
    find_rule,
    get_metric,
    label_change,
    outcomes_for,
)


log = logging.getLogger(__name__)


@dataclass
class ProbableCause:
    driver: str
    before: float | None
    after: float | None
    delta: float | None
    standardized_delta: float | None
    attribution_weight: float        # 0..1, normalized within the anomaly
    direction: str                   # "improvement" | "regression" | "change"
    sentence: str
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "driver": self.driver,
            "before": self.before,
            "after": self.after,
            "delta": self.delta,
            "standardized_delta": self.standardized_delta,
            "attribution_weight": self.attribution_weight,
            "direction": self.direction,
            "sentence": self.sentence,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Driver deltas
# ---------------------------------------------------------------------------

def _value(metric: Metric, row: pd.Series) -> float | None:
    return metric.value_in(row)


def driver_deltas(
    role: Role,
    prior_row: pd.Series,
    latest_row: pd.Series,
    *,
    league_panel: pd.DataFrame | None = None,
) -> list[tuple[Metric, float, float, float, float]]:
    """For each driver metric, return (metric, before, after, raw_delta, std_delta).

    std_delta is the raw delta divided by the league-panel SD of that driver
    (when the panel is given), so deltas across heterogeneous drivers are
    comparable on a single scale.
    """
    out: list[tuple[Metric, float, float, float, float]] = []
    for metric in drivers_for(role):
        before = _value(metric, prior_row)
        after = _value(metric, latest_row)
        if before is None or after is None:
            continue
        raw = after - before
        std = raw
        if league_panel is not None:
            col = metric.column_in(league_panel)
            if col is not None:
                series = pd.to_numeric(league_panel[col], errors="coerce").dropna()
                sd = float(series.std()) if len(series) > 1 else 0.0
                if sd > 0:
                    std = raw / sd
        out.append((metric, before, after, raw, std))
    return out


# ---------------------------------------------------------------------------
# SHAP-based attribution (model-based)
# ---------------------------------------------------------------------------

def shap_attribution(
    role: Role,
    outcome: str,
    league_panel: pd.DataFrame,
    prior_row: pd.Series,
    latest_row: pd.Series,
) -> dict[str, float]:
    """Train a surrogate model on the league panel and return per-driver
    SHAP contribution to the *change* in the outcome between prior and latest.

    Returns {driver_name: shap_delta} mapping. Empty dict on any failure (we
    fall back to delta ranking + rule weighting in that case).
    """
    try:
        import shap
        from sklearn.ensemble import GradientBoostingRegressor
    except ImportError:
        log.warning("shap/sklearn unavailable; falling back to delta-only attribution")
        return {}

    outcome_metric = get_metric(role, outcome)
    if outcome_metric is None:
        return {}
    out_col = outcome_metric.column_in(league_panel)
    if out_col is None:
        return {}

    drivers = drivers_for(role)
    used_metrics: list[Metric] = []
    used_cols: list[str] = []
    for d in drivers:
        c = d.column_in(league_panel)
        if c is not None:
            used_metrics.append(d)
            used_cols.append(c)
    if len(used_cols) < 3:
        return {}

    panel = league_panel[used_cols + [out_col]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(panel) < 30:
        return {}

    X = panel[used_cols].to_numpy()
    y = panel[out_col].to_numpy()

    try:
        model = GradientBoostingRegressor(n_estimators=150, max_depth=3, random_state=42)
        model.fit(X, y)
    except Exception as e:
        log.warning("model fit failed for %s: %s", outcome, e)
        return {}

    def vec(row: pd.Series) -> np.ndarray | None:
        vals: list[float] = []
        for m, c in zip(used_metrics, used_cols):
            v = m.value_in(row)
            if v is None:
                v = row.get(c)
            if v is None or pd.isna(v):
                return None
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                return None
        return np.array(vals)

    x_prior = vec(prior_row)
    x_latest = vec(latest_row)
    if x_prior is None or x_latest is None:
        return {}

    try:
        explainer = shap.TreeExplainer(model)
        shap_prior = explainer.shap_values(x_prior.reshape(1, -1))[0]
        shap_latest = explainer.shap_values(x_latest.reshape(1, -1))[0]
    except Exception as e:
        log.warning("SHAP failed for %s: %s", outcome, e)
        return {}

    return {m.name: float(shap_latest[i] - shap_prior[i]) for i, m in enumerate(used_metrics)}


# ---------------------------------------------------------------------------
# Ranking + sentence generation
# ---------------------------------------------------------------------------

def _expected_direction_for_outcome_move(
    role: Role,
    outcome: str,
    outcome_dir: str,    # "up" or "down" (raw value)
) -> str | None:
    """For boosting drivers whose move sign is consistent with the rule map.

    Returns the SHAP sign we'd expect a 'matching' driver to have, or None
    when there's no rule (so no boost).
    """
    # If outcome moved "up" and outcome is bad-when-up (e.g., ERA), drivers
    # that PUSH it up should have positive SHAP contributions to outcome change.
    # We don't know per-driver sign from the rule map alone, so we just return
    # the outcome direction — caller boosts ANY non-trivial driver listed in
    # the rule map. This is intentionally simple.
    return outcome_dir


def _sentence_for(
    metric: Metric,
    before: float,
    after: float,
) -> str:
    direction = label_change(metric, before, after)
    verb = {
        "improvement": "improved",
        "regression": "worsened",
        "change": "shifted",
    }[direction]
    return f"{metric.name} {verb} from {before:.3f} to {after:.3f}."


def rank_probable_causes(
    role: Role,
    anomaly: Anomaly,
    prior_row: pd.Series,
    latest_row: pd.Series,
    *,
    league_panel: pd.DataFrame | None = None,
    max_causes: int = 5,
) -> list[ProbableCause]:
    """Combine delta ranking + SHAP + rule weighting into a single ranked list."""
    if anomaly.kind not in ("year_over_year", "changepoint"):
        return []

    deltas = driver_deltas(role, prior_row, latest_row, league_panel=league_panel)
    if not deltas:
        return []

    # Map driver -> standardized delta magnitude (for ranking).
    delta_score: dict[str, float] = {m.name: abs(std) for (m, _, _, _, std) in deltas}

    # SHAP contribution to outcome change.
    shap_map: dict[str, float] = {}
    if league_panel is not None and anomaly.kind == "year_over_year":
        shap_map = shap_attribution(role, anomaly.metric, league_panel, prior_row, latest_row)

    # Rule-map boost: drivers listed in the rule for (outcome, direction) get +1.
    outcome_dir = "up" if (anomaly.delta or 0) > 0 else "down"
    rule = find_rule(role, anomaly.metric, outcome_dir)
    rule_drivers = list(rule.drivers) if rule else []
    rule_priority = {name: (len(rule_drivers) - i) / len(rule_drivers) for i, name in enumerate(rule_drivers)} if rule_drivers else {}

    # Composite score:
    #   0.45 * normalized abs SHAP
    # + 0.35 * normalized abs standardized delta
    # + 0.20 * rule_priority (0..1)
    abs_shap = {k: abs(v) for k, v in shap_map.items()}
    max_shap = max(abs_shap.values(), default=0.0) or 1.0
    max_delta = max(delta_score.values(), default=0.0) or 1.0

    scored: list[tuple[float, Metric, float, float, float, float]] = []
    for (metric, before, after, raw, std) in deltas:
        s_shap = abs_shap.get(metric.name, 0.0) / max_shap
        s_delta = delta_score.get(metric.name, 0.0) / max_delta
        s_rule = rule_priority.get(metric.name, 0.0)
        score = 0.45 * s_shap + 0.35 * s_delta + 0.20 * s_rule
        scored.append((score, metric, before, after, raw, std))

    scored.sort(key=lambda t: t[0], reverse=True)

    # Normalize the top-K scores into attribution weights summing to 1.
    top = scored[:max_causes]
    total = sum(max(s, 0.0) for s, *_ in top) or 1.0

    out: list[ProbableCause] = []
    for (score, metric, before, after, raw, std) in top:
        out.append(
            ProbableCause(
                driver=metric.name,
                before=before,
                after=after,
                delta=raw,
                standardized_delta=std,
                attribution_weight=max(score, 0.0) / total,
                direction=label_change(metric, before, after),
                sentence=_sentence_for(metric, before, after),
                detail={
                    "composite_score": score,
                    "shap_delta": shap_map.get(metric.name),
                    "in_rule_map": metric.name in rule_drivers,
                },
            )
        )
    return out
