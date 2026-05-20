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
    (_TMP_ROOT / "cache").mkdir(parents=True, exist_ok=True)


def pytest_unconfigure(config):
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_db_and_cache():
    # Import lazily so env vars are set first.
    from app.db import Base, engine
    from app.models import cache_entry, user  # noqa: F401 — ensure models are registered

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    cache_dir = Path(os.environ["CACHE_DIR"])
    if cache_dir.exists():
        for p in cache_dir.glob("*.parquet"):
            p.unlink()

    yield
