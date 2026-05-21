from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_save_then_list(auth_header):
    c = _client()
    save = c.post(
        "/api/analyses/save",
        json={"player_id": 605141, "season": 2024, "player_name": "Mookie Betts", "title": "Pitch mix shift"},
        headers=auth_header,
    )
    assert save.status_code == 201, save.text
    saved = save.json()
    assert saved["player_id"] == 605141
    assert saved["season"] == 2024
    assert saved["title"] == "Pitch mix shift"
    assert saved["id"]

    lst = c.get("/api/analyses", headers=auth_header)
    assert lst.status_code == 200
    rows = lst.json()
    assert len(rows) == 1
    assert rows[0]["id"] == saved["id"]


def test_save_is_idempotent_per_player_season(auth_header):
    c = _client()
    first = c.post(
        "/api/analyses/save",
        json={"player_id": 1, "season": 2024},
        headers=auth_header,
    )
    second = c.post(
        "/api/analyses/save",
        json={"player_id": 1, "season": 2024, "note": "second time"},
        headers=auth_header,
    )
    assert first.json()["id"] == second.json()["id"]


def test_delete_saved(auth_header):
    c = _client()
    save = c.post(
        "/api/analyses/save",
        json={"player_id": 1, "season": 2024},
        headers=auth_header,
    )
    sid = save.json()["id"]

    rm = c.delete(f"/api/analyses/{sid}", headers=auth_header)
    assert rm.status_code == 204

    lst = c.get("/api/analyses", headers=auth_header)
    assert lst.json() == []


def test_cannot_delete_other_users_saved(auth_header, test_user):
    """A user can't delete a saved analysis they don't own."""
    from app.auth.jwt import create_access_token
    from app.auth.passwords import hash_password
    from app.db import SessionLocal
    from app.models.saved_analysis import SavedAnalysis
    from app.models.user import User

    c = _client()
    # Create a second user with their own saved analysis.
    with SessionLocal() as db:
        other = User(email="other@example.com", password_hash=hash_password("x"))
        db.add(other)
        db.flush()
        their = SavedAnalysis(user_id=other.id, player_id=1, season=2024)
        db.add(their)
        db.commit()
        sid = their.id

    rm = c.delete(f"/api/analyses/{sid}", headers=auth_header)
    assert rm.status_code == 404


def test_save_validation_rejects_oversized_note(auth_header):
    c = _client()
    r = c.post(
        "/api/analyses/save",
        json={"player_id": 1, "season": 2024, "note": "x" * 3000},
        headers=auth_header,
    )
    assert r.status_code == 422
