"""Read-only monitoring endpoints: integrity, sessions, roster, security log."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import room_ids_for_proctor, sitting_for_admin
from app.database import get_db
from app.models import Admin, Answer, Candidate, Exam, ExamEvent, ExamSession, Room, Sitting
from app.models.enums import AdminRole, EventType, SessionStatus
from app.schemas.monitor import (
    RosterCandidate,
    RosterResponse,
    RosterSitting,
    SecurityEventOut,
    SessionSummary,
)
from app.services import session_service

from ._common import _require_proctor, _require_proctor_or_room

router = APIRouter()

_SECURITY_EVENT_TYPES = [
    EventType.LOGIN_ATTEMPT_INVALID_CCCD.value,
    EventType.LOGIN_ATTEMPT_NOT_IN_WHITELIST.value,
    EventType.LOGIN_ATTEMPT_NOT_IN_EXAM.value,
    EventType.LOGIN_RATE_LIMITED.value,
    EventType.REGISTER_DUPLICATE_CCCD.value,
    EventType.SAME_MACHINE_LOGIN.value,
]


# --- integrity --------------------------------------------------------------

@router.get("/sittings/{sitting_id}/integrity")
async def check_integrity(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> dict:
    """Re-hash every finalised session of the sitting vs its stored
    ``results_hash``; any mismatch is logged as ``result_tampered``."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    sessions = list(await db.scalars(
        select(ExamSession).where(
            ExamSession.sitting_id == sitting.id,
            ExamSession.status.in_({SessionStatus.SUBMITTED.value,
                                    SessionStatus.TIMEOUT.value}),
        )
    ))
    ok = 0
    mismatched: list[str] = []
    unsealed: list[str] = []
    for s in sessions:
        answers = list(await db.scalars(select(Answer).where(Answer.session_id == s.id)))
        if not s.results_hash:
            unsealed.append(str(s.id))
            continue
        if session_service.verify_results_hash(s, answers):
            ok += 1
        else:
            mismatched.append(str(s.id))
            db.add(session_service.make_event(
                event_type=EventType.RESULT_TAMPERED.value, session_id=s.id,
                metadata={"sitting_id": str(sitting_id), "stored_hash": s.results_hash,
                          "expected_hash": session_service.compute_results_hash(s, answers)},
            ))
    if mismatched:
        await db.commit()
    return {"checked": len(sessions), "ok": ok,
            "mismatched": mismatched, "unsealed_legacy": unsealed}


# --- listings ---------------------------------------------------------------

async def _room_filter_ids(db: AsyncSession, exam_id, admin: Admin) -> list[uuid.UUID] | None:
    """For a giám thị, the room ids in this exam assigned to them (404 if none).
    Returns None for chủ tịch (no room restriction)."""
    if admin.role != AdminRole.ROOM_PROCTOR.value:
        return None
    ids = await room_ids_for_proctor(db, exam_id, admin)
    if not ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bạn chưa được gán phòng nào trong kỳ thi này.")
    return ids


@router.get("/sittings/{sitting_id}/sessions", response_model=list[SessionSummary])
async def list_sessions(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor_or_room),
) -> list[SessionSummary]:
    sitting = await db.get(Sitting, sitting_id)
    if sitting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy buổi thi")
    if admin.role == AdminRole.PROCTOR.value:
        await sitting_for_admin(db, sitting_id, admin)  # ownership gate
    room_ids = await _room_filter_ids(db, sitting.exam_id, admin)
    stmt = (
        select(ExamSession, Candidate, Room.name)
        .join(Candidate, Candidate.id == ExamSession.candidate_id)
        .outerjoin(Room, Room.id == Candidate.room_id)
        .where(ExamSession.sitting_id == sitting_id)
        .order_by(Candidate.full_name)
    )
    if room_ids is not None:
        stmt = stmt.where(Candidate.room_id.in_(room_ids))
    rows_list = (await db.execute(stmt)).all()
    return [
        SessionSummary(
            session_id=s.id, candidate_id=c.id, cccd=c.cccd, full_name=c.full_name,
            unit=c.unit, category=c.category, attempt_number=c.attempt_number,
            photo_path=c.photo_path, status=s.status, started_at=s.started_at,
            submitted_at=s.submitted_at, end_time=s.end_time,
            score=float(s.score) if s.score is not None else None,
            total_correct=s.total_correct, client_ip=s.client_ip,
            device_id=s.device_id,
            self_registered=c.self_registered,
            paused=s.paused_at is not None,
            room_id=c.room_id, room_name=room_name,
        )
        for s, c, room_name in rows_list
    ]


@router.get("/sittings/{sitting_id}/roster", response_model=RosterResponse)
async def sitting_roster(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> RosterResponse:
    """Dashboard data for the monitor: sitting header + counts of assigned vs
    logged-in candidates (logged-in = has a session in THIS sitting)."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    exam = await db.get(Exam, sitting.exam_id)

    assigned_total = await db.scalar(
        select(func.count(Candidate.id)).where(Candidate.exam_id == sitting.exam_id)
    ) or 0
    # Vắng (absent) không tính là đã đăng nhập (AD-68).
    absent_total = await db.scalar(
        select(func.count(ExamSession.id)).where(
            ExamSession.sitting_id == sitting_id,
            ExamSession.status == SessionStatus.ABSENT.value,
        )
    ) or 0
    logged_in = await db.scalar(
        select(func.count(ExamSession.id)).where(
            ExamSession.sitting_id == sitting_id,
            ExamSession.status != SessionStatus.ABSENT.value,
        )
    ) or 0
    self_registered_total = await db.scalar(
        select(func.count(Candidate.id)).where(
            Candidate.exam_id == sitting.exam_id, Candidate.self_registered.is_(True))
    ) or 0

    session_cand_ids = select(ExamSession.candidate_id).where(ExamSession.sitting_id == sitting_id)
    pending = (await db.execute(
        select(Candidate, Room.name)
        .outerjoin(Room, Room.id == Candidate.room_id)
        .where(Candidate.exam_id == sitting.exam_id, Candidate.id.not_in(session_cand_ids))
        .order_by(Candidate.full_name)
    )).all()

    running_count = await db.scalar(
        select(func.count(ExamSession.id)).where(
            ExamSession.sitting_id == sitting_id,
            ExamSession.status == SessionStatus.IN_PROGRESS.value,
        )
    ) or 0
    earliest_end_time = await db.scalar(
        select(func.min(ExamSession.end_time)).where(
            ExamSession.sitting_id == sitting_id,
            ExamSession.status == SessionStatus.IN_PROGRESS.value,
            ExamSession.end_time.is_not(None),
        )
    )

    return RosterResponse(
        sitting=RosterSitting(
            sitting_id=sitting.id, exam_id=sitting.exam_id,
            exam_name=exam.name if exam else "", sitting_name=sitting.name,
            exam_date=exam.exam_date.isoformat() if exam and exam.exam_date else None,
            duration_minutes=sitting.duration_minutes, status=sitting.status,
            question_count=sitting.question_count or 0,
        ),
        assigned_total=assigned_total,
        logged_in=logged_in,
        absent_total=absent_total,
        not_logged_in_total=len(pending),
        self_registered_total=self_registered_total,
        earliest_end_time=earliest_end_time,
        running_count=int(running_count),
        server_time=datetime.now(timezone.utc),
        not_logged_in=[
            RosterCandidate(
                candidate_id=c.id, cccd=c.cccd, full_name=c.full_name,
                unit=c.unit, category=c.category, attempt_number=c.attempt_number,
                photo_path=c.photo_path, self_registered=c.self_registered,
                room_name=room_name,
            )
            for c, room_name in pending
        ],
    )


@router.get("/security/failed-logins", response_model=list[SecurityEventOut])
async def failed_logins(
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[SecurityEventOut]:
    rows = list(await db.scalars(
        select(ExamEvent)
        .where(ExamEvent.event_type.in_(_SECURITY_EVENT_TYPES))
        .order_by(ExamEvent.created_at.desc())
        .limit(limit)
    ))
    return [
        SecurityEventOut(
            id=e.id, event_type=e.event_type, cccd_attempted=e.cccd_attempted,
            client_ip=e.client_ip, created_at=e.created_at, metadata=e.event_metadata,
        )
        for e in rows
    ]
