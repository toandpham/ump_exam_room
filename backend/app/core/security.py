"""Security primitives: password hashing (bcrypt) and JWT issuing/verification."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


# --- Password hashing -------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt at the configured cost."""
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# --- JWT --------------------------------------------------------------------

def create_access_token(*, subject: str, username: str, role: str) -> tuple[str, int]:
    """Create a signed admin JWT.

    Returns (token, expires_in_seconds). A unique ``jti`` is embedded so the
    token can be revoked via the Redis blacklist on logout.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": subject,
        "username": username,
        "role": role,
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int((expire - now).total_seconds())


def create_candidate_token(candidate_id: str, exam_id: str) -> tuple[str, int]:
    """Create a candidate session JWT (issued after a successful CCCD login)."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": candidate_id,
        "typ": "candidate",
        "exam_id": exam_id,
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int((expire - now).total_seconds())


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises ``jwt.PyJWTError`` on invalid/expired."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
