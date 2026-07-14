"""Rate limiting (slowapi).

Because all traffic arrives through Caddy, ``request.client.host`` is the proxy
IP. We key on the first X-Forwarded-For hop (set by Caddy) so limits apply
per real client — essential for brute-force protection on the login endpoints.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


def device_id(request: Request) -> str | None:
    """Per-browser id the exam client sends (random UUID kept in localStorage).
    Used to spot two candidates at the same browser. None if absent."""
    raw = request.headers.get("x-device-id")
    return raw.strip()[:64] if raw else None


# AD-75: storage PHẢI là Redis — in-memory chia bucket theo TỪNG worker, chạy
# 6 worker thì hạn mức thực tế ×6 (chống dò CCCD yếu đi 6 lần). slowapi dùng
# client sync riêng của limits nên không đụng redis.asyncio ở trên.
from app.config import settings as _settings  # noqa: E402

limiter = Limiter(key_func=client_ip, storage_uri=_settings.redis_url)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # Seconds the caller must wait — the limit's window length (worst case). The
    # frontend uses this to show a live countdown instead of a vague "thử lại".
    retry_after = 60
    try:
        retry_after = int(exc.limit.limit.get_expiry())
    except Exception:  # noqa: BLE001 — fall back to a sane default
        pass

    # Best-effort security log of the throttling event (login brute-force signal).
    try:
        from app.database import AsyncSessionLocal
        from app.models import ExamEvent
        from app.models.enums import EventType

        async with AsyncSessionLocal() as db:
            db.add(ExamEvent(
                event_type=EventType.LOGIN_RATE_LIMITED.value,
                client_ip=client_ip(request),
                event_metadata={"path": request.url.path},
            ))
            await db.commit()
    except Exception:  # noqa: BLE001 — never let logging break the 429 response
        pass

    resp = JSONResponse(
        status_code=429,
        content={"detail": "Quá nhiều lần thử. Vui lòng đợi rồi thử lại.",
                 "retry_after": retry_after},
    )
    resp.headers["Retry-After"] = str(retry_after)
    return resp
