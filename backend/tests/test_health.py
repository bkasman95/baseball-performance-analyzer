from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_reports_ok_or_degraded():
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "db" in body and "ok" in body["db"]
    assert "version" in body


def test_root_endpoint_returns_metadata():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "DiamondScope API"
