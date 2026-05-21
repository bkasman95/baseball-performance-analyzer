from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


# ---- Password hashing ------------------------------------------------------

def test_hash_and_verify_password_round_trip():
    from app.auth.passwords import hash_password, verify_password
    h = hash_password("hunter2")
    assert verify_password("hunter2", h)
    assert not verify_password("wrong", h)
    assert not verify_password("hunter2", "not-a-real-hash")


# ---- JWT round trip --------------------------------------------------------

def test_jwt_round_trip():
    from app.auth.jwt import create_access_token, decode_token
    token, exp = create_access_token(user_id=42)
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert "exp" in payload
    assert int(exp.timestamp()) == int(payload["exp"])


def test_jwt_invalid_token_raises():
    import pytest
    from app.auth.jwt import InvalidTokenError, decode_token
    with pytest.raises(InvalidTokenError):
        decode_token("not.a.valid.jwt")


# ---- Login endpoint --------------------------------------------------------

def test_login_success_returns_token(test_user):
    c = _client()
    r = c.post(
        "/api/auth/login",
        data={"username": test_user.email, "password": "secret123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == test_user.email


def test_login_wrong_password_401(test_user):
    c = _client()
    r = c.post(
        "/api/auth/login",
        data={"username": test_user.email, "password": "WRONG"},
    )
    assert r.status_code == 401


def test_login_unknown_user_401():
    c = _client()
    r = c.post(
        "/api/auth/login",
        data={"username": "nobody@nowhere.test", "password": "whatever"},
    )
    assert r.status_code == 401


def test_login_then_authenticated_request(test_user):
    c = _client()
    r = c.post(
        "/api/auth/login",
        data={"username": test_user.email, "password": "secret123"},
    )
    token = r.json()["access_token"]
    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == test_user.email


def test_logout_requires_token_returns_ok(auth_header):
    c = _client()
    r = c.post("/api/auth/logout", headers=auth_header)
    assert r.status_code == 200
    assert r.json()["status"] == "logged_out"


# ---- Auth dependency edge cases --------------------------------------------

def test_protected_route_with_bad_token():
    c = _client()
    r = c.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_protected_route_with_token_for_missing_user():
    from app.auth.jwt import create_access_token
    c = _client()
    # User id 999999 doesn't exist in the fresh-per-test DB.
    token, _ = create_access_token(user_id=999999)
    r = c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
