"""Tests for the analysis history recording + listing."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.history import (
    record_cache_hit,
    start_history_row,
    attach_job_id,
    wrap_job_for_history,
)
from app.main import app
from app.models.analysis_history import AnalysisHistory


client = TestClient(app)


# ---------------------------------------------------------------------------
# Recording helpers
# ---------------------------------------------------------------------------

def test_record_cache_hit_writes_complete_row(test_user):
    record_cache_hit(
        user_id=test_user.id,
        player_id=605400,
        player_name="Aaron Nola",
        season=2024,
        job_id="abc-123",
        result={"headline": "ok", "findings": []},
    )
    with SessionLocal() as db:
        rows = db.query(AnalysisHistory).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == test_user.id
    assert row.player_id == 605400
    assert row.player_name == "Aaron Nola"
    assert row.season == 2024
    assert row.status == "complete"
    assert row.cache_hit is True
    assert row.job_id == "abc-123"
    assert row.duration_ms == 0
    assert row.response_size_bytes is not None and row.response_size_bytes > 0


def test_start_history_row_creates_running_row(test_user):
    hid = start_history_row(
        user_id=test_user.id, player_id=605400,
        player_name="Aaron Nola", season=2024,
    )
    assert hid is not None
    with SessionLocal() as db:
        row = db.get(AnalysisHistory, hid)
    assert row.status == "running"
    assert row.cache_hit is False
    assert row.completed_at is None
    assert row.duration_ms is None


def test_attach_job_id_updates_row(test_user):
    hid = start_history_row(
        user_id=test_user.id, player_id=1, player_name=None, season=2024,
    )
    attach_job_id(hid, "job-xyz")
    with SessionLocal() as db:
        row = db.get(AnalysisHistory, hid)
    assert row.job_id == "job-xyz"


def test_wrap_job_finalizes_on_success(test_user):
    hid = start_history_row(
        user_id=test_user.id, player_id=1, player_name=None, season=2024,
    )
    wrapped = wrap_job_for_history(hid, lambda: {"headline": "done"})
    out = wrapped()
    assert out == {"headline": "done"}
    with SessionLocal() as db:
        row = db.get(AnalysisHistory, hid)
    assert row.status == "complete"
    assert row.completed_at is not None
    assert row.duration_ms is not None and row.duration_ms >= 0
    assert row.response_size_bytes is not None and row.response_size_bytes > 0
    assert row.error is None


def test_wrap_job_finalizes_on_failure(test_user):
    hid = start_history_row(
        user_id=test_user.id, player_id=1, player_name=None, season=2024,
    )

    def boom():
        raise ValueError("kaboom")

    wrapped = wrap_job_for_history(hid, boom)
    try:
        wrapped()
    except ValueError:
        pass
    with SessionLocal() as db:
        row = db.get(AnalysisHistory, hid)
    assert row.status == "failed"
    assert row.error is not None and "kaboom" in row.error
    assert row.response_size_bytes is None


# ---------------------------------------------------------------------------
# /api/me/history endpoint
# ---------------------------------------------------------------------------

def test_history_endpoint_requires_auth():
    resp = client.get("/api/me/history")
    assert resp.status_code == 401


def test_history_endpoint_lists_user_rows_newest_first(test_user, auth_header):
    # Two rows, distinct timestamps so ordering is deterministic.
    with SessionLocal() as db:
        older = AnalysisHistory(
            user_id=test_user.id, player_id=1, player_name="Older",
            season=2023, status="complete", cache_hit=True,
            created_at=datetime.utcnow() - timedelta(hours=1),
            completed_at=datetime.utcnow() - timedelta(hours=1),
            duration_ms=42, response_size_bytes=100,
        )
        newer = AnalysisHistory(
            user_id=test_user.id, player_id=2, player_name="Newer",
            season=2024, status="complete", cache_hit=False,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=4200, response_size_bytes=5000,
        )
        db.add_all([older, newer])
        db.commit()

    resp = client.get("/api/me/history", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["rows"][0]["player_name"] == "Newer"
    assert body["rows"][1]["player_name"] == "Older"


def test_history_endpoint_excludes_other_users(test_user, auth_header):
    """A second user's rows must not appear in test_user's history."""
    from app.auth.passwords import hash_password
    from app.models.user import User

    with SessionLocal() as db:
        other = User(email="other@example.com",
                     password_hash=hash_password("secret123"), display_name="Other")
        db.add(other)
        db.commit()
        db.refresh(other)
        db.add(AnalysisHistory(
            user_id=other.id, player_id=99, player_name="Other's query",
            season=2024, status="complete", cache_hit=True,
        ))
        db.add(AnalysisHistory(
            user_id=test_user.id, player_id=1, player_name="Mine",
            season=2024, status="complete", cache_hit=True,
        ))
        db.commit()

    resp = client.get("/api/me/history", headers=auth_header)
    assert resp.status_code == 200
    names = [r["player_name"] for r in resp.json()["rows"]]
    assert names == ["Mine"]


def test_history_endpoint_marks_old_running_rows_stale(test_user, auth_header):
    with SessionLocal() as db:
        db.add(AnalysisHistory(
            user_id=test_user.id, player_id=1, player_name="Stuck",
            season=2024, status="running", cache_hit=False,
            created_at=datetime.utcnow() - timedelta(hours=2),
        ))
        db.commit()

    resp = client.get("/api/me/history", headers=auth_header)
    assert resp.json()["rows"][0]["status"] == "stale"


def test_history_endpoint_pagination(test_user, auth_header):
    with SessionLocal() as db:
        for i in range(5):
            db.add(AnalysisHistory(
                user_id=test_user.id, player_id=i, player_name=f"P{i}",
                season=2024, status="complete", cache_hit=True,
                created_at=datetime.utcnow() - timedelta(seconds=i),
            ))
        db.commit()

    resp = client.get("/api/me/history?limit=2&offset=0", headers=auth_header)
    body = resp.json()
    assert body["total"] == 5
    assert len(body["rows"]) == 2
    assert [r["player_name"] for r in body["rows"]] == ["P0", "P1"]

    resp = client.get("/api/me/history?limit=2&offset=2", headers=auth_header)
    assert [r["player_name"] for r in resp.json()["rows"]] == ["P2", "P3"]
