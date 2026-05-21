"""End-to-end test of the report builder with stubbed data-layer fetchers."""

import numpy as np
import pandas as pd

from app.analysis import build_report


def _seasons_df() -> pd.DataFrame:
    return pd.DataFrame({
        "__season": [2020, 2021, 2022, 2023, 2024],
        "ERA":      [3.10, 3.05, 3.25, 3.15, 4.85],
        "WHIP":     [1.10, 1.08, 1.12, 1.09, 1.31],
        "K%":       [0.27, 0.28, 0.26, 0.27, 0.21],
        "HardHit%": [0.32, 0.31, 0.33, 0.32, 0.40],
        "FBv":      [95.4, 95.3, 95.0, 94.8, 92.9],
        "FBspin (sc)": [2350, 2340, 2330, 2320, 2280],
        "Zone%":    [0.51, 0.50, 0.52, 0.50, 0.48],
        "PA":       [800, 820, 790, 810, 760],
        "IP":       [180, 185, 175, 190, 170],
    })


def _league_panel(n: int = 200, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    fbv = rng.normal(94.0, 1.5, n)
    hardhit = rng.normal(0.34, 0.05, n)
    spin = rng.normal(2300, 150, n)
    zone = rng.normal(0.50, 0.04, n)
    era = 4.5 - 0.3 * (fbv - 94.0) + 6.0 * (hardhit - 0.34) + rng.normal(0, 0.6, n)
    whip = 1.20 + 0.05 * (hardhit - 0.34) + rng.normal(0, 0.05, n)
    k_pct = 0.22 + 0.01 * (fbv - 94.0) + rng.normal(0, 0.02, n)
    return pd.DataFrame({
        "FBv": fbv,
        "HardHit%": hardhit,
        "FBspin (sc)": spin,
        "Zone%": zone,
        "ERA": era,
        "WHIP": whip,
        "K%": k_pct,
    })


def test_build_report_emits_findings_and_headline():
    seasons = _seasons_df()
    league = _league_panel()

    report = build_report(
        player_id=605400,
        role="pitcher",
        season=2024,
        seasons_window=6,
        fetch_seasons=lambda pid, r, s: seasons,
        fetch_statcast=lambda pid, r, s: pd.DataFrame(),  # skip in-season
        fetch_league_panel=lambda r, s: league,
    )

    d = report.to_dict()
    assert d["role"] == "pitcher"
    assert d["season"] == 2024
    assert isinstance(d["seasons_analyzed"], list) and 2024 in d["seasons_analyzed"]
    assert d["findings"], "should flag at least one YoY anomaly"

    # ERA spike should be among the findings.
    metrics_flagged = {f["metric"] for f in d["findings"]}
    assert "ERA" in metrics_flagged

    era = next(f for f in d["findings"] if f["metric"] == "ERA")
    assert era["direction"] == "regression"
    assert era["probable_causes"], "ERA finding should carry probable causes"
    assert "ERA" in d["headline"] or any(
        f["metric"] in d["headline"] for f in d["findings"]
    )


def test_build_report_handles_empty_player_data():
    report = build_report(
        player_id=1,
        role="hitter",
        season=2024,
        fetch_seasons=lambda pid, r, s: pd.DataFrame(),
        fetch_statcast=lambda pid, r, s: pd.DataFrame(),
        fetch_league_panel=lambda r, s: pd.DataFrame(),
    )
    d = report.to_dict()
    assert d["findings"] == []
    assert "No FanGraphs" in d["headline"]
    assert "empty_player_seasons" in d["notes"]


def test_build_report_is_jsonable():
    import json
    seasons = _seasons_df()
    league = _league_panel()
    report = build_report(
        player_id=605400,
        role="pitcher",
        season=2024,
        fetch_seasons=lambda pid, r, s: seasons,
        fetch_statcast=lambda pid, r, s: pd.DataFrame(),
        fetch_league_panel=lambda r, s: league,
    )
    # Serialize: must work without TypeErrors from numpy types or NaN.
    blob = json.dumps(report.to_dict(), default=str)
    assert "ERA" in blob
