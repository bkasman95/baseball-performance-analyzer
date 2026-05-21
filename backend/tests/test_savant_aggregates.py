"""Tests for pitch-data gap derivation.

`savant_aggregates` now computes only the metrics MLB doesn't publish on a
season leaderboard (FIP, WHIP, OBP, etc.). Synthetic Statcast pitch data is
small and easy to reason about, so we can verify the formulas without
touching the network.
"""

import pandas as pd

from app.data.savant_aggregates import (
    hitter_gaps_from_pitches,
    pitcher_gaps_from_pitches,
    season_aggregates_from_statcast,
)


def _pitch(events=None, description="ball", pitch_type="FF",
           release_speed=95.0, release_spin_rate=2300.0,
           launch_speed=None, launch_angle=None,
           zone=5, pitch_number=1, at_bat_number=1, game_pk=1,
           ptype="S"):
    return {
        "events": events,
        "description": description,
        "pitch_type": pitch_type,
        "release_speed": release_speed,
        "release_spin_rate": release_spin_rate,
        "release_pos_x": -1.5,
        "release_pos_z": 6.0,
        "release_extension": 6.5,
        "launch_speed": launch_speed,
        "launch_angle": launch_angle,
        "estimated_woba_using_speedangle": 0.40 if launch_speed is not None else None,
        "zone": zone,
        "pitch_number": pitch_number,
        "at_bat_number": at_bat_number,
        "game_pk": game_pk,
        "type": ptype,
        "bb_type": None,
    }


# ---------------------------------------------------------------------------
# Pitcher gaps
# ---------------------------------------------------------------------------

def test_pitcher_gaps_basic_counts():
    """5 PAs: K, BB, single, HR, fly out. Verify IP / WHIP / FIP / BABIP."""
    rows = []
    # K (3 swinging strikes)
    for i in range(3):
        rows.append(_pitch(
            events="strikeout" if i == 2 else None,
            description="swinging_strike",
            at_bat_number=1, pitch_number=i + 1,
        ))
    # BB (4 balls)
    for i in range(4):
        rows.append(_pitch(
            events="walk" if i == 3 else None,
            description="ball",
            at_bat_number=2, pitch_number=i + 1,
        ))
    # Single (EV 95)
    rows.append(_pitch(events="single", description="hit_into_play",
                       launch_speed=95.0, launch_angle=10.0,
                       at_bat_number=3, ptype="X"))
    # HR (EV 105)
    rows.append(_pitch(events="home_run", description="hit_into_play",
                       launch_speed=105.0, launch_angle=28.0,
                       at_bat_number=4, ptype="X"))
    # Fly out
    rows.append(_pitch(events="field_out", description="hit_into_play",
                       launch_speed=85.0, launch_angle=35.0,
                       at_bat_number=5, ptype="X"))

    df = pd.DataFrame(rows)
    gaps = pitcher_gaps_from_pitches(df)

    # Outs = K + field_out = 2, IP = 2/3.
    assert abs(gaps["IP"] - 2 / 3) < 1e-9
    # WHIP = (2 hits + 1 BB) / IP = 3 / (2/3) = 4.5
    assert abs(gaps["WHIP"] - 4.5) < 1e-9
    # HR/9 = (1/IP)*9 = 13.5
    assert abs(gaps["HR/9"] - 13.5) < 1e-9
    # AB = PA-BB-HBP-SAC = 5-1-0-0 = 4
    # BABIP = (hits - HR) / (AB - K - HR + SF) = (2-1)/(4-1-1+0) = 1/2
    assert abs(gaps["BABIP"] - 0.5) < 1e-9
    # CSW%: 3 swinging strikes of 10 pitches
    assert abs(gaps["CSW%"] - 3 / 10) < 1e-9


def test_pitcher_gaps_counts_double_plays_as_two_outs():
    """A GIDP must count as 2 outs, not 1 — otherwise IP is undercounted."""
    rows = [
        _pitch(events="grounded_into_double_play", description="hit_into_play",
               launch_speed=85.0, launch_angle=-5.0,
               at_bat_number=1, ptype="X"),
        _pitch(events="strikeout", description="swinging_strike",
               at_bat_number=2),
    ]
    gaps = pitcher_gaps_from_pitches(pd.DataFrame(rows))
    # 2 outs from GIDP + 1 from K = 3 outs = 1.0 IP
    assert abs(gaps["IP"] - 1.0) < 1e-9


def test_pitcher_gaps_no_leaderboard_metrics_leak():
    """The gap-derivation must NOT emit metrics Savant publishes on a raw-value
    leaderboard (ERA / xERA / wOBA / xwOBA / Barrel% / HardHit% / EV) — those
    are sourced from the leaderboard layer. K% / BB% / O-Swing% / SwStr% etc.
    ARE in this layer because no Savant raw-value endpoint publishes them."""
    rows = [
        _pitch(events="single", description="hit_into_play",
               launch_speed=95.0, launch_angle=15.0, at_bat_number=1, ptype="X"),
    ]
    gaps = pitcher_gaps_from_pitches(pd.DataFrame(rows))
    forbidden = {"ERA", "xERA", "xBA", "xSLG", "wOBA", "xwOBA",
                 "AVG", "Barrel%", "HardHit%", "EV", "maxEV"}
    assert forbidden.isdisjoint(gaps.keys()), \
        f"Leaderboard-owned keys leaked: {forbidden & gaps.keys()}"
    # K% / BB% MUST be here — there's no raw-value Savant leaderboard for them.
    assert "K%" in gaps
    assert "BB%" in gaps


# ---------------------------------------------------------------------------
# Hitter gaps
# ---------------------------------------------------------------------------

def test_hitter_gaps_slash_line():
    """OBP/OPS/ISO/BABIP come from the gap layer because Savant publishes
    AVG/SLG/wOBA but not OBP."""
    rows = []
    for i in range(3):
        rows.append(_pitch(events="strikeout" if i == 2 else None,
                           description="swinging_strike",
                           at_bat_number=1, pitch_number=i + 1))
    rows.append(_pitch(events="single", description="hit_into_play",
                       launch_speed=98.0, launch_angle=15.0,
                       at_bat_number=2, ptype="X"))
    rows.append(_pitch(events="home_run", description="hit_into_play",
                       launch_speed=110.0, launch_angle=28.0,
                       at_bat_number=3, ptype="X"))
    for i in range(4):
        rows.append(_pitch(events="walk" if i == 3 else None,
                           description="ball",
                           at_bat_number=4, pitch_number=i + 1))

    gaps = hitter_gaps_from_pitches(pd.DataFrame(rows))
    # PA = 4, AB = 3, hits = 2, BB = 1, HR = 1, SF = 0
    # OBP = (2 + 1 + 0) / (3 + 1 + 0 + 0) = 3/4 = 0.75
    assert abs(gaps["OBP"] - 0.75) < 1e-9
    # SLG = (1 + 4) / 3 = 5/3
    assert abs(gaps["SLG"] - 5 / 3) < 1e-9
    # OPS = OBP + SLG
    assert abs(gaps["OPS"] - (0.75 + 5 / 3)) < 1e-9
    # ISO = SLG - AVG = 5/3 - 2/3 = 1
    assert abs(gaps["ISO"] - 1.0) < 1e-9


def test_hitter_gaps_no_leaderboard_metrics_leak():
    """Hitter gap layer must not emit metrics Savant publishes raw (xwOBA,
    Barrel%, HardHit%, EV). K%/BB% ARE here because no raw-value leaderboard
    publishes them."""
    rows = [
        _pitch(events="single", description="hit_into_play",
               launch_speed=95.0, launch_angle=15.0, at_bat_number=1, ptype="X"),
    ]
    gaps = hitter_gaps_from_pitches(pd.DataFrame(rows))
    forbidden = {"xwOBA", "xBA", "xSLG", "wOBA",
                 "Barrel%", "HardHit%", "EV", "maxEV"}
    assert forbidden.isdisjoint(gaps.keys()), \
        f"Leaderboard-owned keys leaked: {forbidden & gaps.keys()}"
    assert "K%" in gaps
    assert "BB%" in gaps


# ---------------------------------------------------------------------------
# Multi-season entry point
# ---------------------------------------------------------------------------

def test_season_aggregates_from_statcast_uses_injected_fetcher():
    seasons_data = {
        2023: pd.DataFrame([_pitch(events="single", description="hit_into_play",
                                   launch_speed=95.0, launch_angle=15.0,
                                   at_bat_number=1, ptype="X")]),
        2024: pd.DataFrame([_pitch(events="home_run", description="hit_into_play",
                                   launch_speed=105.0, launch_angle=28.0,
                                   at_bat_number=1, ptype="X")]),
    }
    def fake_fetch(pid, role, season):
        return seasons_data.get(season, pd.DataFrame())

    df = season_aggregates_from_statcast(
        mlbam_id=1, role="hitter", seasons=[2023, 2024], fetch_statcast=fake_fetch,
    )
    assert len(df) == 2
    assert sorted(df["__season"].tolist()) == [2023, 2024]


def test_aggregate_handles_empty_input():
    assert pitcher_gaps_from_pitches(pd.DataFrame()) == {}
    assert hitter_gaps_from_pitches(pd.DataFrame()) == {}


def test_aggregate_handles_missing_optional_columns():
    """Statcast omits zone / bb_type for older seasons. The gap deriver
    must not crash; metrics it can't compute come back as None."""
    minimal = pd.DataFrame([
        {"events": "single", "description": "hit_into_play",
         "at_bat_number": 1, "game_pk": 1, "pitch_number": 1, "type": "X",
         "pitch_type": "FF", "release_speed": 95.0, "launch_speed": 95.0},
    ])
    gaps = hitter_gaps_from_pitches(minimal)
    # AVG / SLG / OBP work from events even without zone
    assert gaps["AVG"] == 1.0
    # Z-Contact% needs the `zone` column
    assert gaps["Z-Contact%"] is None
