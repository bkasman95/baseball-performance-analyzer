"""Management CLI.

Run inside the container:
    docker compose exec api python -m app.cli create-user --email a@b.c --password 'xxx'
    docker compose exec api python -m app.cli set-password --email a@b.c --password 'xxx'
    docker compose exec api python -m app.cli list-users
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.auth.passwords import hash_password
from app.db import SessionLocal, init_db
from app.models.user import User


def _create_user(email: str, password: str, display_name: str | None) -> int:
    init_db()
    email = email.strip().lower()
    with SessionLocal() as db:
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            print(f"user {email} already exists (id={existing.id})", file=sys.stderr)
            return 1
        u = User(email=email, password_hash=hash_password(password), display_name=display_name)
        db.add(u)
        db.commit()
        print(f"created user {email} (id={u.id})")
        return 0


def _set_password(email: str, password: str) -> int:
    init_db()
    email = email.strip().lower()
    with SessionLocal() as db:
        u = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if u is None:
            print(f"no such user: {email}", file=sys.stderr)
            return 1
        u.password_hash = hash_password(password)
        db.commit()
        print(f"password updated for {email}")
        return 0


def _list_users() -> int:
    init_db()
    with SessionLocal() as db:
        users = db.execute(select(User).order_by(User.id)).scalars().all()
        if not users:
            print("(no users)")
            return 0
        for u in users:
            print(f"{u.id}\t{u.email}\t{u.display_name or ''}\t{u.created_at.isoformat()}")
        return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app.cli", description="DiamondScope management commands")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create-user", help="Create a user with email + password")
    c.add_argument("--email", required=True)
    c.add_argument("--password", required=True)
    c.add_argument("--name", default=None, dest="display_name")

    s = sub.add_parser("set-password", help="Reset an existing user's password")
    s.add_argument("--email", required=True)
    s.add_argument("--password", required=True)

    sub.add_parser("list-users", help="List all users")

    args = p.parse_args(argv)
    if args.command == "create-user":
        return _create_user(args.email, args.password, args.display_name)
    if args.command == "set-password":
        return _set_password(args.email, args.password)
    if args.command == "list-users":
        return _list_users()
    return 2


if __name__ == "__main__":
    sys.exit(main())
