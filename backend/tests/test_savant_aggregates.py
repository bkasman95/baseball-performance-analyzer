"""Tests for the Savant-derived season aggregator.

Synthetic Statcast pitch data is small and easy to reason about, so we can
verify the aggregator computes the expected outcome and driver metrics
without ever touching the network.
"""

import numpy as np
import pandas as pd

from app.data.savant_aggregates import (
    aggregate_hitter_season,
    aggregate_pitcher_season,
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


def test_aggregate_pitcher_basic_counts():
    # Build 5 plate appearances ending in: K, BB, single, HR, fly_out
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
    # Single (1 pitch, in play, EV 95 LA 10)
    rows.append(_pitch(
        events="single", description="hit_into_play", launch_speed=95.0,
        launch_angle=10.0, at_bat_number=3, ptype="X",
    ))
    # HR (1 pitch, in play, EV 105 LA 28)
    rows.append(_pitch(
        events="home_run", description="hit_into_play", launch_speed=105.0,
        launch_angle=28.0, at_bat_number=4, ptype="X",
    ))
    # Fly out (1 pitch, in play, EV 85 LA 35)
    rows.append(_pitch(
        events="field_out", description="hit_into_play", launch_speed=85.0,
        launch_angle=35.0, at_bat_number=5, ptype="X",
    ))

    df = pd.DataFrame(rows)
    agg = aggregate_pitcher_season(df)

    assert agg["PA"] == 5
    assert agg["K%"] == 1 / 5
    assert agg["BB%"] == 1 / 5
    # WHIP: (1 hit single + 1 HR + 1 BB) / IP. Outs = K + field_out = 2 -> IP = 2/3
    assert agg["WHIP"] > 0
    # HardHit% — 2 of 3 batted balls had EV>=95
    assert abs(agg["HardHit%"] - 2 / 3) < 1e-9
    # 1 barrel (EV 105, LA 28 -> in 26-30 window)
    assert abs(agg["Barrel%"] - 1 / 3) < 1e-9
    # CSW% — 3 swinging strikes out of 10 pitches
    assert abs(agg["CSW%"] - 3 / 10) < 1e-9


def test_aggregate_hitter_basic_counts():
    rows = []
    # K
    for i in range(3):
        rows.append(_pitch(
            events="strikeout" if i == 2 else None,
            description="swinging_strike",
            at_bat_number=1, pitch_number=i + 1,
        ))
    # Single
    rows.append(_pitch(
        events="single", description="hit_into_play", launch_speed=98.0,
        launch_angle=15.0, at_bat_number=2, ptype="X",
    ))
    # HR
    rows.append(_pitch(
        events="home_run", description="hit_into_play", launch_speed=110.0,
        launch_angle=28.0, at_bat_number=3, ptype="X",
    ))
    # Walk
    for i in range(4):
        rows.append(_pitch(
            events="walk" if i == 3 else None,
            description="ball",
            at_bat_number=4, pitch_number=i + 1,
        ))

    df = pd.DataFrame(rows)
    agg = aggregate_hitter_season(df)

    assert agg["PA"] == 4
    # AB = PA - BB = 3.  AVG = 2 hits / 3 AB
    assert abs(agg["AVG"] - 2 / 3) < 1e-9
    # OBP = (2 hits + 1 BB) / 4 PA
    assert abs(agg["OBP"] - 3 / 4) < 1e-9
    # SLG = (1 + 4) / 3
    assert abs(agg["SLG"] - 5 / 3) < 1e-9
    assert agg["K%"] == 1 / 4
    assert agg["BB%"] == 1 / 4


def test_season_aggregates_from_statcast_uses_injected_fetcher():
    """Verify the public entry point assembles a multi-season DataFrame."""
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
    assert aggregate_pitcher_season(pd.DataFrame()) == {}
    assert aggregate_hitter_season(pd.DataFrame()) == {}


def test_aggregate_handles_missing_optional_columns():
    """Statcast schema sometimes omits zone / bb_type / bat_speed for older
    seasons. The aggregator must not crash; missing metrics come back as None."""
    minimal = pd.DataFrame([
        {"events": "single", "description": "hit_into_play",
         "at_bat_number": 1, "game_pk": 1, "pitch_number": 1, "type": "X",
         "pitch_type": "FF", "release_speed": 95.0,
         "launch_speed": 95.0},
    ])
    agg = aggregate_hitter_season(minimal)
    assert agg["PA"] == 1
    assert agg["GB%"] is None       # no bb_type column
    assert agg["O-Swing%"] is None  # no zone column
