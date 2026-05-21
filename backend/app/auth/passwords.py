"""Password hashing — bcrypt directly.

We use the `bcrypt` package without passlib's wrapper. passlib 1.7.x and
bcrypt >= 4.x have a known incompatibility (passlib can't detect the bcrypt
version), and passlib itself is in maintenance mode.

bcrypt has a 72-byte limit. We pre-hash with SHA-256 so arbitrarily long
passwords work without surprising truncation. This is a standard pattern;
the SHA-256 digest fits in 64 hex chars / 32 raw bytes.
"""

from __future__ import annotations

import hashlib

import bcrypt


_BCRYPT_ROUNDS = 12


def _normalize(password: str) -> bytes:
    # SHA-256 -> hex (64 ASCII chars) -> bytes. Within bcrypt's 72-byte limit,
    # collision-resistant, and password length is no longer observable from
    # the input shape.
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(_normalize(password), salt).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_normalize(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        # Malformed hash, etc. — treat as bad password.
        return False
