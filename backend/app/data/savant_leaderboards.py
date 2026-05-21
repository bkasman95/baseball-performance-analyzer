"""Assemble per-player season rows from Baseball Savant's leaderboards.

Savant publishes MLB's official per-season metrics — xERA, xwOBA, Barrel%,
HardHit%, exit velocity, pitch arsenal — computed with proprietary park /
league factors we can't replicate.

IMPORTANT: each metric is pulled from THE specific endpoint that publishes
it as a raw value. We deliberately do NOT touch the `percentile-rankings`
endpoint, whose columns (xera, k_percent, …) carry 0-100 percentile RANKS,
not the underlying stats — merging that table on top of `expected_statistics`
would silently overwrite the real xERA / xBA / xSLG with rank numbers.

Anything Savant doesn't publish as a raw season value (K%, BB%, FIP, WHIP,
OBP, swing-decision rates, …) is filled in by `savant_aggregates.py` from
cached pitch-level data.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd

from app.data.leaderboards import get_leaderboard


log = logging.getLogger(__name__)


# A small pool: each Savant CSV is ~50-200 KB; concurrency higher than ~6
# doesn't help wall-time and risks Savant rate-limiting us.
_LB_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="lb-fetch")


def _fetch_many(kinds: list[str], year: int, force_refresh: bool) -> dict[str, pd.DataFrame]:
    futures = {
        kind: _LB_POOL.submit(get_leaderboard, kind, year, force_refresh=force_refresh)  # type: ignore[arg-type]
        for kind in kinds
    }
    out: dict[str, pd.DataFrame] = {}
    for kind, fut in futures.items():
        try:
            out[kind] = fut.result()
        except Exception as e:
            log.warning("parallel leaderboard fetch failed for %s/%s: %s", kind, year, e)
            out[kind] = pd.DataFrame()
    return out


# ---------------------------------------------------------------------------
# Helpers
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
    in either 0-100 (e.g. `hard_hit_percent=42.0`) or already 0-1 (e.g.
    `brl_pa=0.063`), depending on the endpoint."""
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

_PITCHER_LEADERBOARD_KINDS = [
    "pitcher_expected",          # xBA / xSLG / xwOBA / xERA + actual outcomes
    "pitcher_exitvelo",          # EV / Barrel% / HardHit% / batted-ball
    "pitcher_arsenal_usage",     # pitch-mix %
    "pitcher_arsenal_speed",     # per-pitch avg velocity
    "pitcher_arsenal_spin",      # per-pitch avg spin
    # NOTE: pitcher_percentile is intentionally omitted — its columns are
    # 0-100 percentile RANKS, not raw values.
]


def assemble_pitcher_season(mlbam_id: int, year: int, *, force_refresh: bool = False) -> dict[str, Any]:
    lbs = _fetch_many(_PITCHER_LEADERBOARD_KINDS, year, force_refresh)
    exp = _row_for_player(lbs["pitcher_expected"], mlbam_id)
    ev  = _row_for_player(lbs["pitcher_exitvelo"], mlbam_id)
    use = _row_for_player(lbs["pitcher_arsenal_usage"], mlbam_id)
    spd = _row_for_player(lbs["pitcher_arsenal_speed"], mlbam_id)
    spn = _row_for_player(lbs["pitcher_arsenal_spin"], mlbam_id)
    if not any([exp, ev, use, spd, spn]):
        return {}

    row: dict[str, Any] = {
        # --- expected_statistics: official MLB outcome + xstats ---
        "ERA":      _first_value(exp, "era"),
        "xERA":     _first_value(exp, "xera"),
        "AVG":      _first_value(exp, "ba"),
        "xBA":      _first_value(exp, "est_ba"),
        "SLG":      _first_value(exp, "slg"),
        "xSLG":     _first_value(exp, "est_slg"),
        "wOBA":     _first_value(exp, "woba"),
        "xwOBA":    _first_value(exp, "est_woba"),
        "PA":       _first_value(exp, "pa"),
        "BIP":      _first_value(exp, "bip"),
        # --- exitvelo / barrels: official contact-quality stats ---
        "HardHit%": _to_pct(_first_value(ev, "hard_hit_percent", "ev95percent")),
        "Barrel%":  _to_pct(_first_value(ev, "barrel_batted_rate", "brl_percent", "brl_pa")),
        "EV":       _first_value(ev, "exit_velocity_avg", "avg_hit_speed"),
        "maxEV":    _first_value(ev, "exit_velocity_max", "max_hit_speed"),
        "LA":       _first_value(ev, "launch_angle_avg", "avg_hit_angle"),
        # --- arsenal usage (Savant returns 0-100, normalize to 0-1) ---
        "FB%":      _to_pct(_first_value(use, "n_ff", "n_fastball")),
        "SI%":      _to_pct(_first_value(use, "n_si", "n_sinker")),
        "SL%":      _to_pct(_first_value(use, "n_sl", "n_slider")),
        "CB%":      _to_pct(_first_value(use, "n_cu", "n_curveball", "n_cukc")),
        "CH%":      _to_pct(_first_value(use, "n_ch", "n_changeup")),
        "FC%":      _to_pct(_first_value(use, "n_fc", "n_cutter")),
        # --- arsenal velocity / spin ---
        "FBv":          _first_value(spd, "ff_avg_speed", "fastball_avg_speed"),
        "FBspin (sc)":  _first_value(spn, "ff_avg_spin", "fastball_avg_spin"),
        # K%, BB%, O-Swing%, SwStr%, CSW%, Zone%, F-Strike%, FIP, WHIP, HR/9,
        # BABIP are all filled in by savant_aggregates.pitcher_gaps_from_pitches.
    }
    return {k: v for k, v in row.items() if v is not None}


# ---------------------------------------------------------------------------
# Hitter assembly
# ---------------------------------------------------------------------------

_HITTER_LEADERBOARD_KINDS = [
    "batter_expected",
    "batter_exitvelo",
    # batter_percentile omitted for the same reason as pitcher_percentile.
]


def assemble_hitter_season(mlbam_id: int, year: int, *, force_refresh: bool = False) -> dict[str, Any]:
    lbs = _fetch_many(_HITTER_LEADERBOARD_KINDS, year, force_refresh)
    exp = _row_for_player(lbs["batter_expected"], mlbam_id)
    ev  = _row_for_player(lbs["batter_exitvelo"], mlbam_id)
    if not any([exp, ev]):
        return {}

    row: dict[str, Any] = {
        # --- expected_statistics: actual + xstats ---
        "AVG":      _first_value(exp, "ba"),
        "xBA":      _first_value(exp, "est_ba"),
        "SLG":      _first_value(exp, "slg"),
        "xSLG":     _first_value(exp, "est_slg"),
        "wOBA":     _first_value(exp, "woba"),
        "xwOBA":    _first_value(exp, "est_woba"),
        "PA":       _first_value(exp, "pa"),
        "BIP":      _first_value(exp, "bip"),
        # --- exitvelo: contact-quality + batted-ball profile ---
        "HardHit%": _to_pct(_first_value(ev, "hard_hit_percent", "ev95percent")),
        "Barrel%":  _to_pct(_first_value(ev, "barrel_batted_rate", "brl_percent")),
        "EV":       _first_value(ev, "exit_velocity_avg", "avg_hit_speed"),
        "maxEV":    _first_value(ev, "exit_velocity_max", "max_hit_speed"),
        "LA":       _first_value(ev, "launch_angle_avg", "avg_hit_angle"),
        "SweetSpot%": _to_pct(_first_value(ev, "sweet_spot_percent", "anglesweetspotpercent")),
        "GB%":      _to_pct(_first_value(ev, "gb_percent", "groundballs_percent")),
        "FB%":      _to_pct(_first_value(ev, "fb_percent", "flyballs_percent")),
        "LD%":      _to_pct(_first_value(ev, "ld_percent", "linedrives_percent")),
        # K%, BB%, OBP, OPS, ISO, BABIP, Whiff%, O-Swing%, Contact%, Z-Contact%,
        # SwStr%, Bat_speed, Swing_length are filled in by
        # savant_aggregates.hitter_gaps_from_pitches.
    }
    return {k: v for k, v in row.items() if v is not None}


__all__ = [
    "assemble_pitcher_season",
    "assemble_hitter_season",
]
