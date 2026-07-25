"""Helpers dùng chung cho các submodule auth thí sinh (refactor đợt 3).

Tách từ api/exam/auth.py 513 dòng theo pattern candidates/ (AD-75).
``_session_state`` để ở đây vì cả confirm lẫn api/exam/session.py dùng."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import client_ip, device_id
from app.models import Candidate, ExamSession
from app.models.enums import EventType, SessionStatus
from app.schemas.exam_session import (
    SessionStateOut,
)
from app.services import session_service
from app.websocket.manager import manager



_LIVE_STATUSES = [
    SessionStatus.WAITING.value,
    SessionStatus.READY.value,
    SessionStatus.IN_PROGRESS.value,
]


def _login_rate_key(request) -> str:
    """Rate-limit login/register PER MACHINE (X-Device-Id), không theo IP. Vì máy
    thi sau Docker NAT đều ra cùng 1 IP gateway (AD-35) → key theo IP biến giới hạn
    thành bucket DÙNG CHUNG cho mọi thí sinh → đông người đăng nhập là 429 oan
    (AD-69). Mỗi trình duyệt có device-id riêng nên đây là bucket đúng-từng-máy;
    chống dò CCCD từ 1 máy vẫn còn. Thiếu device-id thì lùi về IP."""
    return device_id(request) or client_ip(request)


async def _assert_device_free(
    db: AsyncSession, *, exam_id, dev: str | None, cccd: str, full_name: str,
    ip: str, exclude_candidate_id=None, log_event: bool = False,
) -> None:
    """One machine = one account (AD-32): if this browser (``dev``) already has a
    live session for a DIFFERENT candidate in the exam, alert the proctor and
    reject with 409. Keyed on device-id (not IP) so a NAT'd LAN sharing one
    gateway IP isn't falsely blocked. No-op when ``dev`` is absent."""
    if not dev:
        return
    q = (
        select(Candidate.full_name)
        .join(ExamSession, ExamSession.candidate_id == Candidate.id)
        .where(
            ExamSession.exam_id == exam_id,
            ExamSession.device_id == dev,
            ExamSession.status.in_(_LIVE_STATUSES),
        )
    )
    if exclude_candidate_id is not None:
        q = q.where(ExamSession.candidate_id != exclude_candidate_id)
    busy_name = await db.scalar(q.limit(1))
    if not busy_name:
        return
    await manager.publish(
        "admin", "candidate_same_machine", exam_id=exam_id,
        data={"cccd": cccd, "full_name": full_name, "ip": ip,
              "others": [busy_name], "blocked": True},
    )
    if log_event:
        await session_service.log_event_commit(
            db, event_type=EventType.SAME_MACHINE_LOGIN.value, cccd=cccd, ip=ip,
            metadata={"full_name": full_name, "blocked_other": busy_name, "device_id": dev},
        )
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        f"Máy này đang có thí sinh \"{busy_name}\" làm bài. Mỗi máy chỉ dùng "
        "cho 1 tài khoản — hãy dùng máy khác hoặc báo giám thị.",
    )




def _session_state(session: ExamSession | None) -> SessionStateOut:
    """Per-candidate state (AD-47): pause is now per-session, so the clock freezes
    at THIS candidate's own ``paused_at`` instant."""
    now = datetime.now(timezone.utc)
    paused = bool(session and session.paused_at is not None)
    remaining = session_service.time_remaining(session) if session else None
    return SessionStateOut(
        session_id=session.id if session else None,
        status=session.status if session else None,
        started_at=session.started_at if session else None,
        end_time=session.end_time if session else None,
        submitted_at=session.submitted_at if session else None,
        server_time=now,
        time_remaining_seconds=remaining,
        paused=paused,
    )
