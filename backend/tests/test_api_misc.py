"""Tests for /api/jobs, /api/auth, /api/analyses (open + protected behavior)."""

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


# ---- Open endpoints --------------------------------------------------------

def test_health_is_open():
    r = _client().get("/api/health")
    assert r.status_code == 200


def test_root_is_open():
    r = _client().get("/")
    assert r.status_code == 200


# ---- Auth requirement on protected routes ----------------------------------

def test_jobs_endpoint_requires_auth():
    r = _client().get("/api/jobs/anything")
    assert r.status_code == 401


def test_players_search_requires_auth():
    r = _client().get("/api/players/search", params={"q": "ohtani"})
    assert r.status_code == 401


def test_analyses_list_requires_auth():
    r = _client().get("/api/analyses")
    assert r.status_code == 401


def test_logout_requires_auth():
    r = _client().post("/api/auth/logout")
    assert r.status_code == 401


def test_me_requires_auth():
    r = _client().get("/api/auth/me")
    assert r.status_code == 401


# ---- With auth -------------------------------------------------------------

def test_jobs_endpoint_404_for_unknown(auth_header):
    c = _client()
    r = c.get("/api/jobs/does-not-exist", headers=auth_header)
    assert r.status_code == 404


def test_me_returns_current_user(auth_header, test_user):
    c = _client()
    r = c.get("/api/auth/me", headers=auth_header)
    assert r.status_code == 200
    assert r.json()["email"] == test_user.email


# ---- OpenAPI ---------------------------------------------------------------

def test_openapi_lists_expected_routes():
    r = _client().get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    expected = {
        "/api/players/search",
        "/api/players/{mlbam_id}/profile",
        "/api/players/{mlbam_id}/analysis",
        "/api/players/{mlbam_id}/metrics/timeseries",
        "/api/players/{mlbam_id}/refresh",
        "/api/jobs/{job_id}",
        "/api/health",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/me",
        "/api/analyses",
        "/api/analyses/save",
        "/api/analyses/{saved_id}",
    }
    missing = expected - set(paths.keys())
    assert not missing, f"OpenAPI is missing routes: {missing}"
