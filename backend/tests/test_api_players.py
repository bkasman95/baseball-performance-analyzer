"""HTTP-level tests for /api/players/* endpoints.

We stub the data layer functions (`search_players`, `get_player_by_mlbam`,
`get_season_aggregates`, `get_statcast`, `get_league_season`, `invalidate`)
so no network or pybaseball is needed.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.data.players import Player
from app.jobs.registry import reset_registry_for_tests


@pytest.fixture
def client(monkeypatch, auth_header):
    # ----- player module stubs --------------------------------------------------
    fake_players = [
        Player(605141, 13510, "Mookie", "Betts", "hitter", 2014, 2025),
        Player(660271, 19755, "Shohei", "Ohtani", "two_way", 2018, 2025),
        Player(545361, 10155, "Mike", "Trout", "hitter", 2011, 2025),
    ]
    by_id = {p.mlbam_id: p for p in fake_players}

    def _search(q: str, limit: int = 10, active_only: bool = True):
        ql = q.lower()
        return [p for p in fake_players if ql in p.full_name.lower()][:limit]

    monkeypatch.setattr("app.api.players.search_players", _search)
    monkeypatch.setattr(
        "app.api.players.get_player_by_mlbam",
        lambda mid, **_kw: by_id.get(mid),
    )

    # ----- aggregates / statcast stubs -----------------------------------------
    def _season_df(_pid, _role, seasons):
        # Mookie-shaped time series; doesn't matter for endpoint contracts.
        seasons = list(seasons)
        return pd.DataFrame({
            "__season": seasons,
            "AVG":  np.linspace(0.295, 0.270, len(seasons)),
            "OBP":  np.linspace(0.380, 0.355, len(seasons)),
            "wOBA": np.linspace(0.390, 0.350, len(seasons)),
            "PA":   [600] * len(seasons),
        })

    def _statcast(_pid, _role, season):
        # 200-pitch synthetic game series with a midseason shift.
        return pd.DataFrame({
            "game_date": pd.date_range(f"{season}-04-01", periods=200, freq="D"),
            "launch_speed": np.concatenate([np.full(100, 88.0), np.full(100, 92.0)]),
            "estimated_woba_using_speedangle": np.concatenate(
                [np.full(100, 0.30), np.full(100, 0.40)]
            ),
        })

    def _league_panel(_role, season):
        rng = np.random.default_rng(season)
        return pd.DataFrame({
            "AVG":  rng.normal(0.252, 0.020, 200),
            "OBP":  rng.normal(0.320, 0.025, 200),
            "wOBA": rng.normal(0.320, 0.028, 200),
            "PA":   rng.integers(100, 700, 200),
        })

    monkeypatch.setattr("app.api.players.get_season_aggregates", _season_df)
    monkeypatch.setattr("app.api.players.get_statcast", _statcast)
    monkeypatch.setattr("app.api.players.get_league_season", _league_panel)
    monkeypatch.setattr("app.api.players.invalidate", lambda prefix: 3)

    # Have the analysis builder use the same stubs. players._run_analysis
    # lazy-imports app.analysis.build_report, so we patch it on that module.
    # Import the underlying implementation directly so the stub can call it
    # without recursing into the monkeypatched name.
    from app.analysis.report import build_report as _real_build_report

    def _build_report_stub(*, player_id, role, season, seasons_window=6, **_kw):
        return _real_build_report(
            player_id=player_id,
            role=role,
            season=season,
            seasons_window=seasons_window,
            fetch_seasons=lambda pid, r, s: _season_df(pid, r, s),
            fetch_statcast=lambda pid, r, s: _statcast(pid, r, s),
            fetch_league_panel=lambda r, s: _league_panel(r, s),
        )

    import app.analysis as analysis_module
    monkeypatch.setattr(analysis_module, "build_report", _build_report_stub)

    reset_registry_for_tests()
    from app.main import app
    tc = TestClient(app)
    tc.headers.update(auth_header)
    return tc


# ---------------------------------------------------------------------------
# Search + profile
# ---------------------------------------------------------------------------

def test_search_returns_matches(client):
    r = client.get("/api/players/search", params={"q": "ohtani"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "ohtani"
    assert any(c["last_name"] == "Ohtani" for c in body["results"])


def test_search_rejects_too_short(client):
    r = client.get("/api/players/search", params={"q": "a"})
    assert r.status_code == 422  # pydantic min_length


def test_profile_returns_404_for_unknown(client):
    r = client.get("/api/players/9999999/profile")
    assert r.status_code == 404


def test_profile_includes_seasons_and_photo(client):
    r = client.get("/api/players/660271/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["mlbam_id"] == 660271
    assert body["full_name"] == "Shohei Ohtani"
    assert 2024 in body["seasons_available"]
    assert "660271" in body["photo_url"]


# ---------------------------------------------------------------------------
# Analysis (async)
# ---------------------------------------------------------------------------

def _wait_for_job(client, job_id, timeout_s=5.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = client.get(f"/api/jobs/{job_id}")
        if r.status_code == 200 and r.json()["status"] in ("complete", "failed"):
            return r.json()
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not complete within {timeout_s}s")


def test_analysis_returns_202_and_job_completes(client):
    r = client.get("/api/players/605141/analysis", params={"season": 2024})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert body["job_status"] in ("pending", "running", "complete")
    job_id = body["job_id"]

    final = _wait_for_job(client, job_id)
    assert final["status"] == "complete"
    assert final["result"] is not None
    assert final["result"]["player_id"] == 605141
    assert final["result"]["role"] in ("hitter", "pitcher")


def test_analysis_deduplicates_concurrent_requests(client):
    r1 = client.get("/api/players/605141/analysis", params={"season": 2024})
    r2 = client.get("/api/players/605141/analysis", params={"season": 2024})
    assert r1.status_code in (200, 202)
    assert r2.status_code in (200, 202)
    # Both should reference the same job (dedup by key).
    j1 = r1.json().get("job_id")
    j2 = r2.json().get("job_id")
    assert j1 and j2 and j1 == j2


def test_analysis_404_on_unknown_player(client):
    r = client.get("/api/players/9999999/analysis")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Timeseries
# ---------------------------------------------------------------------------

def test_timeseries_season_grain(client):
    r = client.get(
        "/api/players/605141/metrics/timeseries",
        params={"metric": "AVG", "grain": "season"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["metric"] == "AVG"
    assert body["grain"] == "season"
    assert len(body["points"]) >= 2
    assert all("y" in p and "x" in p for p in body["points"])


def test_timeseries_rolling_requires_season(client):
    r = client.get(
        "/api/players/605141/metrics/timeseries",
        params={"metric": "wOBA", "grain": "rolling"},
    )
    assert r.status_code == 400


def test_timeseries_rolling_returns_points(client):
    r = client.get(
        "/api/players/605141/metrics/timeseries",
        params={"metric": "wOBA", "grain": "rolling", "season": 2024, "window": 20},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["grain"] == "rolling"
    assert len(body["points"]) > 0


def test_timeseries_unknown_metric_400(client):
    r = client.get(
        "/api/players/605141/metrics/timeseries",
        params={"metric": "NOT_A_METRIC"},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

def test_refresh_invalidates_and_returns_count(client):
    r = client.post("/api/players/605141/refresh", params={"season": 2024})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "accepted"
    assert body["invalidated_keys"] == 3
    assert body["job_id"]  # rebuild job kicked off


def test_refresh_404_on_unknown(client):
    r = client.post("/api/players/9999999/refresh")
    assert r.status_code == 404
