"""Assemble per-player season rows from Baseball Savant's leaderboards.

Savant publishes MLB's official per-season metrics — xERA, xwOBA, Barrel%,
HardHit%, exit velocity, pitch arsenal, swing decisions — computed with
proprietary park / league factors we can't replicate. We pull each
leaderboard once per season (via `leaderboards.get_leaderboard`), then this
module joins the relevant boards into a single dict for one player-season.

Anything Savant doesn't publish (FIP, WHIP, BABIP, OBP, …) is filled in
separately by `savant_aggregates.py` from cached pitch data.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from app.data.leaderboards import get_leaderboard


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Player-row lookup
# ---------------------------------------------------------------------------

_PLAYER_ID_COLS = ("player_id", "playerid", "MLBAMID", "mlbamid", "key_mlbam", "pitcher", "batter")


def _row_for_player(df: pd.DataFrame, mlbam_id: int) -> dict[str, Any]:
    if df.empty:
        return {}
    for col in _PLAYER_ID_COLS:
        if col not in df.columns:
            continue
        try:
            mask = df[col].astype("Int64") == mlbam_id
        except (TypeError, ValueError):
            continue
        sub = df.loc[mask]
        if not sub.empty:
            return sub.iloc[0].to_dict()
    return {}


def _first_value(d: dict[str, Any], *names: str) -> Any:
    for n in names:
        if n in d:
            v = d[n]
            if v is None:
                continue
            try:
                if pd.isna(v):  # type: ignore[arg-type]
                    continue
            except (TypeError, ValueError):
                pass
            return v
    return None


def _to_pct(v: Any) -> float | None:
    """Normalize a Savant percent value to a 0-1 ratio. Savant returns these
    in either 0-100 (e.g. `k_percent=24.7`) or already 0-1 (e.g. `brl_pa=0.063`),
    depending on the endpoint."""
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(x):
        return None
    return x / 100.0 if abs(x) > 1.0 else x


# ---------------------------------------------------------------------------
# Pitcher assembly
# ---------------------------------------------------------------------------

def assemble_pitcher_season(mlbam_id: int, year: int, *, force_refresh: bool = False) -> dict[str, Any]:
    """Pull every relevant Savant leaderboard for the season and return one
    flat dict for the player. Missing values are simply absent so downstream
    pitch-derived gap filling has somewhere to land."""
    exp = _row_for_player(get_leaderboard("pitcher_expected", year, force_refresh=force_refresh), mlbam_id)
    ev  = _row_for_player(get_leaderboard("pitcher_exitvelo", year, force_refresh=force_refresh), mlbam_id)
    pct = _row_for_player(get_leaderboard("pitcher_percentile", year, force_refresh=force_refresh), mlbam_id)
    use = _row_for_player(get_leaderboard("pitcher_arsenal_usage", year, force_refresh=force_refresh), mlbam_id)
    spd = _row_for_player(get_leaderboard("pitcher_arsenal_speed", year, force_refresh=force_refresh), mlbam_id)
    spn = _row_for_player(get_leaderboard("pitcher_arsenal_spin", year, force_refresh=force_refresh), mlbam_id)
    merged: dict[str, Any] = {**exp, **ev, **pct, **use, **spd, **spn}
    if not merged:
        return {}

    row: dict[str, Any] = {
        # --- outcomes (official MLB values) ---
        "ERA":      _first_value(merged, "era", "p_era"),
        "xERA":     _first_value(merged, "xera", "p_xera"),
        "AVG":      _first_value(merged, "ba", "p_ba", "batting_avg"),
        "xBA":      _first_value(merged, "est_ba", "xba"),
        "SLG":      _first_value(merged, "slg", "p_slg"),
        "xSLG":     _first_value(merged, "est_slg", "xslg"),
        "wOBA":     _first_value(merged, "woba", "p_woba"),
        "xwOBA":    _first_value(merged, "est_woba", "xwoba"),
        "K%":       _to_pct(_first_value(merged, "k_percent", "p_k_percent", "k_pct")),
        "BB%":      _to_pct(_first_value(merged, "bb_percent", "p_bb_percent", "bb_pct")),
        "HardHit%": _to_pct(_first_value(merged, "hard_hit_percent", "ev95percent")),
        "Barrel%":  _to_pct(_first_value(merged, "barrel_batted_rate", "brl_percent", "brl_pa")),
        # --- contact quality (against) ---
        "EV":       _first_value(merged, "exit_velocity_avg", "avg_hit_speed"),
        "maxEV":    _first_value(merged, "exit_velocity_max", "max_hit_speed"),
        "LA":       _first_value(merged, "launch_angle_avg", "avg_hit_angle"),
        # --- pitch-mix usage (kept as 0-1 ratios for consistency) ---
        "FB%":      _to_pct(_first_value(merged, "n_ff", "n_fastball")),
        "SI%":      _to_pct(_first_value(merged, "n_si", "n_sinker")),
        "SL%":      _to_pct(_first_value(merged, "n_sl", "n_slider")),
        "CB%":      _to_pct(_first_value(merged, "n_cu", "n_curveball", "n_cukc")),
        "CH%":      _to_pct(_first_value(merged, "n_ch", "n_changeup")),
        "FC%":      _to_pct(_first_value(merged, "n_fc", "n_cutter")),
        # --- arsenal velocity / spin ---
        "FBv":          _first_value(merged, "ff_avg_speed", "fastball_avg_speed", "fb_velocity"),
        "FBspin (sc)":  _first_value(merged, "ff_avg_spin", "fastball_avg_spin", "fb_spin"),
        # --- swing decisions ---
        "O-Swing%":     _to_pct(_first_value(merged, "oz_swing_percent", "chase_percent")),
        "SwStr%":       _to_pct(_first_value(merged, "swing_miss_percent", "whiff_percent")),
        # --- sample-size context ---
        "PA":       _first_value(merged, "pa", "p_pa"),
        "BIP":      _first_value(merged, "bip", "attempts", "bbe"),
    }
    return {k: v for k, v in row.items() if v is not None}


# ---------------------------------------------------------------------------
# Hitter assembly
# ---------------------------------------------------------------------------

def assemble_hitter_season(mlbam_id: int, year: int, *, force_refresh: bool = False) -> dict[str, Any]:
    exp = _row_for_player(get_leaderboard("batter_expected", year, force_refresh=force_refresh), mlbam_id)
    ev  = _row_for_player(get_leaderboard("batter_exitvelo", year, force_refresh=force_refresh), mlbam_id)
    pct = _row_for_player(get_leaderboard("batter_percentile", year, force_refresh=force_refresh), mlbam_id)
    merged: dict[str, Any] = {**exp, **ev, **pct}
    if not merged:
        return {}

    row: dict[str, Any] = {
        # --- outcomes ---
        "AVG":      _first_value(merged, "ba", "batting_avg"),
        "xBA":      _first_value(merged, "est_ba", "xba"),
        "SLG":      _first_value(merged, "slg"),
        "xSLG":     _first_value(merged, "est_slg", "xslg"),
        "wOBA":     _first_value(merged, "woba"),
        "xwOBA":    _first_value(merged, "est_woba", "xwoba"),
        "K%":       _to_pct(_first_value(merged, "k_percent", "k_pct")),
        "BB%":      _to_pct(_first_value(merged, "bb_percent", "bb_pct")),
        "HardHit%": _to_pct(_first_value(merged, "hard_hit_percent", "ev95percent")),
        "Barrel%":  _to_pct(_first_value(merged, "barrel_batted_rate", "brl_percent")),
        # --- contact quality ---
        "EV":       _first_value(merged, "exit_velocity_avg", "avg_hit_speed"),
        "maxEV":    _first_value(merged, "exit_velocity_max", "max_hit_speed"),
        "LA":       _first_value(merged, "launch_angle_avg", "avg_hit_angle"),
        "SweetSpot%": _to_pct(_first_value(merged, "sweet_spot_percent", "anglesweetspotpercent")),
        # --- batted-ball profile ---
        "GB%":      _to_pct(_first_value(merged, "gb_percent", "groundballs_percent")),
        "FB%":      _to_pct(_first_value(merged, "fb_percent", "flyballs_percent")),
        "LD%":      _to_pct(_first_value(merged, "ld_percent", "linedrives_percent")),
        # --- bat tracking ---
        "avg_bat_speed":    _first_value(merged, "avg_bat_speed", "bat_speed"),
        "avg_swing_length": _first_value(merged, "avg_swing_length", "swing_length"),
        # --- swing decisions ---
        "O-Swing%":     _to_pct(_first_value(merged, "oz_swing_percent", "chase_percent")),
        "Whiff%":       _to_pct(_first_value(merged, "whiff_percent")),
        # --- sample size ---
        "PA":       _first_value(merged, "pa"),
        "BIP":      _first_value(merged, "bip", "attempts", "bbe"),
    }
    return {k: v for k, v in row.items() if v is not None}


__all__ = [
    "assemble_pitcher_season",
    "assemble_hitter_season",
]
