"""Shared API dependencies: authentication and role guards."""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import device_lock, kiosk_guard, seb_config
from app.core.limiter import client_ip, device_id
from app.core.redis import redis_client
from app.core.security import decode_token
from app.database import get_db
from app.models import Admin, Candidate, ExamSession, Room, Sitting
from app.models import Exam
from app.models.enums import AdminRole, SessionStatus

bearer_scheme = HTTPBearer(auto_error=True)

_seb_required_exc = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail={
        "code": "seb_required",
        "message": "Kỳ thi yêu cầu Safe Exam Browser. Vui lòng mở bằng SEB.",
    },
)


_kiosk_required_exc = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail={
        "code": "kiosk_required",
        "message": "Chỉ được làm bài bằng phần mềm thi (Kiosk). "
                   "Vui lòng đóng trình duyệt và mở ứng dụng thi trên máy.",
    },
)


def enforce_exam_client(request: Request) -> None:
    """Chặn mọi request thi không đến từ phần mềm được phép (AD-91).

    Hai lớp độc lập, bật/tắt bằng biến môi trường:
      - ``KIOSK_ONLY`` (mặc định BẬT): chỉ nhận request từ ứng dụng kiosk —
        trình duyệt thường (Firefox/Chrome/Edge…) bị 403 ``kiosk_required``.
      - ``SEB_ENFORCE`` (mặc định TẮT từ AD-64): chỉ nhận request từ Safe Exam
        Browser. Giữ lại làm lối thoát nếu sau này quay về SEB.

    Van xả khi cần cho thi tạm bằng trình duyệt: đặt ``KIOSK_ONLY=false`` trong
    ``.env`` rồi ``docker compose up -d backend``.
    """
    if settings.kiosk_only and not kiosk_guard.is_kiosk_request(request):
        raise _kiosk_required_exc
    if not settings.seb_enforce:
        return
    if not seb_config.verify_seb_header(request, seb_config.current_config_key()):
        raise _seb_required_exc

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Không xác thực được",
    headers={"WWW-Authenticate": "Bearer"},
)


def blacklist_key(jti: str) -> str:
    return f"bl:{jti}"


async def get_exam_or_404(db: AsyncSession, exam_id: uuid.UUID) -> Exam:
    """Fetch an exam by id or raise 404. Shared by the admin routers."""
    exam = await db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề thi")
    return exam


async def exam_for_admin(db: AsyncSession, exam_id: uuid.UUID, admin: Admin) -> Exam:
    """Like get_exam_or_404 but enforces ownership (AD-30): a proctor may only
    touch exams they created (or legacy NULL-owner exams). super_admin sees all.
    Non-owned exams 404 (hide their existence) rather than 403."""
    exam = await get_exam_or_404(db, exam_id)
    if (
        admin.role == AdminRole.PROCTOR.value
        and exam.created_by is not None
        and exam.created_by != admin.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề thi")
    return exam


async def get_sitting_or_404(db: AsyncSession, sitting_id: uuid.UUID) -> Sitting:
    sitting = await db.get(Sitting, sitting_id)
    if sitting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy buổi thi")
    return sitting


async def sitting_for_admin(db: AsyncSession, sitting_id: uuid.UUID, admin: Admin) -> Sitting:
    """Load a sitting, enforcing exam ownership (AD-30/47): a proctor (chủ tịch)
    may only touch sittings of exams they created (or legacy NULL-owner ones);
    super_admin sees all. Non-owned → 404 (hide existence)."""
    sitting = await get_sitting_or_404(db, sitting_id)
    if admin.role == AdminRole.PROCTOR.value:
        exam = await db.get(Exam, sitting.exam_id)
        if exam is not None and exam.created_by is not None and exam.created_by != admin.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy buổi thi")
    return sitting


async def room_ids_for_proctor(db: AsyncSession, exam_id, admin: Admin) -> list[uuid.UUID]:
    """Room ids in this exam assigned to a giám thị (room_proctor). Shared by the
    room-scoping checks across the admin routers (AD-55 M5)."""
    return list(await db.scalars(
        select(Room.id).where(Room.exam_id == exam_id, Room.proctor_id == admin.id)
    ))


async def candidate_in_sitting_for_admin(
    db: AsyncSession,
    sitting_id: uuid.UUID,
    candidate_id: uuid.UUID,
    admin: Admin,
) -> tuple:
    """(Sitting, Candidate) cho thao tác trên 1 thí sinh trong 1 buổi.

    Chủ tịch: sở hữu kỳ thi (AD-30).
    Giám thị: thí sinh phải thuộc phòng của mình.
    404 nếu sai quyền (ẩn sự tồn tại như các helper khác)."""
    sitting = await db.get(Sitting, sitting_id)
    if sitting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy buổi thi")
    cand = await db.get(Candidate, candidate_id)
    if cand is None or cand.exam_id != sitting.exam_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy thí sinh")
    if admin.role == AdminRole.ROOM_PROCTOR.value:
        room_ids = await room_ids_for_proctor(db, sitting.exam_id, admin)
        if cand.room_id not in room_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Thí sinh không thuộc phòng của bạn")
    else:
        await exam_for_admin(db, sitting.exam_id, admin)  # kiểm tra sở hữu cho chủ tịch
    return sitting, cand


async def session_for_pause(db: AsyncSession, session_id: uuid.UUID, admin: Admin) -> ExamSession:
    """Resolve a session a proctor/giám thị may pause or resume (AD-47).

    - super_admin / proctor (chủ tịch): any session of an exam they own.
    - room_proctor (giám thị): only sessions of candidates in a room assigned to
      them.
    Anything else → 404 (hide existence)."""
    session = await db.get(ExamSession, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phiên thi")
    if admin.role == AdminRole.ROOM_PROCTOR.value:
        candidate = await db.get(Candidate, session.candidate_id)
        room = await db.get(Room, candidate.room_id) if candidate and candidate.room_id else None
        if room is None or room.proctor_id != admin.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phiên thi")
        return session
    # proctor / super_admin → exam-ownership gate.
    exam = await db.get(Exam, session.exam_id)
    if (
        admin.role == AdminRole.PROCTOR.value
        and exam is not None and exam.created_by is not None
        and exam.created_by != admin.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phiên thi")
    return session


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    """Resolve the authenticated admin from a Bearer JWT.

    Rejects invalid/expired tokens, revoked (blacklisted) tokens, and inactive
    or missing admin accounts.
    """
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise _credentials_exc

    # Only full admin access tokens (no ``typ``) may reach the API. Candidate
    # tokens (typ=candidate) share the same signing key but must not authorise
    # admin actions.
    if payload.get("typ") is not None:
        raise _credentials_exc

    jti = payload.get("jti")
    if not jti or await redis_client.exists(blacklist_key(jti)):
        raise _credentials_exc

    try:
        admin_id = uuid.UUID(payload.get("sub", ""))
    except (ValueError, TypeError):
        raise _credentials_exc

    admin = await db.get(Admin, admin_id)
    if admin is None or not admin.is_active:
        raise _credentials_exc
    return admin


_device_superseded_exc = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail={
        "code": "device_superseded",
        "message": "Tài khoản của bạn vừa được đăng nhập ở thiết bị khác. "
                   "Phiên làm bài trên thiết bị này đã kết thúc.",
    },
)


async def get_current_candidate(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Candidate:
    """Resolve the authenticated candidate from a candidate Bearer JWT, and
    enforce single-active-device: the token's jti must match the one currently
    registered for this candidate. A newer login on another device supersedes
    this one → 409 device_superseded."""
    enforce_exam_client(request)
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise _credentials_exc
    if payload.get("typ") != "candidate":
        raise _credentials_exc
    try:
        candidate_id = uuid.UUID(payload.get("sub", ""))
    except (ValueError, TypeError):
        raise _credentials_exc
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise _credentials_exc

    jti = payload.get("jti")
    active = await device_lock.get_active(candidate.id)
    # Preserve the stored device-id across heartbeats (the exam client always
    # sends X-Device-Id, but fall back to the stored value just in case).
    dev = device_id(request) or (active.get("dev") if active else None)
    if active is None:
        # Key expired (long-idle) — adopt this token as the active device.
        await device_lock.claim(candidate.id, jti, client_ip(request), dev)
    elif active.get("jti") != jti:
        # Superseded by a newer login. But if this candidate has ALREADY FINISHED
        # (submitted/timeout), don't kick them off their result screen — the exam
        # is over for them, so single-device enforcement no longer matters. Only
        # bounce them while a session could still be in progress (anti-cheat).
        latest_status = await db.scalar(
            select(ExamSession.status)
            .where(ExamSession.candidate_id == candidate.id)
            .order_by(ExamSession.created_at.desc())
            .limit(1)
        )
        if latest_status not in (SessionStatus.SUBMITTED.value, SessionStatus.TIMEOUT.value):
            raise _device_superseded_exc
    else:
        # Heartbeat: keep this device marked live.
        await device_lock.claim(candidate.id, jti, client_ip(request), dev)
    return candidate


def require_roles(*roles: str):
    """Dependency factory enforcing that the current admin has one of ``roles``."""

    async def checker(admin: Admin = Depends(get_current_admin)) -> Admin:
        if admin.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Không đủ quyền"
            )
        return admin

    return checker
