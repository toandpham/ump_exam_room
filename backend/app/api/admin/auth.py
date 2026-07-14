"""Admin authentication endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import bearer_scheme, blacklist_key, get_current_admin
from app.core import login_guard
from app.core.limiter import client_ip
from app.core.redis import redis_client
from app.core.security import create_access_token, decode_token, hash_password, verify_password
from app.database import get_db
from app.models import Admin, ExamEvent
from app.models.enums import EventType
from app.schemas.auth import AdminMe, ChangePasswordRequest, LoginRequest, TokenResponse

router = APIRouter()


def _locked(seconds: int) -> JSONResponse:
    """429 with the seconds remaining so the UI can count down."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Đăng nhập sai quá nhiều lần. Vui lòng đợi rồi thử lại.",
                 "retry_after": seconds},
        headers={"Retry-After": str(seconds)},
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Password login. Wrong attempts trigger an ESCALATING per-IP lockout
    (60s, then 120s, then 180s… — see login_guard)."""
    ip = client_ip(request)
    locked = await login_guard.seconds_locked(ip)
    if locked:
        return _locked(locked)

    admin = await db.scalar(select(Admin).where(Admin.username == body.username))
    # Same generic error whether the user is missing, inactive, or the password
    # is wrong — avoid leaking which usernames exist.
    if (
        admin is None
        or not admin.is_active
        or not verify_password(body.password, admin.password_hash)
    ):
        lock_seconds = await login_guard.register_failure(ip)
        if lock_seconds:
            db.add(ExamEvent(
                event_type=EventType.LOGIN_RATE_LIMITED.value, client_ip=ip,
                event_metadata={"path": "/admin/auth/login",
                                "username": body.username, "lock_seconds": lock_seconds},
            ))
            await db.commit()
            return _locked(lock_seconds)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai tên đăng nhập hoặc mật khẩu",
        )

    await login_guard.clear(ip)
    token, expires_in = create_access_token(
        subject=str(admin.id), username=admin.username, role=admin.role
    )
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=AdminMe)
async def me(admin: Admin = Depends(get_current_admin)) -> Admin:
    return admin


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Self-service password change for the logged-in admin/proctor."""
    if not verify_password(body.old_password, admin.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mật khẩu hiện tại không đúng")
    admin.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"detail": "Đã đổi mật khẩu"}


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    _: Admin = Depends(get_current_admin),
) -> dict[str, str]:
    """Revoke the current token by blacklisting its jti until it would expire."""
    payload = decode_token(credentials.credentials)
    jti = payload.get("jti")
    ttl = int(payload.get("exp", 0)) - int(time.time())
    if jti and ttl > 0:
        await redis_client.setex(blacklist_key(jti), ttl, "1")
    return {"detail": "Đã đăng xuất"}
