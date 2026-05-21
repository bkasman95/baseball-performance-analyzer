import numpy as np
import pandas as pd

from app.analysis import anomalies as A
from app.analysis import attribution as B


def _pitcher_league_panel(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Simulate a league where higher velocity / lower HardHit% predicts lower ERA.
    fbv = rng.normal(94.0, 1.5, n)
    hardhit = rng.normal(0.34, 0.05, n)
    spin = rng.normal(2300, 150, n)
    zone = rng.normal(0.50, 0.04, n)
    era = 4.5 - 0.3 * (fbv - 94.0) + 6.0 * (hardhit - 0.34) + rng.normal(0, 0.6, n)
    return pd.DataFrame({
        "FBv": fbv,
        "HardHit%": hardhit,
        "FBspin (sc)": spin,
        "Zone%": zone,
        "ERA": era,
    })


def _prior_latest_with_velocity_drop():
    prior = pd.Series({
        "FBv": 95.5, "HardHit%": 0.32, "FBspin (sc)": 2350, "Zone%": 0.52,
        "ERA": 3.10, "__season": 2023, "IP": 180,
    })
    latest = pd.Series({
        "FBv": 93.0, "HardHit%": 0.39, "FBspin (sc)": 2280, "Zone%": 0.49,
        "ERA": 4.85, "__season": 2024, "IP": 170,
    })
    return prior, latest


def test_driver_deltas_uses_panel_sd_for_standardization():
    panel = _pitcher_league_panel()
    prior, latest = _prior_latest_with_velocity_drop()
    deltas = B.driver_deltas("pitcher", prior, latest, league_panel=panel)
    by_name = {m.name: (raw, std) for (m, _, _, raw, std) in deltas}
    assert "FB_velocity" in by_name
    raw, std = by_name["FB_velocity"]
    assert raw == -2.5
    # Standardized should be raw / panel SD; panel SD ~ 1.5
    assert abs(std) > 1.0


def test_rank_probable_causes_returns_velocity_for_era_spike():
    panel = _pitcher_league_panel()
    prior, latest = _prior_latest_with_velocity_drop()
    anomaly = A.Anomaly(
        metric="ERA",
        kind="year_over_year",
        season=2024,
        before=3.10,
        after=4.85,
        delta=1.75,
        z_score=3.5,
        severity="high",
        direction="regression",
        confidence="high",
    )
    causes = B.rank_probable_causes("pitcher", anomaly, prior, latest, league_panel=panel)
    assert causes, "should return at least one probable cause"
    top_names = [c.driver for c in causes]
    # Either velocity OR HardHit% should land in the top two -- both moved hard.
    assert any(n in top_names[:3] for n in ("FB_velocity", "HardHit%"))
    # Weights are a normalized distribution
    total = sum(c.attribution_weight for c in causes)
    assert 0.95 <= total <= 1.05


def test_rank_probable_causes_handles_missing_league_panel():
    prior, latest = _prior_latest_with_velocity_drop()
    anomaly = A.Anomaly(
        metric="ERA", kind="year_over_year", season=2024,
        before=3.10, after=4.85, delta=1.75, z_score=3.5,
        severity="high", direction="regression", confidence="high",
    )
    # No league_panel -> falls back to delta+rule ranking only
    causes = B.rank_probable_causes("pitcher", anomaly, prior, latest, league_panel=None)
    assert causes
    assert all(c.attribution_weight >= 0 for c in causes)


def test_rank_returns_empty_for_multivariate_anomaly():
    anomaly = A.Anomaly(
        metric="profile", kind="multivariate", season=None,
        before=None, after=None, delta=None, z_score=None,
        severity="medium", direction="change", confidence="high",
    )
    prior, latest = _prior_latest_with_velocity_drop()
    assert B.rank_probable_causes("pitcher", anomaly, prior, latest) == []
