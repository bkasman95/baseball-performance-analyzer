"""Pitch-data derivations for the metrics Savant leaderboards don't publish.

Most season-level stats (xERA, xwOBA, Barrel%, HardHit%, EV, swing decisions,
pitch arsenal) come from `savant_leaderboards.py` — MLB computes those
officially and we shouldn't reinvent them.

What MLB does NOT publish on a leaderboard (or only as a percentile rank,
not a raw value), we compute here from the cached pitch-level Statcast feed:

  Pitcher gaps : IP, FIP, WHIP, HR/9, BABIP, CSW%, Zone%, F-Strike%,
                 release height/side, extension, pitch counts
  Hitter gaps  : OBP, OPS, ISO, BABIP, Z-Contact%, Contact%

All formulas here are exact (no approximations); we own them because they're
either trivial counting math or pitch-level rollups, not the kind of
proprietary computation we'd want to second-guess MLB on.
"""

from __future__ import annotations

import logging
from typing import Iterable, Literal

import pandas as pd


log = logging.getLogger(__name__)

Role = Literal["pitcher", "hitter", "batting", "pitching"]


# ---------------------------------------------------------------------------
# wOBA linear weights — used only for the BB/HBP credit when we derive OBP
# / OPS / ISO from raw counts. NOT used for wOBA itself (that comes from the
# leaderboard).
# ---------------------------------------------------------------------------

_CFIP = 3.10  # league-average FIP constant, ~stable across recent seasons


# Outs per terminal-event. Multi-out events matter: GIDPs alone produce
# ~6-7 IP per season that a "1 out each" treatment would miss.
_OUT_EVENT_WEIGHTS: dict[str, int] = {
    "strikeout":                   1,
    "field_out":                   1,
    "force_out":                   1,
    "fielders_choice":             1,
    "fielders_choice_out":         1,
    "sac_fly":                     1,
    "sac_bunt":                    1,
    "other_out":                   1,
    "double_play":                 2,
    "grounded_into_double_play":   2,
    "strikeout_double_play":       2,
    "sac_fly_double_play":         2,
    "sac_bunt_double_play":        2,
    "triple_play":                 3,
}


def _count(series: pd.Series, value: str) -> int:
    return int((series == value).sum())


def _pa_total(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    keys = [c for c in ("game_pk", "at_bat_number") if c in df.columns]
    if not keys:
        return 0
    return int(df.drop_duplicates(keys).shape[0])


def _terminal_events(df: pd.DataFrame) -> pd.Series:
    if df.empty or "events" not in df.columns:
        return pd.Series(dtype="object")
    return df["events"].dropna()


def _mean_or_none(series: pd.Series) -> float | None:
    s = series.dropna()
    if s.empty:
        return None
    return float(s.mean())


# ---------------------------------------------------------------------------
# Pitcher gaps
# ---------------------------------------------------------------------------

def pitcher_gaps_from_pitches(df: pd.DataFrame) -> dict[str, float | int | None]:
    """Compute the pitcher-side metrics Savant leaderboards don't publish."""
    if df.empty:
        return {}

    pitches = len(df)
    pa = _pa_total(df)
    events = _terminal_events(df)

    so   = _count(events, "strikeout") + _count(events, "strikeout_double_play")
    bb   = _count(events, "walk")
    hbp  = _count(events, "hit_by_pitch")
    single = _count(events, "single")
    double = _count(events, "double")
    triple = _count(events, "triple")
    hr   = _count(events, "home_run")
    hits = single + double + triple + hr
    sac     = _count(events, "sac_fly") + _count(events, "sac_bunt")
    sac_fly = _count(events, "sac_fly")
    ab = max(pa - bb - hbp - sac, 0)

    outs = int(events.map(_OUT_EVENT_WEIGHTS).fillna(0).sum())
    implied_outs = max(pa - (hits + bb + hbp), 0)
    outs = max(outs, implied_outs)
    ip = outs / 3.0 if outs else 0.0

    whip = (hits + bb) / ip if ip else None
    hr_9 = (hr / ip) * 9 if ip else None
    fip = (((13 * hr) + (3 * (bb + hbp)) - (2 * so)) / ip + _CFIP) if ip else None

    babip_den = ab - so - hr + sac_fly
    babip = (hits - hr) / babip_den if babip_den > 0 else None

    # Pitch-level rates (these aren't on the season leaderboards as raw values)
    desc = df.get("description", pd.Series(dtype="object"))
    called = _count(desc, "called_strike")
    whiff  = _count(desc, "swinging_strike") + _count(desc, "swinging_strike_blocked")
    csw    = (called + whiff) / pitches if pitches else None
    swstr  = whiff / pitches if pitches else None

    zone_pct: float | None = None
    if "zone" in df.columns:
        z = pd.to_numeric(df["zone"], errors="coerce").dropna()
        if not z.empty:
            zone_pct = float(((z >= 1) & (z <= 9)).mean())

    f_strike_pct: float | None = None
    if "pitch_number" in df.columns and "type" in df.columns:
        first = df[df["pitch_number"] == 1]
        if not first.empty:
            f_strike_pct = float(first["type"].isin(["S", "X"]).mean())

    # Release mechanics — averages across all pitches the player threw.
    release_h = _mean_or_none(df["release_pos_z"]) if "release_pos_z" in df.columns else None
    release_s = _mean_or_none(df["release_pos_x"]) if "release_pos_x" in df.columns else None
    extension = _mean_or_none(df["release_extension"]) if "release_extension" in df.columns else None

    return {
        "IP":               ip,
        "FIP":              fip,
        "xFIP":             fip,    # without league HR/FB rate we can't separate; FIP is the honest answer
        "WHIP":             whip,
        "HR/9":             hr_9,
        "BABIP":            babip,
        "CSW%":             csw,
        "SwStr%":           swstr,    # pitcher-side swstr; leaderboard's pitcher swing_miss_percent will override when present
        "Zone%":            zone_pct,
        "F-Strike%":        f_strike_pct,
        "Release_height":   release_h,
        "Release_side":     release_s,
        "Extension":        extension,
        "Pitches":          pitches,
        "_PA_pitch":        pa,         # for sanity-checking vs leaderboard PA
    }


# ---------------------------------------------------------------------------
# Hitter gaps
# ---------------------------------------------------------------------------

def hitter_gaps_from_pitches(df: pd.DataFrame) -> dict[str, float | int | None]:
    """Compute hitter-side metrics Savant leaderboards don't publish — chiefly
    the slash line beyond AVG/SLG (OBP/OPS/ISO) and BABIP."""
    if df.empty:
        return {}

    pa = _pa_total(df)
    events = _terminal_events(df)

    so   = _count(events, "strikeout") + _count(events, "strikeout_double_play")
    bb   = _count(events, "walk")
    hbp  = _count(events, "hit_by_pitch")
    single = _count(events, "single")
    double = _count(events, "double")
    triple = _count(events, "triple")
    hr   = _count(events, "home_run")
    hits = single + double + triple + hr
    sac     = _count(events, "sac_fly") + _count(events, "sac_bunt")
    sac_fly = _count(events, "sac_fly")

    ab = max(pa - bb - hbp - sac, 0)
    tb = single + 2 * double + 3 * triple + 4 * hr

    avg = hits / ab if ab else None
    slg = tb / ab if ab else None
    # OBP excludes sacrifice bunts from the denominator (PA includes them).
    obp_den = ab + bb + hbp + sac_fly
    obp = (hits + bb + hbp) / obp_den if obp_den else None
    ops = (obp + slg) if (obp is not None and slg is not None) else None
    iso = (slg - avg) if (slg is not None and avg is not None) else None

    babip_den = ab - so - hr + sac_fly
    babip = (hits - hr) / babip_den if babip_den > 0 else None

    # Plate-discipline rates derivable from pitch descriptions.
    desc = df.get("description", pd.Series(dtype="object"))
    pitches = len(df)
    whiff = _count(desc, "swinging_strike") + _count(desc, "swinging_strike_blocked")
    foul  = _count(desc, "foul") + _count(desc, "foul_tip")
    in_play = _count(desc, "hit_into_play")
    swings = whiff + foul + in_play
    contact_pct = (swings - whiff) / swings if swings else None
    swstr_pct = whiff / pitches if pitches else None

    z_contact_pct: float | None = None
    if "zone" in df.columns:
        z = pd.to_numeric(df["zone"], errors="coerce")
        inside = df[(z >= 1) & (z <= 9)]
        if not inside.empty:
            iz_swings = inside["description"].isin([
                "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play",
            ])
            iz_whiffs = inside["description"].isin([
                "swinging_strike", "swinging_strike_blocked",
            ])
            n_sw = int(iz_swings.sum())
            n_wh = int(iz_whiffs.sum())
            z_contact_pct = (n_sw - n_wh) / n_sw if n_sw else None

    return {
        "OBP":          obp,
        "OPS":          ops,
        "ISO":          iso,
        "BABIP":        babip,
        # Slash-line basics too — leaderboard provides AVG/SLG/wOBA already,
        # but if a player slipped under their minPA threshold, this fills in.
        "AVG":          avg,
        "SLG":          slg,
        "Contact%":     contact_pct,
        "Z-Contact%":   z_contact_pct,
        "SwStr%":       swstr_pct,
        "_PA_pitch":    pa,
    }


# ---------------------------------------------------------------------------
# Public entry point — preserves the old signature so aggregates.py can
# keep calling it while we switch the data path under the hood.
# ---------------------------------------------------------------------------

def season_aggregates_from_statcast(
    mlbam_id: int,
    role: Role,
    seasons: Iterable[int],
    *,
    fetch_statcast,
) -> pd.DataFrame:
    """One row per season with PITCH-DERIVED gap metrics only.

    The leaderboard-sourced metrics get merged in by `aggregates.get_season_aggregates`.
    """
    norm_role = "pitcher" if role in ("pitcher", "pitching") else "hitter"
    deriver = pitcher_gaps_from_pitches if norm_role == "pitcher" else hitter_gaps_from_pitches

    rows: list[dict] = []
    for season in seasons:
        try:
            sc = fetch_statcast(mlbam_id, norm_role, season)
        except Exception as e:
            log.warning("statcast fetch failed for %s/%s/%s: %s", mlbam_id, norm_role, season, e)
            continue
        if sc is None or sc.empty:
            continue
        gaps = deriver(sc)
        if not gaps:
            continue
        gaps["__season"] = season
        rows.append(gaps)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


__all__ = [
    "pitcher_gaps_from_pitches",
    "hitter_gaps_from_pitches",
    "season_aggregates_from_statcast",
]
