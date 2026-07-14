"""Shared guards + helpers cho các submodule monitor (AD-47)."""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.models import Sitting
from app.models.enums import AdminRole, SittingStatus
from app.services import session_service

_require_proctor = require_roles(AdminRole.PROCTOR.value)
_require_proctor_or_room = require_roles(AdminRole.PROCTOR.value, AdminRole.ROOM_PROCTOR.value)


async def _require_open_sitting(db: AsyncSession, sitting: Sitting) -> None:
    if sitting.status != SittingStatus.ACTIVE.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Buổi thi chưa được mở.")
    # Check IS NOT NULL qua SQL — cột blob deferred, không kéo 100MB+ vào đây.
    if not await session_service.sitting_has_payload(db, sitting.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Buổi thi chưa có đề — nạp QTI trước.")
