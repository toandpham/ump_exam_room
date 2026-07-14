"""Per-candidate / single-session actions (AD-47, AD-68).

Timers are per-candidate; pause/resume act on a single session and may be issued
by the chủ tịch (any session of an owned exam) or a giám thị (only sessions of
candidates in their room).
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    candidate_in_sitting_for_admin,
    exam_for_admin,
    session_for_pause,
    sitting_for_admin,
)
from app.core import device_lock
from app.database import get_db
from app.models import Admin, ExamSession
from app.models.enums import EventType, SessionStatus
from app.schemas.monitor import AbsentRequest, StartResult
from app.services import session_service
from app.websocket.manager import manager

from ._common import _require_open_sitting, _require_proctor, _require_proctor_or_room

router = APIRouter()


# --- per-candidate pause / resume (AD-47) -----------------------------------

@router.post("/sessions/{session_id}/pause")
async def pause_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor_or_room),
) -> dict:
    """Tạm dừng MỘT thí sinh: freeze their clock + block answer/submit. The chủ
    tịch may pause any session of an owned exam; a giám thị only candidates in
    their room (enforced by ``session_for_pause``). Idempotent."""
    session = await session_for_pause(db, session_id, admin)
    if session.status != SessionStatus.IN_PROGRESS.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Thí sinh chưa làm bài.")
    if session.paused_at is None:
        session.paused_at = datetime.now(timezone.utc)
        db.add(session_service.make_event(
            event_type=EventType.PAUSE.value, session_id=session.id,
            metadata={"admin": admin.username, "candidate_id": str(session.candidate_id)}))
        await db.commit()
        await manager.publish("admin", "candidate_paused", exam_id=session.exam_id,
                              session_id=session.id,
                              data={"candidate_id": str(session.candidate_id)})
    return {"paused": True}


@router.post("/sessions/{session_id}/resume")
async def resume_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor_or_room),
) -> dict:
    """Tiếp tục MỘT thí sinh: shift their own end_time forward by the paused
    duration so they get back exactly the time they had left."""
    session = await session_for_pause(db, session_id, admin)
    if session.paused_at is None:
        return {"resumed": False}  # idempotent
    paused_for = datetime.now(timezone.utc) - session.paused_at
    if session.end_time is not None:
        session.end_time = session.end_time + paused_for
    session.paused_at = None
    db.add(session_service.make_event(
        event_type=EventType.RESUME.value, session_id=session.id,
        metadata={"admin": admin.username, "candidate_id": str(session.candidate_id),
                  "paused_seconds": int(paused_for.total_seconds())}))
    await db.commit()
    await manager.publish("admin", "candidate_resumed", exam_id=session.exam_id,
                          session_id=session.id,
                          data={"candidate_id": str(session.candidate_id)})
    return {"resumed": True, "paused_seconds": int(paused_for.total_seconds())}


@router.post("/sittings/{sitting_id}/pause-all")
async def pause_all(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> dict:
    """Chủ tịch tạm dừng CẢ BUỔI: freeze every running candidate at once (AD-48).
    Timers vẫn per-candidate — chỉ là set paused_at hàng loạt."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    now = datetime.now(timezone.utc)
    sessions = list(await db.scalars(
        select(ExamSession).where(
            ExamSession.sitting_id == sitting_id,
            ExamSession.status == SessionStatus.IN_PROGRESS.value,
            ExamSession.paused_at.is_(None),
        )
    ))
    for s in sessions:
        s.paused_at = now
    db.add(session_service.make_event(
        event_type=EventType.PAUSE.value,
        metadata={"action": "pause_all", "admin": admin.username, "sitting_id": str(sitting_id)}))
    await db.commit()
    await manager.publish("exam", "exam_paused", exam_id=sitting.exam_id)
    return {"paused": len(sessions)}


@router.post("/sittings/{sitting_id}/resume-all")
async def resume_all(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> dict:
    """Chủ tịch tiếp tục CẢ BUỔI: unfreeze everyone, dời end_time riêng từng người."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    now = datetime.now(timezone.utc)
    sessions = list(await db.scalars(
        select(ExamSession).where(
            ExamSession.sitting_id == sitting_id,
            ExamSession.status == SessionStatus.IN_PROGRESS.value,
            ExamSession.paused_at.is_not(None),
        )
    ))
    for s in sessions:
        if s.end_time is not None:
            s.end_time = s.end_time + (now - s.paused_at)
        s.paused_at = None
    db.add(session_service.make_event(
        event_type=EventType.RESUME.value,
        metadata={"action": "resume_all", "admin": admin.username, "sitting_id": str(sitting_id)}))
    await db.commit()
    await manager.publish("exam", "exam_resumed", exam_id=sitting.exam_id)
    return {"resumed": len(sessions)}


# --- single-session actions -------------------------------------------------

@router.post("/sessions/{session_id}/logout")
async def logout_candidate(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> dict:
    """Đăng xuất thí sinh: kick the current device. If not started yet
    (waiting/ready) drop the session so they re-enter clean; if in_progress keep
    the session + answers so they can resume on another machine."""
    session = await db.get(ExamSession, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phiên thi")
    await exam_for_admin(db, session.exam_id, admin)  # ownership gate
    await device_lock.revoke(session.candidate_id)
    cand_id = session.candidate_id
    exam_id = session.exam_id
    not_started = session.status in {SessionStatus.WAITING.value, SessionStatus.READY.value}
    db.add(session_service.make_event(
        event_type=EventType.PROCTOR_LOGOUT.value,
        session_id=None if not_started else session_id,
        metadata={"admin": admin.username,
                  "candidate_id": str(cand_id), "removed_session": not_started},
    ))
    if not_started:
        await db.delete(session)
    await db.commit()
    await manager.publish("admin", "candidate_logout", exam_id=exam_id,
                          data={"candidate_id": str(cand_id)})
    return {"session_id": str(session_id), "logged_out": True, "removed_session": not_started}


@router.post("/sessions/{session_id}/admit", response_model=StartResult)
async def admit_late_candidate(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> StartResult:
    """Duyệt thí sinh đi trễ: push one waiting/ready session straight into the
    exam. Their independent clock = full sitting duration from now (timers are
    per-candidate, so a late start just means they finish later)."""
    session = await db.get(ExamSession, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phiên thi")
    sitting = await sitting_for_admin(db, session.sitting_id, admin)  # ownership gate
    await _require_open_sitting(db, sitting)
    if session.status not in {SessionStatus.WAITING.value, SessionStatus.READY.value}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Chỉ duyệt được thí sinh đang ở trạng thái Chờ / Sẵn sàng.",
        )
    now = datetime.now(timezone.utc)
    end_time = now + timedelta(minutes=sitting.duration_minutes)
    session.status = SessionStatus.IN_PROGRESS.value
    session.started_at = now
    session.end_time = end_time
    db.add(session_service.make_event(
        event_type=EventType.START.value, session_id=session_id,
        metadata={"action": "admit_late", "admin": admin.username,
                  "candidate_id": str(session.candidate_id)},
    ))
    await db.commit()
    await manager.publish("admin", "candidate_admitted", exam_id=session.exam_id,
                          data={"candidate_id": str(session.candidate_id)})
    return StartResult(started=1, end_time=end_time)


# --- đánh dấu vắng (AD-68) -------------------------------------------------

@router.post("/sittings/{sitting_id}/candidates/{candidate_id}/absent")
async def mark_absent(
    sitting_id: uuid.UUID,
    candidate_id: uuid.UUID,
    body: AbsentRequest,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor_or_room),
) -> dict:
    """Đánh dấu/bỏ vắng 1 thí sinh trong buổi.

    Giám thị: chỉ thí sinh thuộc phòng mình.
    Chủ tịch: mọi thí sinh trong kỳ thi mình.
    Thí sinh ĐÃ ĐĂNG NHẬP (có phiên chờ/sẵn sàng/đang làm/đã nộp/hết giờ) là CÓ
    MẶT → 409, không đánh vắng được (đăng xuất trước nếu thật sự cần)."""
    sitting, cand = await candidate_in_sitting_for_admin(db, sitting_id, candidate_id, admin)
    session = (await db.execute(
        select(ExamSession).where(
            ExamSession.sitting_id == sitting_id,
            ExamSession.candidate_id == candidate_id,
        )
    )).scalar_one_or_none()

    if body.absent:
        # Bất kỳ phiên SỐNG nào (trừ chính trạng thái absent) đều nghĩa là thí sinh
        # đã đăng nhập → không được đánh vắng. Chỉ người CHƯA đăng nhập (session
        # None) mới đánh vắng được; phiên absent sẵn có thì idempotent.
        if session is not None and session.status != SessionStatus.ABSENT.value:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Thí sinh đã đăng nhập — không đánh dấu vắng được "
                "(đăng xuất thí sinh trước nếu thật sự cần).",
            )
        if session is None:
            session = ExamSession(
                candidate_id=candidate_id,
                sitting_id=sitting_id,
                exam_id=sitting.exam_id,
                status=SessionStatus.ABSENT.value,
            )
            db.add(session)
        else:
            session.status = SessionStatus.ABSENT.value
        await device_lock.revoke(candidate_id)
        db.add(session_service.make_event(
            event_type=EventType.ABSENT_MARK.value,
            session_id=None,
            metadata={
                "action": "mark_absent",
                "admin": admin.username,
                "candidate_id": str(candidate_id),
                "sitting_id": str(sitting_id),
            },
        ))
        await db.commit()
        await db.refresh(session)
        return {"absent": True, "session_id": str(session.id)}
    else:
        if session is not None and session.status == SessionStatus.ABSENT.value:
            await db.delete(session)
            db.add(session_service.make_event(
                event_type=EventType.ABSENT_MARK.value,
                session_id=None,
                metadata={
                    "action": "unmark_absent",
                    "admin": admin.username,
                    "candidate_id": str(candidate_id),
                    "sitting_id": str(sitting_id),
                },
            ))
            await db.commit()
        return {"absent": False, "session_id": None}
