"""Metric catalog — the domain source of truth (§6 of the spec).

Maps human metric names to the FanGraphs / Statcast column names that
pybaseball returns. Column names drift between pybaseball versions, so every
metric has a list of `aliases` — the first column that exists in the input
DataFrame wins.

Also defines:
  * direction map: "up is good" vs "up is bad" — needed to label spikes as
    improvement vs regression in the UI.
  * outcome vs driver classification — outcomes get anomaly-detected, drivers
    are inspected for attribution.
  * rule map (§6.3): outcome change → ranked driver list + sentence templates.
  * sample-size thresholds: minimum IP/PA before a finding is "high confidence."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

import pandas as pd


Role = Literal["pitcher", "hitter"]
Direction = Literal["higher_is_better", "lower_is_better", "neutral"]


# ---------------------------------------------------------------------------
# Metric definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Metric:
    name: str                       # canonical name, e.g. "ERA"
    role: Role | Literal["both"]
    kind: Literal["outcome", "driver"]
    direction: Direction
    aliases: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""

    def value_in(self, row: pd.Series) -> float | None:
        """Return this metric's value from a single row (or None if missing)."""
        for alias in self.aliases or (self.name,):
            if alias in row.index:
                v = row[alias]
                if pd.isna(v):
                    continue
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return None

    def column_in(self, df: pd.DataFrame) -> str | None:
        """First alias present in this DataFrame, or None."""
        for alias in self.aliases or (self.name,):
            if alias in df.columns:
                return alias
        return None


# ---------------------------------------------------------------------------
# Pitcher metrics
# ---------------------------------------------------------------------------
# Pitcher outcomes get anomaly-detected year-over-year and in-season. Drivers
# are inspected during attribution. Direction is from the PITCHER's
# perspective: ERA lower is better; K% higher is better.

PITCHER_METRICS: tuple[Metric, ...] = (
    # ---- outcomes ----
    Metric("ERA", "pitcher", "outcome", "lower_is_better", ("ERA",)),
    Metric("FIP", "pitcher", "outcome", "lower_is_better", ("FIP",)),
    Metric("xERA", "pitcher", "outcome", "lower_is_better", ("xERA",)),
    Metric("xFIP", "pitcher", "outcome", "lower_is_better", ("xFIP",)),
    Metric("WHIP", "pitcher", "outcome", "lower_is_better", ("WHIP",)),
    Metric("K%", "pitcher", "outcome", "higher_is_better", ("K%", "K_pct", "k_percent")),
    Metric("BB%", "pitcher", "outcome", "lower_is_better", ("BB%", "BB_pct")),
    Metric("K-BB%", "pitcher", "outcome", "higher_is_better", ("K-BB%", "K_minus_BB_pct")),
    Metric("HR/9", "pitcher", "outcome", "lower_is_better", ("HR/9",)),
    Metric("BABIP", "pitcher", "outcome", "neutral", ("BABIP",), "BABIP-against; mostly luck."),
    Metric("LOB%", "pitcher", "outcome", "higher_is_better", ("LOB%",)),
    Metric("AVG", "pitcher", "outcome", "lower_is_better", ("AVG",), "AVG against"),
    Metric("wOBA", "pitcher", "outcome", "lower_is_better", ("wOBA",), "wOBA against"),
    Metric("HardHit%", "pitcher", "outcome", "lower_is_better", ("HardHit%", "Hard%", "hard_hit_percent")),
    Metric("Barrel%", "pitcher", "outcome", "lower_is_better", ("Barrel%", "barrel_batted_rate")),
    Metric("CSW%", "pitcher", "outcome", "higher_is_better", ("CSW%",)),
    # ---- drivers ----
    Metric("FB_velocity", "pitcher", "driver", "higher_is_better",
           ("FBv", "FBv (sc)", "fb_velocity"), "Avg four-seam fastball velocity"),
    Metric("FB_spin", "pitcher", "driver", "neutral",
           ("FBspin (sc)", "Spin (sc)", "fb_spin_rate"), "Avg fastball spin rate"),
    Metric("Release_height", "pitcher", "driver", "neutral",
           ("Release_height", "release_pos_z"), "Vertical release point"),
    Metric("Release_side", "pitcher", "driver", "neutral",
           ("Release_side", "release_pos_x"), "Horizontal release point"),
    Metric("Extension", "pitcher", "driver", "higher_is_better",
           ("Extension", "release_extension")),
    Metric("FB_pitch_pct", "pitcher", "driver", "neutral",
           ("FB%", "FB% (sc)"), "Four-seam usage rate"),
    Metric("SL_pitch_pct", "pitcher", "driver", "neutral",
           ("SL%", "SL% (sc)"), "Slider usage rate"),
    Metric("CH_pitch_pct", "pitcher", "driver", "neutral",
           ("CH%", "CH% (sc)"), "Changeup usage rate"),
    Metric("CB_pitch_pct", "pitcher", "driver", "neutral",
           ("CB%", "CB% (sc)", "CU%"), "Curveball usage rate"),
    Metric("Zone%", "pitcher", "driver", "higher_is_better",
           ("Zone%", "Zone% (sc)")),
    Metric("F-Strike%", "pitcher", "driver", "higher_is_better",
           ("F-Strike%", "FStrike%")),
    Metric("O-Swing%", "pitcher", "driver", "higher_is_better",
           ("O-Swing%", "OSwing% (sc)"), "Chase rate induced"),
    Metric("SwStr%", "pitcher", "driver", "higher_is_better",
           ("SwStr%",)),
)


# ---------------------------------------------------------------------------
# Hitter metrics
# ---------------------------------------------------------------------------

HITTER_METRICS: tuple[Metric, ...] = (
    # ---- outcomes ----
    Metric("AVG", "hitter", "outcome", "higher_is_better", ("AVG",)),
    Metric("OBP", "hitter", "outcome", "higher_is_better", ("OBP",)),
    Metric("SLG", "hitter", "outcome", "higher_is_better", ("SLG",)),
    Metric("OPS", "hitter", "outcome", "higher_is_better", ("OPS",)),
    Metric("wOBA", "hitter", "outcome", "higher_is_better", ("wOBA",)),
    Metric("xwOBA", "hitter", "outcome", "higher_is_better", ("xwOBA",)),
    Metric("wRC+", "hitter", "outcome", "higher_is_better", ("wRC+",)),
    Metric("ISO", "hitter", "outcome", "higher_is_better", ("ISO",)),
    Metric("K%", "hitter", "outcome", "lower_is_better", ("K%", "K_pct")),
    Metric("BB%", "hitter", "outcome", "higher_is_better", ("BB%", "BB_pct")),
    Metric("BABIP", "hitter", "outcome", "neutral", ("BABIP",)),
    # ---- drivers ----
    Metric("Bat_speed", "hitter", "driver", "higher_is_better",
           ("avg_bat_speed", "Bat Speed", "bat_speed")),
    Metric("Swing_length", "hitter", "driver", "neutral",
           ("avg_swing_length", "Swing Length", "swing_length")),
    Metric("Squared_up_pct", "hitter", "driver", "higher_is_better",
           ("squared_up_per_swing", "Squared Up%", "squared_up_pct")),
    Metric("O-Swing%", "hitter", "driver", "lower_is_better",
           ("O-Swing%", "OSwing% (sc)"), "Chase rate"),
    Metric("SwStr%", "hitter", "driver", "lower_is_better", ("SwStr%",)),
    Metric("Contact%", "hitter", "driver", "higher_is_better", ("Contact%", "Contact% (sc)")),
    Metric("Z-Contact%", "hitter", "driver", "higher_is_better", ("Z-Contact%", "ZContact% (sc)")),
    Metric("Whiff%", "hitter", "driver", "lower_is_better", ("Whiff%", "whiff_percent")),
    Metric("EV", "hitter", "driver", "higher_is_better",
           ("EV", "avg_hit_speed", "exit_velocity_avg")),
    Metric("MaxEV", "hitter", "driver", "higher_is_better",
           ("maxEV", "max_hit_speed", "exit_velocity_max")),
    Metric("HardHit%", "hitter", "driver", "higher_is_better",
           ("HardHit%", "Hard%", "hard_hit_percent")),
    Metric("Barrel%", "hitter", "driver", "higher_is_better",
           ("Barrel%", "barrel_batted_rate")),
    Metric("LA", "hitter", "driver", "neutral",
           ("LA", "launch_angle_avg")),
    Metric("Pull%", "hitter", "driver", "neutral", ("Pull%",)),
    Metric("Oppo%", "hitter", "driver", "neutral", ("Oppo%",)),
    Metric("GB%", "hitter", "driver", "neutral", ("GB%",)),
    Metric("FB%", "hitter", "driver", "neutral", ("FB%",)),
    Metric("LD%", "hitter", "driver", "higher_is_better", ("LD%",)),
)


_ALL_METRICS: dict[str, Metric] = {
    **{m.name: m for m in PITCHER_METRICS},
    # Hitter metrics overwrite pitcher entries where names collide (e.g. AVG, wOBA);
    # call sites filter by role so this is fine — but to look up uniquely we
    # prefix collisions:
}
# Build a (role, name) keyed map so lookups don't collide between roles.
_ROLE_KEYED: dict[tuple[Role, str], Metric] = {}
for m in PITCHER_METRICS:
    _ROLE_KEYED[("pitcher", m.name)] = m
for m in HITTER_METRICS:
    _ROLE_KEYED[("hitter", m.name)] = m


def metrics_for(role: Role) -> tuple[Metric, ...]:
    return PITCHER_METRICS if role == "pitcher" else HITTER_METRICS


def outcomes_for(role: Role) -> tuple[Metric, ...]:
    return tuple(m for m in metrics_for(role) if m.kind == "outcome")


def drivers_for(role: Role) -> tuple[Metric, ...]:
    return tuple(m for m in metrics_for(role) if m.kind == "driver")


def get_metric(role: Role, name: str) -> Metric | None:
    return _ROLE_KEYED.get((role, name))


# ---------------------------------------------------------------------------
# Direction-aware delta labeling
# ---------------------------------------------------------------------------

def label_change(metric: Metric, before: float, after: float) -> Literal["improvement", "regression", "change"]:
    """Map raw delta to improvement/regression based on the metric's direction."""
    if metric.direction == "neutral":
        return "change"
    delta = after - before
    if delta == 0:
        return "change"
    if metric.direction == "higher_is_better":
        return "improvement" if delta > 0 else "regression"
    return "improvement" if delta < 0 else "regression"


# ---------------------------------------------------------------------------
# Sample-size guardrails (§5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SampleThresholds:
    min_pa_hitter: int = 120
    min_ip_pitcher: float = 40.0
    min_pitches_pitcher: int = 600
    min_rolling_window: int = 20    # min observations before in-season flagging


SAMPLE = SampleThresholds()


def confidence_for_sample(role: Role, *, pa: float | None = None,
                          ip: float | None = None, pitches: int | None = None) -> Literal["high", "low"]:
    if role == "hitter":
        return "high" if (pa is not None and pa >= SAMPLE.min_pa_hitter) else "low"
    # pitcher
    ok_ip = ip is not None and ip >= SAMPLE.min_ip_pitcher
    ok_p = pitches is not None and pitches >= SAMPLE.min_pitches_pitcher
    return "high" if (ok_ip or ok_p) else "low"


# ---------------------------------------------------------------------------
# Driver rule map (§6.3) — outcome change → which drivers to inspect
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriverRule:
    """When `outcome` moves in `outcome_direction`, inspect these drivers."""
    role: Role
    outcome: str
    outcome_direction: Literal["up", "down"]     # of the raw value
    drivers: tuple[str, ...]                     # ranked priority
    sentence_template: str                       # uses {outcome}, {drivers}


PITCHER_RULES: tuple[DriverRule, ...] = (
    DriverRule(
        "pitcher", "ERA", "up",
        ("FB_velocity", "FB_spin", "HardHit%", "Barrel%", "Zone%",
         "F-Strike%", "FB_pitch_pct", "SL_pitch_pct", "Release_height", "Release_side"),
        "{outcome} rose; the leading drivers appear to be {drivers}.",
    ),
    DriverRule(
        "pitcher", "WHIP", "up",
        ("BB%", "Zone%", "F-Strike%", "O-Swing%", "FB_velocity", "HardHit%"),
        "{outcome} climbed; likely contributors are {drivers}.",
    ),
    DriverRule(
        "pitcher", "wOBA", "up",
        ("HardHit%", "Barrel%", "FB_velocity", "FB_spin", "Zone%", "FB_pitch_pct"),
        "Opponent wOBA jumped; the most prominent shifts are in {drivers}.",
    ),
    DriverRule(
        "pitcher", "K%", "down",
        ("SwStr%", "O-Swing%", "FB_velocity", "CSW%", "FB_pitch_pct", "SL_pitch_pct"),
        "Strikeout rate fell; the likely drivers are {drivers}.",
    ),
    DriverRule(
        "pitcher", "HardHit%", "up",
        ("FB_velocity", "FB_spin", "Zone%", "FB_pitch_pct", "Release_height"),
        "HardHit% against rose; check {drivers}.",
    ),
)


HITTER_RULES: tuple[DriverRule, ...] = (
    DriverRule(
        "hitter", "AVG", "down",
        ("Bat_speed", "O-Swing%", "Whiff%", "Contact%", "EV", "HardHit%", "LA"),
        "Average dropped; the most likely drivers are {drivers}.",
    ),
    DriverRule(
        "hitter", "wOBA", "down",
        ("EV", "HardHit%", "Barrel%", "Bat_speed", "O-Swing%", "Whiff%", "LA"),
        "wOBA fell; the leading shifts are in {drivers}.",
    ),
    DriverRule(
        "hitter", "OPS", "down",
        ("EV", "HardHit%", "Barrel%", "Bat_speed", "O-Swing%", "Whiff%"),
        "OPS dropped; the prominent changes are in {drivers}.",
    ),
    DriverRule(
        "hitter", "K%", "up",
        ("O-Swing%", "Whiff%", "Contact%", "Z-Contact%", "Bat_speed", "SwStr%"),
        "Strikeout rate climbed; likely drivers are {drivers}.",
    ),
    DriverRule(
        "hitter", "ISO", "down",
        ("EV", "Barrel%", "LA", "Pull%", "Bat_speed", "HardHit%"),
        "Power dropped; the leading factors are {drivers}.",
    ),
    DriverRule(
        "hitter", "SLG", "down",
        ("EV", "Barrel%", "HardHit%", "LA", "Pull%", "Bat_speed"),
        "Slugging dropped; the leading factors are {drivers}.",
    ),
)


def find_rule(role: Role, outcome: str, direction: Literal["up", "down"]) -> DriverRule | None:
    rules = PITCHER_RULES if role == "pitcher" else HITTER_RULES
    for r in rules:
        if r.outcome == outcome and r.outcome_direction == direction:
            return r
    return None


def candidate_drivers(role: Role) -> tuple[str, ...]:
    return tuple(m.name for m in drivers_for(role))


__all__ = [
    "Metric",
    "Role",
    "Direction",
    "PITCHER_METRICS",
    "HITTER_METRICS",
    "metrics_for",
    "outcomes_for",
    "drivers_for",
    "get_metric",
    "label_change",
    "SampleThresholds",
    "SAMPLE",
    "confidence_for_sample",
    "DriverRule",
    "PITCHER_RULES",
    "HITTER_RULES",
    "find_rule",
    "candidate_drivers",
]
