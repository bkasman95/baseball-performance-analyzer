"""Admin user seeding.

Called once on app startup. If no users exist AND the ADMIN_EMAIL +
ADMIN_PASSWORD env vars are present, create the admin user. Idempotent —
re-runs are a no-op once a user exists.

This intentionally does NOT update the password of an existing admin from
env on every boot; that would let a leaked env var silently lock people out.
Password rotation goes through the create_user CLI explicitly.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.auth.passwords import hash_password
from app.config import get_settings
from app.db import SessionLocal
from app.models.user import User


log = logging.getLogger(__name__)


def seed_admin_if_empty() -> None:
    settings = get_settings()
    email = (settings.admin_email or "").strip().lower()
    password = settings.admin_password or ""

    if not email or not password or password == "changeme":
        log.info("admin seed skipped (ADMIN_EMAIL / ADMIN_PASSWORD not set)")
        return

    with SessionLocal() as db:
        any_user = db.execute(select(User).limit(1)).first()
        if any_user is not None:
            log.info("admin seed skipped (users table not empty)")
            return

        admin = User(
            email=email,
            display_name="Admin",
            password_hash=hash_password(password),
        )
        db.add(admin)
        db.commit()
        log.info("seeded admin user %s", email)
