"""Tests for the Savant leaderboard assembly layer.

We mock `get_leaderboard` so the tests don't hit the network, then verify
the assemble functions normalize Savant's column names into the canonical
ones the analysis catalog expects.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from app.data import savant_leaderboards as sl

_APPROX = pytest.approx  # short alias


def _make_lb(player_id: int, **cols) -> pd.DataFrame:
    return pd.DataFrame([{"player_id": player_id, **cols}])


# ---------------------------------------------------------------------------
# Percent normalization
# ---------------------------------------------------------------------------

def test_to_pct_handles_both_scales():
    # 0-100 scale → divided
    assert sl._to_pct(24.7) == 0.247
    # Already 0-1 → untouched
    assert sl._to_pct(0.247) == 0.247
    # None / NaN passthrough
    assert sl._to_pct(None) is None
    assert sl._to_pct(float("nan")) is None
    # Bad input
    assert sl._to_pct("not a number") is None


# ---------------------------------------------------------------------------
# Player row lookup
# ---------------------------------------------------------------------------

def test_row_for_player_matches_player_id_column():
    df = pd.DataFrame([
        {"player_id": 111, "stat": 1.0},
        {"player_id": 222, "stat": 2.0},
    ])
    row = sl._row_for_player(df, 222)
    assert row["stat"] == 2.0


def test_row_for_player_returns_empty_when_missing():
    df = pd.DataFrame([{"player_id": 111, "stat": 1.0}])
    assert sl._row_for_player(df, 999) == {}


def test_row_for_player_returns_empty_for_empty_df():
    assert sl._row_for_player(pd.DataFrame(), 111) == {}


# ---------------------------------------------------------------------------
# Pitcher assembly
# ---------------------------------------------------------------------------

def test_assemble_pitcher_normalizes_savant_column_names():
    """Savant uses lowercased snake_case; the catalog expects canonical
    names (xERA, xwOBA, K%, Barrel%, HardHit%, FBv). The assembler bridges them."""
    expected_df = _make_lb(123, era=3.45, xera=3.21, ba=0.245, est_ba=0.231,
                           slg=0.380, est_slg=0.395,
                           woba=0.300, est_woba=0.291, pa=600, bip=200)
    exitvelo_df = _make_lb(123, barrel_batted_rate=8.5, hard_hit_percent=42.0,
                           exit_velocity_avg=88.5, max_hit_speed=110.3,
                           launch_angle_avg=12.0)
    pct_df = _make_lb(123, k_percent=24.5, bb_percent=7.2,
                      oz_swing_percent=30.5, whiff_percent=11.0)
    usage_df = _make_lb(123, n_ff=55.0, n_sl=20.0, n_ch=15.0, n_cu=10.0)
    speed_df = _make_lb(123, ff_avg_speed=95.4)
    spin_df = _make_lb(123, ff_avg_spin=2400.0)

    def fake_lb(kind, year, *, force_refresh=False):
        return {
            "pitcher_expected":      expected_df,
            "pitcher_exitvelo":      exitvelo_df,
            "pitcher_percentile":    pct_df,
            "pitcher_arsenal_usage": usage_df,
            "pitcher_arsenal_speed": speed_df,
            "pitcher_arsenal_spin":  spin_df,
        }.get(kind, pd.DataFrame())

    with patch.object(sl, "get_leaderboard", side_effect=fake_lb):
        row = sl.assemble_pitcher_season(123, 2024)

    assert row["ERA"] == _APPROX(3.45)
    assert row["xERA"] == _APPROX(3.21)
    assert row["AVG"] == _APPROX(0.245)
    assert row["xBA"] == _APPROX(0.231)
    assert row["xwOBA"] == _APPROX(0.291)
    # Percentages get normalized to 0-1
    assert row["K%"] == _APPROX(0.245)
    assert row["BB%"] == _APPROX(0.072)
    assert row["Barrel%"] == _APPROX(0.085)
    assert row["HardHit%"] == _APPROX(0.42)
    assert row["O-Swing%"] == _APPROX(0.305)
    # Pitch mix
    assert row["FB%"] == _APPROX(0.55)
    assert row["SL%"] == _APPROX(0.20)
    # Velocity / spin stay in physical units
    assert row["FBv"] == _APPROX(95.4)
    assert row["FBspin (sc)"] == _APPROX(2400.0)
    # Contact-quality raw values stay unscaled
    assert row["EV"] == _APPROX(88.5)
    assert row["maxEV"] == _APPROX(110.3)


def test_assemble_pitcher_returns_empty_when_no_leaderboards_have_player():
    with patch.object(sl, "get_leaderboard", return_value=pd.DataFrame()):
        assert sl.assemble_pitcher_season(999, 2024) == {}


def test_assemble_pitcher_drops_missing_fields():
    """If only the percentile leaderboard has the player, we should still
    get a row back with just those fields — no `None` keys leaking."""
    pct_df = _make_lb(123, k_percent=22.0, bb_percent=8.0)

    def fake_lb(kind, year, *, force_refresh=False):
        return pct_df if kind == "pitcher_percentile" else pd.DataFrame()

    with patch.object(sl, "get_leaderboard", side_effect=fake_lb):
        row = sl.assemble_pitcher_season(123, 2024)

    assert row["K%"] == _APPROX(0.22)
    assert row["BB%"] == _APPROX(0.08)
    assert "xERA" not in row     # absent endpoint → key not present
    assert "Barrel%" not in row


# ---------------------------------------------------------------------------
# Hitter assembly
# ---------------------------------------------------------------------------

def test_assemble_hitter_normalizes_savant_columns():
    expected_df = _make_lb(456, ba=0.275, est_ba=0.291, slg=0.480, est_slg=0.495,
                           woba=0.350, est_woba=0.362, pa=550, bip=420)
    exitvelo_df = _make_lb(456, barrel_batted_rate=11.5, hard_hit_percent=48.0,
                           exit_velocity_avg=90.2, max_hit_speed=114.1,
                           launch_angle_avg=15.5,
                           sweet_spot_percent=35.5)
    pct_df = _make_lb(456, k_percent=18.0, bb_percent=10.5,
                      oz_swing_percent=28.0, whiff_percent=22.0,
                      avg_bat_speed=72.5, avg_swing_length=7.1)

    def fake_lb(kind, year, *, force_refresh=False):
        return {
            "batter_expected":   expected_df,
            "batter_exitvelo":   exitvelo_df,
            "batter_percentile": pct_df,
        }.get(kind, pd.DataFrame())

    with patch.object(sl, "get_leaderboard", side_effect=fake_lb):
        row = sl.assemble_hitter_season(456, 2024)

    assert row["AVG"] == _APPROX(0.275)
    assert row["xBA"] == _APPROX(0.291)
    assert row["xwOBA"] == _APPROX(0.362)
    assert row["K%"] == _APPROX(0.18)
    assert row["Barrel%"] == _APPROX(0.115)
    assert row["HardHit%"] == _APPROX(0.48)
    assert row["SweetSpot%"] == _APPROX(0.355)
    assert row["avg_bat_speed"] == _APPROX(72.5)
    assert row["avg_swing_length"] == _APPROX(7.1)
