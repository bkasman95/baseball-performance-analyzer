import pandas as pd

from app.analysis import metrics as M


def test_pitcher_outcomes_include_core_set():
    names = {m.name for m in M.outcomes_for("pitcher")}
    assert {"ERA", "FIP", "WHIP", "K%", "BB%", "HR/9", "wOBA", "HardHit%"} <= names


def test_hitter_outcomes_include_core_set():
    names = {m.name for m in M.outcomes_for("hitter")}
    assert {"AVG", "OBP", "SLG", "OPS", "wOBA", "wRC+", "ISO", "K%", "BB%"} <= names


def test_direction_is_set_for_every_metric():
    for m in (*M.PITCHER_METRICS, *M.HITTER_METRICS):
        assert m.direction in {"higher_is_better", "lower_is_better", "neutral"}


def test_label_change_respects_direction():
    era = M.get_metric("pitcher", "ERA")
    k_pct_p = M.get_metric("pitcher", "K%")
    assert M.label_change(era, 3.10, 4.85) == "regression"     # ERA up = bad
    assert M.label_change(era, 4.85, 3.10) == "improvement"
    assert M.label_change(k_pct_p, 0.20, 0.28) == "improvement"
    assert M.label_change(k_pct_p, 0.28, 0.20) == "regression"


def test_metric_value_in_handles_aliases():
    velocity = M.get_metric("pitcher", "FB_velocity")
    row_a = pd.Series({"FBv": 95.4})
    row_b = pd.Series({"fb_velocity": 95.4})
    row_c = pd.Series({})
    assert velocity.value_in(row_a) == 95.4
    assert velocity.value_in(row_b) == 95.4
    assert velocity.value_in(row_c) is None


def test_confidence_for_sample_thresholds():
    assert M.confidence_for_sample("hitter", pa=150) == "high"
    assert M.confidence_for_sample("hitter", pa=80) == "low"
    assert M.confidence_for_sample("pitcher", ip=50) == "high"
    assert M.confidence_for_sample("pitcher", ip=10, pitches=700) == "high"
    assert M.confidence_for_sample("pitcher", ip=10, pitches=100) == "low"


def test_find_rule_returns_drivers_for_known_outcomes():
    rule = M.find_rule("pitcher", "ERA", "up")
    assert rule is not None
    assert "FB_velocity" in rule.drivers
    assert "HardHit%" in rule.drivers
    rule2 = M.find_rule("hitter", "AVG", "down")
    assert rule2 is not None
    assert "O-Swing%" in rule2.drivers


def test_find_rule_returns_none_for_unknown():
    assert M.find_rule("pitcher", "ERA", "down") is None  # no rule for ERA dropping
