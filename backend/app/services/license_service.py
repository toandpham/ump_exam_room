"""Đọc/ghi + cache trạng thái giấy phép (AD-74).

Middleware gọi `current_state()` MỖI request → cache in-process TTL 60s để không
query DB mỗi lần (mỗi uvicorn worker 1 cache riêng — nhập key mới thì worker khác
tự thấy sau ≤60s). `max_seen_at` được đẩy tới lười (≥1h/lần) ngay trong lượt đọc.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.license import LicenseError, LicensePayload, LicenseState, evaluate, parse_key
from app.database import AsyncSessionLocal
from app.models.license import SystemLicense

CACHE_TTL_SECONDS = 60
# Đẩy max_seen_at tối thiểu mỗi giờ — đủ mịn để chống lùi đồng hồ, đủ thưa để
# không ghi DB liên tục.
_TOUCH_INTERVAL = timedelta(hours=1)

_cached: LicenseState | None = None
_cached_at: float = 0.0


def invalidate_cache() -> None:
    global _cached, _cached_at
    _cached, _cached_at = None, 0.0


async def read_state(db: AsyncSession) -> LicenseState:
    """Đọc trạng thái TƯƠI từ DB (không cache) + đẩy max_seen_at nếu tới hạn."""
    row = await db.get(SystemLicense, 1)
    now = datetime.now(timezone.utc)
    state = evaluate(
        row.key if row else None,
        row.installed_at if row else None,
        row.max_seen_at if row else None,
        now=now,
    )
    # Chỉ tiến, không lùi: đồng hồ bị vặn ngược thì giữ nguyên mốc cũ làm bằng chứng.
    if row and now > row.max_seen_at + _TOUCH_INTERVAL:
        row.max_seen_at = now
        await db.commit()
    return state


async def ensure_installed(db: AsyncSession) -> None:
    """AD-81: đảm bảo có dòng license id=1 với ``installed_at`` = lúc cài (dùng thử
    90 ngày bắt đầu tính từ đây). Chạy 1 lần ở startup; idempotent."""
    row = await db.get(SystemLicense, 1)
    if row is None:
        now = datetime.now(timezone.utc)
        db.add(SystemLicense(id=1, installed_at=now, key=None, activated_at=None, max_seen_at=now))
        await db.commit()
        invalidate_cache()


async def current_state() -> LicenseState:
    """Trạng thái cho middleware — cache 60s, tự mở session riêng."""
    global _cached, _cached_at
    if _cached is not None and time.monotonic() - _cached_at < CACHE_TTL_SECONDS:
        return _cached
    async with AsyncSessionLocal() as db:
        state = await read_state(db)
    _cached, _cached_at = state, time.monotonic()
    return state


async def set_key(db: AsyncSession, key: str) -> LicensePayload:
    """Kiểm chữ ký + lưu key GIA HẠN (upsert dòng id=1). Raise LicenseError nếu key sai.

    Dòng luôn tồn tại sau startup (ensure_installed); nếu chưa có thì tạo kèm
    installed_at=now để không mất mốc dùng thử."""
    payload = parse_key(key)
    now = datetime.now(timezone.utc)
    if now >= payload.expires_at:
        raise LicenseError("Key đã hết hạn — xin key mới từ nhà cung cấp")
    row = await db.get(SystemLicense, 1)
    if row is None:
        row = SystemLicense(id=1, installed_at=now, key=key.strip(),
                            activated_at=now, max_seen_at=now)
        db.add(row)
    else:
        row.key = key.strip()
        row.activated_at = now
        row.max_seen_at = max(row.max_seen_at, now)
    await db.commit()
    invalidate_cache()
    return payload
