"""Verify the admin auto-seed is idempotent and respects empty creds."""

import importlib
import os

from sqlalchemy import select

from app.db import SessionLocal
from app.models.user import User


def _seed():
    # Re-import to pick up env changes (and clear the cached settings).
    from app.config import get_settings
    get_settings.cache_clear()
    from app.auth import bootstrap
    importlib.reload(bootstrap)
    bootstrap.seed_admin_if_empty()


def test_seed_creates_admin_when_table_empty(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boot@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "letmein-strong")
    _seed()

    with SessionLocal() as db:
        u = db.execute(select(User).where(User.email == "boot@example.com")).scalar_one()
        assert u.email == "boot@example.com"


def test_seed_is_idempotent(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boot@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "letmein-strong")
    _seed()
    _seed()
    with SessionLocal() as db:
        users = db.execute(select(User)).scalars().all()
        assert len(users) == 1


def test_seed_skipped_when_password_unset(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boot@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    _seed()
    with SessionLocal() as db:
        users = db.execute(select(User)).scalars().all()
        assert len(users) == 0


def test_seed_skipped_for_default_changeme(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boot@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "changeme")
    _seed()
    with SessionLocal() as db:
        users = db.execute(select(User)).scalars().all()
        assert len(users) == 0
