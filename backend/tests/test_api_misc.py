"""Tests for /api/jobs, /api/auth, /api/analyses."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_jobs_endpoint_404_for_unknown():
    r = client.get("/api/jobs/does-not-exist")
    assert r.status_code == 404


def test_auth_endpoints_stub_503():
    r = client.post("/api/auth/login")
    assert r.status_code == 503
    r = client.post("/api/auth/logout")
    assert r.status_code == 503


def test_saved_analyses_endpoints_stub_503():
    r = client.get("/api/analyses")
    assert r.status_code == 503
    r = client.post("/api/analyses/save")
    assert r.status_code == 503


def test_openapi_lists_phase3_routes():
    r = client.get("/openapi.json")
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
        "/api/analyses",
        "/api/analyses/save",
    }
    missing = expected - set(paths.keys())
    assert not missing, f"OpenAPI is missing routes: {missing}"
