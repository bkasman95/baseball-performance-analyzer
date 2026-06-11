"""Test isolation.

Env vars are set in `pytest_configure` — *before* any `app.*` import — so the
module-level engine is bound to a tmp SQLite DB from the start. Per-test
isolation is then done by truncating tables (no module reloads, which would
double-register SQLAlchemy tables on the shared MetaData).
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest


_TMP_ROOT = Path(tempfile.mkdtemp(prefix="diamondscope_tests_"))


def pytest_configure(config):
    os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_ROOT / 'test.sqlite'}"
    os.environ["CACHE_DIR"] = str(_TMP_ROOT / "cache")
    os.environ["JWT_SECRET"] = "test-secret-do-not-use-in-prod"
    os.environ["ADMIN_EMAIL"] = ""           # disable boot-time seeding
    os.environ["ADMIN_PASSWORD"] = ""
    os.environ["DIAMONDSCOPE_DISABLE_SCHEDULER"] = "1"
    (_TMP_ROOT / "cache").mkdir(parents=True, exist_ok=True)


def pytest_unconfigure(config):
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_db_and_cache():
    # Import lazily so env vars are set first.
    from app.db import Base, engine
    from app.models import cache_entry, user, saved_analysis, analysis_history  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    cache_dir = Path(os.environ["CACHE_DIR"])
    if cache_dir.exists():
        for p in cache_dir.glob("*.parquet"):
            p.unlink()

    yield


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def test_user():
    """Create a user in the DB and return the ORM instance."""
    from app.auth.passwords import hash_password
    from app.db import SessionLocal
    from app.models.user import User

    with SessionLocal() as db:
        u = User(email="tester@example.com", password_hash=hash_password("secret123"), display_name="Tester")
        db.add(u)
        db.commit()
        db.refresh(u)
        # Detach so the caller can use attributes after the session closes.
        db.expunge(u)
        return u


@pytest.fixture
def auth_header(test_user):
    """Return an Authorization header for `test_user`."""
    from app.auth.jwt import create_access_token
    token, _ = create_access_token(user_id=test_user.id)
    return {"Authorization": f"Bearer {token}"}
