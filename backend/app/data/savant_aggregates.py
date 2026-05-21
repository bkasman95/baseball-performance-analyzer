"""Season aggregates computed from raw Baseball Savant Statcast pitch data.

This module replaces the FanGraphs-derived `batting_stats` / `pitching_stats`
path when FanGraphs is unreachable (e.g. from cloud IPs that they block).
Savant is MLB's official Statcast operation and serves pitch-level data
directly — we aggregate it ourselves.

Trade-offs vs the FanGraphs path:
  - More granular: derived from every pitch / event rather than season totals.
  - Some metrics (xERA, wRC+, park-adjusted figures) require league baselines
    or park factors that aren't trivially derivable from raw Statcast. We
    approximate where reasonable and omit otherwise.
  - Linear weights for wOBA are hard-coded MLB-wide constants. Good enough
    for anomaly detection (which looks at CHANGES, not absolute values).
  - FIP uses a fixed cFIP constant. Same caveat.
"""

from __future__ import annotations

import logging
from typing import Iterable, Literal

import pandas as pd


log = logging.getLogger(__name__)

Role = Literal["pitcher", "hitter", "batting", "pitching"]


# ---------------------------------------------------------------------------
# Linear weights / constants
# ---------------------------------------------------------------------------
# These are MLB-wide ~2023 values. Not park- or year-adjusted. Sufficient for
# detecting year-over-year shifts in a single player's profile.
_WOBA_WEIGHTS = {
    "walk":          0.696,
    "hit_by_pitch":  0.726,
    "single":        0.882,
    "double":        1.247,
    "triple":        1.578,
    "home_run":      2.005,
}
_CFIP = 3.10  # league-average FIP constant; approximation


# Number of outs each terminal PA event contributes. Multi-out events are
# critical for IP: a season with 20 GIDPs is ~6-7 IP we'd otherwise miss,
# which propagates 2-3% errors into WHIP / FIP / HR/9.
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
_OUT_EVENTS = frozenset(_OUT_EVENT_WEIGHTS)
_FB_PITCH_TYPES = {"FF", "FT", "SI", "FA"}
_SL_PITCH_TYPES = {"SL", "ST", "SV"}        # slider, sweeper, slurve
_CB_PITCH_TYPES = {"CU", "KC", "CS"}        # curveball, knuckle curve, slow curve
_CH_PITCH_TYPES = {"CH", "FS", "FO"}        # changeup, splitter, forkball


def _count(series: pd.Series, value: str) -> int:
    return int((series == value).sum())


def _pa_total(df: pd.DataFrame) -> int:
    """Count distinct plate appearances. Statcast assigns at_bat_number per game."""
    if df.empty:
        return 0
    keys = [c for c in ("game_pk", "at_bat_number") if c in df.columns]
    if not keys:
        return 0
    return int(df.drop_duplicates(keys).shape[0])


def _ab_events(df: pd.DataFrame) -> pd.Series:
    """Return one `events` value per PA — the last pitch of each at-bat carries
    the outcome in Statcast's schema."""
    if df.empty or "events" not in df.columns:
        return pd.Series(dtype="object")
    return df["events"].dropna()


# ---------------------------------------------------------------------------
# Pitcher aggregates
# ---------------------------------------------------------------------------

def aggregate_pitcher_season(df: pd.DataFrame) -> dict[str, float | None]:
    """Compute one season of pitcher aggregates from pitch-level Statcast."""
    if df.empty:
        return {}

    pitches = len(df)
    pa = _pa_total(df)
    events = _ab_events(df)

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
    # Each terminal event contributes 1, 2, or 3 outs (see _OUT_EVENT_WEIGHTS).
    outs = int(events.map(_OUT_EVENT_WEIGHTS).fillna(0).sum())
    # Safety net for any out-events not in the weight map: count any PA that
    # didn't reach base as at least 1 out.
    implied_outs = max(pa - (hits + bb + hbp), 0)
    outs = max(outs, implied_outs)
    ip = outs / 3.0 if outs else 0.0

    # Rate stats
    k_pct  = so / pa if pa else 0.0
    bb_pct = bb / pa if pa else 0.0
    whip   = (hits + bb) / ip if ip else 0.0
    hr_9   = (hr / ip) * 9 if ip else 0.0
    avg    = hits / ab if ab else 0.0

    babip_den = ab - so - hr + sac_fly
    babip = (hits - hr) / babip_den if babip_den > 0 else 0.0

    # wOBA via linear weights (against the pitcher)
    woba_num = sum(_WOBA_WEIGHTS[e] * _count(events, e) for e in _WOBA_WEIGHTS)
    woba_den = ab + bb + hbp + sac_fly
    woba = woba_num / woba_den if woba_den else 0.0

    # FIP and a FIP-shaped ERA proxy (we don't have earned runs in pitch data)
    fip = (((13 * hr) + (3 * (bb + hbp)) - (2 * so)) / ip + _CFIP) if ip else 0.0
    # xwOBA against — use BIP-level estimated_woba_using_speedangle if present.
    if "estimated_woba_using_speedangle" in df.columns:
        bip = df.dropna(subset=["launch_speed", "estimated_woba_using_speedangle"])
        if not bip.empty:
            x_bip = float(bip["estimated_woba_using_speedangle"].sum())
            xwoba_num = _WOBA_WEIGHTS["walk"] * bb + _WOBA_WEIGHTS["hit_by_pitch"] * hbp + x_bip
            xwoba = xwoba_num / woba_den if woba_den else 0.0
        else:
            xwoba = woba
    else:
        xwoba = woba

    # Scale xwOBA-against to the ERA range. Statcast's published xERA uses
    # proprietary park / league factors we don't have; empirically the
    # league-wide xwOBA→ERA slope is ~22 ERA points per 0.010 xwOBA. Anchor
    # the line at (league_avg_xwoba=0.310, league_avg_ERA=4.20). When xwoba
    # is zero (no data), fall back to FIP so the metric still has a sensible
    # value.
    xera = (xwoba - 0.310) * 22.0 + 4.20 if xwoba > 0 else fip

    # Contact quality (against)
    batted = df.dropna(subset=["launch_speed"]) if "launch_speed" in df.columns else pd.DataFrame()
    hardhit_pct = float((batted["launch_speed"] >= 95).mean()) if not batted.empty else None
    barrel_pct  = _barrel_rate(batted)

    # CSW%
    desc = df.get("description", pd.Series(dtype="object"))
    called = _count(desc, "called_strike")
    whiff  = _count(desc, "swinging_strike") + _count(desc, "swinging_strike_blocked")
    csw    = (called + whiff) / pitches if pitches else 0.0
    swstr  = whiff / pitches if pitches else 0.0

    # Drivers — velocity / spin / release / pitch mix / zone / first-pitch strike
    pitch_type = df.get("pitch_type", pd.Series(dtype="object"))
    fb_mask = pitch_type.isin(_FB_PITCH_TYPES)
    sl_mask = pitch_type.isin(_SL_PITCH_TYPES)
    cb_mask = pitch_type.isin(_CB_PITCH_TYPES)
    ch_mask = pitch_type.isin(_CH_PITCH_TYPES)

    def _mean(col: str, mask: pd.Series) -> float | None:
        if col not in df.columns or not mask.any():
            return None
        v = df.loc[mask, col].dropna()
        return float(v.mean()) if not v.empty else None

    fbv     = _mean("release_speed",      fb_mask)
    fbspin  = _mean("release_spin_rate",  fb_mask)
    rel_h   = _mean("release_pos_z",      pd.Series([True] * len(df), index=df.index))
    rel_s   = _mean("release_pos_x",      pd.Series([True] * len(df), index=df.index))
    ext     = _mean("release_extension",  pd.Series([True] * len(df), index=df.index))

    fb_use = float(fb_mask.mean()) if pitches else 0.0
    sl_use = float(sl_mask.mean()) if pitches else 0.0
    cb_use = float(cb_mask.mean()) if pitches else 0.0
    ch_use = float(ch_mask.mean()) if pitches else 0.0

    # Zone% — Statcast zone 1..9 is in-strike-zone, 11..14 is outside.
    zone_pct: float | None = None
    if "zone" in df.columns:
        z = pd.to_numeric(df["zone"], errors="coerce").dropna()
        if not z.empty:
            zone_pct = float(((z >= 1) & (z <= 9)).mean())

    # First-pitch strike %
    f_strike_pct: float | None = None
    if "pitch_number" in df.columns and "type" in df.columns:
        first = df[df["pitch_number"] == 1]
        if not first.empty:
            f_strike_pct = float(first["type"].isin(["S", "X"]).mean())

    # Chase induced (O-Swing%) — pitches outside the zone that the batter swung at.
    o_swing_induced_pct: float | None = None
    if "zone" in df.columns and "description" in df.columns:
        z = pd.to_numeric(df["zone"], errors="coerce")
        outside = df[z >= 10]
        if not outside.empty:
            swung = outside["description"].isin([
                "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play",
            ])
            o_swing_induced_pct = float(swung.mean())

    return {
        # Outcomes
        "ERA":      fip,            # FIP-shaped proxy when earned runs aren't available
        "FIP":      fip,
        "xERA":     xera,
        "xFIP":     fip,            # without league HR/FB rate, fall back to FIP
        "WHIP":     whip,
        "K%":       k_pct,
        "BB%":      bb_pct,
        "K-BB%":    k_pct - bb_pct,
        "HR/9":     hr_9,
        "BABIP":    babip,
        "AVG":      avg,
        "wOBA":     woba,
        "HardHit%": hardhit_pct,
        "Barrel%":  barrel_pct,
        "CSW%":     csw,
        # Drivers
        "FBv":              fbv,
        "FBspin (sc)":      fbspin,
        "Release_height":   rel_h,
        "Release_side":     rel_s,
        "Extension":        ext,
        "FB%":              fb_use,
        "SL%":              sl_use,
        "CB%":              cb_use,
        "CH%":              ch_use,
        "Zone%":            zone_pct,
        "F-Strike%":        f_strike_pct,
        "O-Swing%":         o_swing_induced_pct,
        "SwStr%":           swstr,
        # Sample size
        "PA":       pa,
        "IP":       ip,
        "Pitches":  pitches,
    }


# ---------------------------------------------------------------------------
# Hitter aggregates
# ---------------------------------------------------------------------------

def aggregate_hitter_season(df: pd.DataFrame) -> dict[str, float | None]:
    """Compute one season of hitter aggregates from pitch-level Statcast."""
    if df.empty:
        return {}

    pa = _pa_total(df)
    events = _ab_events(df)

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

    avg = hits / ab if ab else 0.0
    obp = (hits + bb + hbp) / pa if pa else 0.0
    slg = tb / ab if ab else 0.0
    ops = obp + slg
    iso = slg - avg
    k_pct  = so / pa if pa else 0.0
    bb_pct = bb / pa if pa else 0.0
    babip_den = ab - so - hr + sac_fly
    babip = (hits - hr) / babip_den if babip_den > 0 else 0.0

    woba_num = sum(_WOBA_WEIGHTS[e] * _count(events, e) for e in _WOBA_WEIGHTS)
    woba_den = ab + bb + hbp + sac_fly
    woba = woba_num / woba_den if woba_den else 0.0

    # xwOBA: walks/HBP weighted same as wOBA, BIPs use estimated_woba_using_speedangle
    if "estimated_woba_using_speedangle" in df.columns:
        bip = df.dropna(subset=["launch_speed", "estimated_woba_using_speedangle"])
        if not bip.empty:
            x_bip = float(bip["estimated_woba_using_speedangle"].sum())
            xwoba_num = _WOBA_WEIGHTS["walk"] * bb + _WOBA_WEIGHTS["hit_by_pitch"] * hbp + x_bip
            xwoba = xwoba_num / woba_den if woba_den else 0.0
        else:
            xwoba = woba
    else:
        xwoba = woba

    # wRC+ requires league wOBA + park factor — out of scope without those.
    # We omit it (analysis layer tolerates missing columns).

    # Plate discipline
    desc = df.get("description", pd.Series(dtype="object"))
    whiff = _count(desc, "swinging_strike") + _count(desc, "swinging_strike_blocked")
    foul  = _count(desc, "foul") + _count(desc, "foul_tip")
    in_play = _count(desc, "hit_into_play")
    swings = whiff + foul + in_play
    pitches = len(df)
    whiff_pct = whiff / swings if swings else None
    contact_pct = (swings - whiff) / swings if swings else None
    swstr_pct = whiff / pitches if pitches else None

    # Chase + Z-Contact
    o_swing_pct: float | None = None
    z_contact_pct: float | None = None
    if "zone" in df.columns:
        z = pd.to_numeric(df["zone"], errors="coerce")
        outside = df[z >= 10]
        if not outside.empty:
            o_swung = outside["description"].isin([
                "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play",
            ])
            o_swing_pct = float(o_swung.mean())
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

    # Contact quality
    batted = df.dropna(subset=["launch_speed"]) if "launch_speed" in df.columns else pd.DataFrame()
    ev      = float(batted["launch_speed"].mean()) if not batted.empty else None
    max_ev  = float(batted["launch_speed"].max())  if not batted.empty else None
    hardhit = float((batted["launch_speed"] >= 95).mean()) if not batted.empty else None
    barrel  = _barrel_rate(batted)
    la      = float(batted["launch_angle"].mean()) if not batted.empty and "launch_angle" in batted.columns else None

    # Batted-ball profile (bb_type categorical)
    gb = fb = ld = None
    if "bb_type" in batted.columns and not batted.empty:
        share = batted["bb_type"].value_counts(normalize=True)
        gb = float(share.get("ground_ball", 0.0))
        fb = float(share.get("fly_ball",   0.0))
        ld = float(share.get("line_drive", 0.0))

    # Bat tracking (2024+) — bat_speed / swing_length come through when present.
    bat_speed = (
        float(df["bat_speed"].dropna().mean()) if "bat_speed" in df.columns and df["bat_speed"].notna().any() else None
    )
    swing_length = (
        float(df["swing_length"].dropna().mean()) if "swing_length" in df.columns and df["swing_length"].notna().any() else None
    )

    return {
        "AVG":       avg,
        "OBP":       obp,
        "SLG":       slg,
        "OPS":       ops,
        "wOBA":      woba,
        "xwOBA":     xwoba,
        "ISO":       iso,
        "K%":        k_pct,
        "BB%":       bb_pct,
        "BABIP":     babip,
        # Drivers
        "avg_bat_speed":      bat_speed,
        "avg_swing_length":   swing_length,
        "O-Swing%":           o_swing_pct,
        "SwStr%":             swstr_pct,
        "Contact%":           contact_pct,
        "Z-Contact%":         z_contact_pct,
        "Whiff%":             whiff_pct,
        "EV":                 ev,
        "maxEV":              max_ev,
        "HardHit%":           hardhit,
        "Barrel%":            barrel,
        "LA":                 la,
        "GB%":                gb,
        "FB%":                fb,
        "LD%":                ld,
        # Sample size
        "PA":      pa,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _barrel_rate(batted: pd.DataFrame) -> float | None:
    """Approximation of Statcast 'Barrel'.

    Statcast's definition is a piecewise EV/LA window that expands with EV:
      EV  98:  LA 26-30   (range 4°)
      EV  99:  LA 25-31   (range 6°)
      EV 100:  LA 24-33   (range 9°)
      …
      EV 116:  LA  8-50   (range 42°)
    Expansion is roughly 1° on each side per +1 mph of EV. That's a close
    enough approximation to land in the right ballpark — a single fixed
    98-mph/26-30° window only catches the narrowest tier and misses most
    real barrels.
    """
    if batted.empty or "launch_angle" not in batted.columns:
        return None
    ev = batted["launch_speed"]
    la = batted["launch_angle"]
    expand = (ev - 98).clip(lower=0)
    la_min = 26 - expand
    la_max = 30 + expand
    barrel = (ev >= 98) & (la >= la_min) & (la <= la_max)
    return float(barrel.mean())


# ---------------------------------------------------------------------------
# Public entry point — produces a DataFrame with the same shape the analysis
# layer expects from FanGraphs.
# ---------------------------------------------------------------------------

def season_aggregates_from_statcast(
    mlbam_id: int,
    role: Role,
    seasons: Iterable[int],
    *,
    fetch_statcast,
) -> pd.DataFrame:
    """One row per season for the given player, columns matching the FanGraphs
    schema the analysis layer expects.

    `fetch_statcast(mlbam_id, role, season)` is injected so the data layer
    can control caching / retries.
    """
    norm_role = "pitcher" if role in ("pitcher", "pitching") else "hitter"
    aggregator = aggregate_pitcher_season if norm_role == "pitcher" else aggregate_hitter_season

    rows: list[dict] = []
    for season in seasons:
        try:
            sc = fetch_statcast(mlbam_id, norm_role, season)
        except Exception as e:
            log.warning("statcast fetch failed for %s/%s/%s: %s", mlbam_id, norm_role, season, e)
            continue
        if sc is None or sc.empty:
            continue
        agg = aggregator(sc)
        if not agg:
            continue
        agg["__season"] = season
        rows.append(agg)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
