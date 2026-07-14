"""Admin account management (super_admin only): list/create accounts + reset password."""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.security import hash_password
from app.database import get_db
from app.models import Admin, Candidate, Exam, ExamEvent, ExamSession
from app.models.enums import AdminRole, SessionStatus
from app.schemas.auth import AdminCreate, AdminSummary, PasswordSet
from app.schemas.monitor import SecurityEventOut
from app.schemas.room import RoomProctorCreate
from app.services import server_metrics

router = APIRouter()

_super_only = require_roles(AdminRole.SUPER_ADMIN.value)
_require_proctor = require_roles(AdminRole.PROCTOR.value)
_VALID_ROLES = {AdminRole.SUPER_ADMIN.value, AdminRole.PROCTOR.value,
                AdminRole.ROOM_PROCTOR.value}


@router.get("/dashboard")
async def dashboard(
    _: Admin = Depends(_super_only),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """System overview for the super_admin landing page: exam/account/candidate
    counts. Super_admin doesn't operate exams, so this is read-only aggregate."""
    async def count(model, *where) -> int:
        stmt = select(func.count()).select_from(model)
        for w in where:
            stmt = stmt.where(w)
        return int(await db.scalar(stmt) or 0)

    return {
        "exams": {
            "total": await count(Exam),
            "active": await count(Exam, Exam.status == "active"),
            "closed": await count(Exam, Exam.status == "closed"),
        },
        "accounts": {
            "total": await count(Admin),
            "super_admin": await count(Admin, Admin.role == AdminRole.SUPER_ADMIN.value),
            "proctor": await count(Admin, Admin.role == AdminRole.PROCTOR.value),
            "room_proctor": await count(Admin, Admin.role == AdminRole.ROOM_PROCTOR.value),
        },
        "candidates_total": await count(Candidate),
        "sessions_in_progress": await count(
            ExamSession, ExamSession.status == SessionStatus.IN_PROGRESS.value
        ),
    }


@router.get("/server-stats")
async def server_stats(
    _: Admin = Depends(_super_only),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Live server-health metrics (CPU/RAM/disk/network + DB/Redis) so the
    operator can spot overload before it bites. Polled frequently by the UI."""
    return await server_metrics.collect(db)


@router.get("/audit", response_model=list[SecurityEventOut])
async def audit_log(
    _: Admin = Depends(_super_only),
    db: AsyncSession = Depends(get_db),
    event_type: str | None = Query(default=None, description="lọc đúng 1 loại sự kiện"),
    q: str | None = Query(default=None, description="lọc theo CCCD"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[SecurityEventOut]:
    """Nhật ký hệ thống (super_admin): toàn bộ ``exam_events`` — đăng nhập, nộp
    bài, cảnh báo bảo mật, thao tác giám thị, niêm phong/tamper… — mới nhất
    trước, lọc theo loại + CCCD."""
    stmt = select(ExamEvent).order_by(ExamEvent.created_at.desc())
    if event_type:
        stmt = stmt.where(ExamEvent.event_type == event_type)
    if q and q.strip():
        stmt = stmt.where(ExamEvent.cccd_attempted.ilike(f"%{q.strip()}%"))
    rows = list(await db.scalars(stmt.limit(limit)))
    return [
        SecurityEventOut(
            id=e.id, event_type=e.event_type, cccd_attempted=e.cccd_attempted,
            client_ip=e.client_ip, created_at=e.created_at, metadata=e.event_metadata,
        )
        for e in rows
    ]


@router.get("", response_model=list[AdminSummary])
async def list_admins(
    _: Admin = Depends(_super_only),
    db: AsyncSession = Depends(get_db),
) -> list[Admin]:
    return list(await db.scalars(select(Admin).order_by(Admin.username)))


@router.post("", response_model=AdminSummary, status_code=status.HTTP_201_CREATED)
async def create_admin(
    body: AdminCreate,
    _: Admin = Depends(_super_only),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    """Create a giám thị (proctor) or another super_admin."""
    if body.role not in _VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vai trò không hợp lệ")
    exists = await db.scalar(select(Admin).where(Admin.username == body.username))
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tên đăng nhập đã tồn tại")
    admin = Admin(
        username=body.username,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


@router.post("/{admin_id}/set-password", response_model=AdminSummary)
async def set_password(
    admin_id: uuid.UUID,
    body: PasswordSet,
    _: Admin = Depends(_super_only),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    """Reset an account's password (super_admin)."""
    target = await db.get(Admin, admin_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tài khoản")
    target.password_hash = hash_password(body.password)
    await db.commit()
    await db.refresh(target)
    return target


# --- Giám thị (room_proctor) accounts, managed by the chủ tịch (AD-47) -------

@router.get("/room-proctors", response_model=list[AdminSummary])
async def list_room_proctors(
    _: Admin = Depends(_require_proctor),
    db: AsyncSession = Depends(get_db),
) -> list[Admin]:
    """All giám thị accounts (so the chủ tịch can pick one to assign to a room)."""
    return list(await db.scalars(
        select(Admin).where(Admin.role == AdminRole.ROOM_PROCTOR.value)
        .order_by(Admin.username)
    ))


@router.post("/room-proctors", response_model=AdminSummary,
             status_code=status.HTTP_201_CREATED)
async def create_room_proctor(
    body: RoomProctorCreate,
    _: Admin = Depends(_require_proctor),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    """The chủ tịch creates a giám thị account (role forced to room_proctor)."""
    exists = await db.scalar(select(Admin).where(Admin.username == body.username))
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tên đăng nhập đã tồn tại")
    admin = Admin(
        username=body.username,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=AdminRole.ROOM_PROCTOR.value,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


@router.post("/room-proctors/{admin_id}/set-password", response_model=AdminSummary)
async def reset_room_proctor_password(
    admin_id: uuid.UUID,
    body: PasswordSet,
    _: Admin = Depends(_require_proctor),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    """The chủ tịch resets a giám thị's password."""
    target = await db.get(Admin, admin_id)
    if target is None or target.role != AdminRole.ROOM_PROCTOR.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy giám thị")
    target.password_hash = hash_password(body.password)
    await db.commit()
    await db.refresh(target)
    return target


@router.post("/room-proctors/{admin_id}/reset-pin")
async def reset_room_proctor_pin(
    admin_id: uuid.UUID,
    _: Admin = Depends(_require_proctor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The chủ tịch auto-resets a giám thị's password to a random 6-digit PIN and
    reads it back (to tell the giám thị). Plaintext is returned once, never stored
    (AD-48)."""
    target = await db.get(Admin, admin_id)
    if target is None or target.role != AdminRole.ROOM_PROCTOR.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy giám thị")
    pin = f"{secrets.randbelow(900000) + 100000}"   # 6 digits, 100000..999999
    target.password_hash = hash_password(pin)
    await db.commit()
    return {"id": str(target.id), "username": target.username,
            "full_name": target.full_name, "pin": pin}
