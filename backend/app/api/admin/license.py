"""API giấy phép server (AD-74).

GET  /api/admin/license  — mọi admin xem trạng thái (dashboard cảnh báo sắp hết hạn).
POST /api/admin/license  — CHỈ super_admin nhập key mới.
Cả 2 nằm trong skip-list của middleware license (main.py) để còn vào được khi hết hạn.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, require_roles
from app.core.license import WARN_DAYS, LicenseError, LicenseState
from app.database import get_db
from app.models.enums import AdminRole
from app.schemas.license import LicenseInfo, LicenseSetIn
from app.services import license_service

router = APIRouter()

_super_only = require_roles(AdminRole.SUPER_ADMIN.value)


def _to_info(state: LicenseState) -> LicenseInfo:
    days = state.days_left
    # Cảnh báo khi bị khoá HOẶC sắp hết hạn (≤WARN_DAYS) — dùng thử còn nhiều ngày
    # thì KHÔNG kêu (tránh banner đỏ suốt 90 ngày).
    warn = state.status in ("expired", "missing", "clock_tampered") or (
        days is not None and days <= WARN_DAYS)
    return LicenseInfo(
        status=state.status,
        issued_to=state.issued_to,
        expires_at=state.expires_at,
        days_left=days,
        warn=warn,
    )


@router.get("", response_model=LicenseInfo, dependencies=[Depends(get_current_admin)])
async def get_license(db: AsyncSession = Depends(get_db)) -> LicenseInfo:
    return _to_info(await license_service.read_state(db))


@router.post("", response_model=LicenseInfo, dependencies=[Depends(_super_only)])
async def set_license(body: LicenseSetIn, db: AsyncSession = Depends(get_db)) -> LicenseInfo:
    try:
        await license_service.set_key(db, body.key)
    except LicenseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_info(await license_service.read_state(db))
