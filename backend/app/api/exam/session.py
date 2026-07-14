"""Candidate session state (poll / resume)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_candidate
from app.api.exam.auth import _session_state
from app.core.redis import redis_client
from app.database import get_db
from app.models import Candidate, Exam, ExamSession
from app.models.enums import ExamStatus
from app.schemas.exam_session import CandidateInfo, CandidateLoginResponse, ExamInfo, SessionStateOut
from app.services import session_service

router = APIRouter()


@router.get("/me", response_model=CandidateLoginResponse)
async def get_me(
    candidate: Candidate = Depends(get_current_candidate),
    db: AsyncSession = Depends(get_db),
) -> CandidateLoginResponse:
    """Authoritative identity for the current token — used by the client to
    restore the displayed name/photo after a reload (the store keeps only the
    token). Always reflects the server, so a hand-edited localStorage can't
    fake a different candidate."""
    exam = await db.get(Exam, candidate.exam_id) if candidate.exam_id else None
    return CandidateLoginResponse(
        token=None,
        candidate=CandidateInfo.model_validate(candidate),
        exam=ExamInfo.model_validate(exam) if exam else None,
    )


@router.get("/state", response_model=SessionStateOut)
async def get_state(
    candidate: Candidate = Depends(get_current_candidate),
    db: AsyncSession = Depends(get_db),
) -> SessionStateOut:
    # Resolve the candidate's CURRENT session (AD-47): if a sitting (buổi) is open,
    # use their session in it (None → they still need to confirm); otherwise show
    # their most recent finished session (last buổi's result screen).
    session = None
    if candidate.exam_id:
        # Đường đọc nóng: id buổi active lấy từ cache Redis (AD-69) — tránh query
        # get_active_sitting xuống DB mỗi cú poll /state của mọi máy.
        active_sid = await session_service.cached_active_sitting_id(
            db, redis_client, candidate.exam_id)
        if active_sid is not None:
            session = await db.scalar(
                select(ExamSession).where(
                    ExamSession.candidate_id == candidate.id,
                    ExamSession.sitting_id == active_sid,
                )
            )
        else:
            session = await db.scalar(
                select(ExamSession)
                .where(ExamSession.candidate_id == candidate.id)
                .order_by(ExamSession.created_at.desc())
                .limit(1)
            )
    return _session_state(session)


@router.get("/kiosk/command")
async def kiosk_command(db: AsyncSession = Depends(get_db)) -> dict:
    """Polled by Exam Kiosk machines (~5s). Returns {"quit": true} when the chủ
    tịch has triggered 'Thoát tất cả máy thi' for any currently-active exam (AD-66).
    No auth + no SEB gate on purpose: idle (not-logged-in) machines must poll too.
    In production the at-most-1-active invariant ensures at most one active exam."""
    # Lệnh quit chỉ tới được khi kỳ thi vẫn ACTIVE; nếu đóng kỳ thi trước thì flag Redis đã bị xoá.
    # Danh sách kỳ thi active lấy từ cache Redis (AD-69) — endpoint này MỌI máy poll
    # mỗi 5s, trước đây query DB mỗi lần là tải áp đảo.
    exams = await session_service.cached_active_exams(db, redis_client)
    if not exams:
        return {"quit": False, "wipe": False}
    ids = [e["id"] for e in exams]
    quit_vals = await redis_client.mget(*[session_service.kiosk_quit_key(i) for i in ids])
    wipe_vals = await redis_client.mget(*[session_service.kiosk_wipe_key(i) for i in ids])
    return {
        "quit": any(v is not None for v in quit_vals),
        "wipe": any(v is not None for v in wipe_vals),
    }
