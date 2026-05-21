import numpy as np
import pandas as pd

from app.analysis import anomalies as A


def test_robust_z_returns_none_for_zero_mad():
    assert A.robust_z(5.0, [1.0, 1.0, 1.0, 1.0]) is None


def test_robust_z_flags_outliers():
    series = [3.10, 3.20, 3.05, 3.15, 2.95]
    z = A.robust_z(4.80, series)
    assert z is not None and z > 3.0


def _pitcher_seasons() -> pd.DataFrame:
    return pd.DataFrame({
        "__season": [2020, 2021, 2022, 2023, 2024],
        "ERA":      [3.10, 3.05, 3.25, 3.15, 4.85],
        "WHIP":     [1.10, 1.08, 1.12, 1.09, 1.31],
        "K%":       [0.27, 0.28, 0.26, 0.27, 0.21],
        "HardHit%": [0.32, 0.31, 0.33, 0.32, 0.40],
        "FBv":      [95.4, 95.3, 95.0, 94.8, 92.9],
        "PA":       [800, 820, 790, 810, 760],  # ignored for pitcher
        "IP":       [180, 185, 175, 190, 170],
    })


def test_detect_yoy_anomalies_flags_spike_in_era():
    df = _pitcher_seasons()
    anomalies = A.detect_yoy_anomalies("pitcher", df)
    metrics_flagged = {a.metric for a in anomalies}
    assert "ERA" in metrics_flagged
    # ERA going up is a regression for a pitcher.
    era_anom = next(a for a in anomalies if a.metric == "ERA")
    assert era_anom.direction == "regression"
    assert era_anom.before == 3.15
    assert era_anom.after == 4.85
    assert era_anom.severity in ("medium", "high")
    assert era_anom.confidence == "high"   # IP=170 > 40 threshold


def test_detect_yoy_anomalies_returns_empty_for_short_history():
    df = pd.DataFrame({"__season": [2024], "ERA": [3.10], "IP": [180]})
    assert A.detect_yoy_anomalies("pitcher", df) == []


def test_detect_changepoints_finds_known_break():
    # Flat at 0.300, then jump to 0.380
    series = pd.Series([0.30] * 60 + [0.38] * 60)
    bkps = A.detect_changepoints(series, min_size=10)
    assert bkps, "should detect at least one changepoint"
    # The break should be near index 60.
    assert any(50 <= b <= 70 for b in bkps)


def test_detect_changepoints_skips_short_series():
    assert A.detect_changepoints(pd.Series([0.3] * 5)) == []


def test_detect_multivariate_anomaly_returns_none_on_thin_panel():
    # Tiny league panel; should refuse rather than fabricate.
    panel = pd.DataFrame({"FBv": [95, 94, 93], "Zone%": [0.5, 0.51, 0.49]})
    player = pd.Series({"FBv": 93, "Zone%": 0.5})
    out = A.detect_multivariate_anomaly("pitcher", panel, player)
    assert out is None


def test_detect_multivariate_anomaly_runs_with_sufficient_panel():
    rng = np.random.default_rng(42)
    n = 200
    panel = pd.DataFrame({
        "FBv": rng.normal(94.0, 1.0, n),
        "FBspin (sc)": rng.normal(2300, 100, n),
        "Release_height": rng.normal(6.0, 0.2, n),
        "Release_side": rng.normal(-1.5, 0.3, n),
        "Extension": rng.normal(6.5, 0.3, n),
        "Zone%": rng.normal(0.5, 0.03, n),
    })
    # Make an extreme outlier player
    player = pd.Series({
        "FBv": 88.0,
        "FBspin (sc)": 1800,
        "Release_height": 7.5,
        "Release_side": -2.5,
        "Extension": 5.0,
        "Zone%": 0.30,
    })
    out = A.detect_multivariate_anomaly("pitcher", panel, player)
    assert out is not None
    assert out.kind == "multivariate"
    assert out.detail["panel_size"] == n
