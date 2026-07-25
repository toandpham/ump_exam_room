"""Đăng nhập thí sinh (whitelist CCCD/hộ chiếu) + trạng thái kỳ thi đang mở."""


from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_exam_client
from app.config import settings
from app.core.limiter import client_ip, device_id, limiter
from app.core.redis import redis_client
from app.core import device_lock
from app.core.identifier import classify_identifier
from app.core.security import create_candidate_token, decode_token
from app.database import get_db
from app.models import Candidate, Exam, ExamSession
from app.models.enums import EventType, ExamStatus
from app.schemas.exam_session import (
    ActiveExamInfo,
    CandidateInfo,
    CandidateLoginResponse,
    CCCDLogin,
    ExamInfo,
    ExamRunningStatus,
)
from app.services import session_service
from app.websocket.manager import manager

router = APIRouter()


from ._common import _assert_device_free, _login_rate_key


@router.post("/login", response_model=CandidateLoginResponse)
@limiter.limit(settings.exam_login_rate, key_func=_login_rate_key)
async def candidate_login(
    request: Request,
    body: CCCDLogin,
    db: AsyncSession = Depends(get_db),
) -> CandidateLoginResponse:
    enforce_exam_client(request)
    ip = client_ip(request)

    # 1. Format — accept a CCCD (12 digits) or a passport (6–9 alnum), AD-58.
    try:
        cccd, _ = classify_identifier(body.cccd)
    except ValueError as exc:
        await session_service.log_event_commit(
            db, event_type=EventType.LOGIN_ATTEMPT_INVALID_CCCD.value,
            cccd=body.cccd.strip(), ip=ip,
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # 2. Whitelist
    candidate = await db.scalar(select(Candidate).where(Candidate.cccd == cccd))
    if candidate is None:
        await session_service.log_event_commit(
            db, event_type=EventType.LOGIN_ATTEMPT_NOT_IN_WHITELIST.value, cccd=cccd, ip=ip
        )
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Bạn không có trong danh sách thí sinh. Vui lòng liên hệ giám thị.",
        )

    # 3. Assigned to an active exam with an open sitting (buổi đang mở).
    exam = await db.get(Exam, candidate.exam_id) if candidate.exam_id else None
    if exam is None or exam.status != ExamStatus.ACTIVE.value:
        await session_service.log_event_commit(
            db, event_type=EventType.LOGIN_ATTEMPT_NOT_IN_EXAM.value, cccd=cccd, ip=ip
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bạn không có lịch thi hôm nay.")
    active_sitting = await session_service.get_active_sitting(db, exam.id)
    if active_sitting is None:
        await session_service.log_event_commit(
            db, event_type=EventType.LOGIN_ATTEMPT_NOT_IN_EXAM.value, cccd=cccd, ip=ip
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Chưa tới giờ thi — chưa có buổi thi nào được mở.")

    # 4. Single-active-device. The reliable signal that the candidate moved to a
    # DIFFERENT machine is the browser device-id, NOT the IP: behind LAN NAT
    # every client reaches the backend as the same reverse-proxy gateway IP, so
    # IP can't tell two machines apart. We compare device-ids (falling back to IP
    # only when no device-id is present). If another device is still live, ask
    # the new one to confirm taking over (unless force=true). A reconnect from
    # the SAME device just silently re-claims — no nagging.
    dev = device_id(request)
    active = await device_lock.get_active(candidate.id)
    prev_ip = active.get("ip") if active else None
    prev_dev = active.get("dev") if active else None
    if dev is not None and prev_dev is not None:
        device_changed = prev_dev != dev
    elif prev_ip is not None and (dev is None or prev_dev is None):
        device_changed = prev_ip != ip      # legacy fallback (no device-id stored)
    else:
        device_changed = False
    other_live_device = device_lock.is_live(active) and active is not None and device_changed
    if other_live_device and not body.force:
        return CandidateLoginResponse(
            candidate=CandidateInfo.model_validate(candidate),
            exam=ExamInfo.model_validate(exam),
            requires_takeover=True,
            active_device_ip=active.get("ip") if active else None,
        )

    # 4b. One machine = one account (AD-32).
    await _assert_device_free(
        db, exam_id=exam.id, dev=dev, cccd=cccd, full_name=candidate.full_name,
        ip=ip, exclude_candidate_id=candidate.id, log_event=True,
    )

    # 5. Resume existing session for the OPEN sitting if any. Refresh its IP +
    # device so the monitor shows where the candidate currently is.
    session = await db.scalar(
        select(ExamSession).where(
            ExamSession.candidate_id == candidate.id,
            ExamSession.sitting_id == active_sitting.id,
        )
    )
    if session is not None:
        session.client_ip = ip
        if dev:
            session.device_id = dev
    db.add(session_service.make_event(
        event_type=EventType.LOGIN_SUCCESS.value, cccd=cccd, ip=ip,
        session_id=session.id if session else None,
    ))
    await db.commit()

    token, _ = create_candidate_token(str(candidate.id), str(exam.id))
    await device_lock.claim(candidate.id, decode_token(token)["jti"], ip, dev)

    # Logged in from a different device than before → warn the proctor (fires for
    # both the confirmed takeover and a silent re-login after the old device went
    # stale, so the monitor always reflects the move). Carries device-ids (short)
    # since IP is the same gateway for everyone on the LAN.
    if device_changed:
        await manager.publish(
            "admin", "candidate_device_switch", exam_id=exam.id,
            session_id=session.id if session else None,
            data={"cccd": cccd, "full_name": candidate.full_name,
                  "old_ip": prev_ip, "new_ip": ip,
                  "old_device": (prev_dev or "")[:8], "new_device": (dev or "")[:8]},
        )

    return CandidateLoginResponse(
        token=token,
        candidate=CandidateInfo.model_validate(candidate),
        exam=ExamInfo.model_validate(exam),
        session_status=session.status if session else None,
    )




@router.get("/status", response_model=ExamRunningStatus)
async def exam_running_status(
    request: Request, db: AsyncSession = Depends(get_db)
) -> ExamRunningStatus:
    """Is there an exam open right now (an ACTIVE kỳ thi)? The exam app shows the
    login form when this is true; otherwise a "no exam in progress" screen that
    keeps polling until one opens (AD-61). Gated on the kỳ thi being active — NOT
    on a buổi being open — per the operator: opening the exam is enough to switch
    candidates to the login screen. Kiosk-gated (AD-91): a plain browser gets 403
    kiosk_required here, so opening /thisinh/ outside the kiosk shows that screen."""
    enforce_exam_client(request)
    # Cache Redis (AD-69): máy chưa đăng nhập poll /status mỗi 5s — tránh query DB mỗi lần.
    exams = await session_service.cached_active_exams(db, redis_client)
    first = exams[0] if exams else None
    return ExamRunningStatus(
        open=first is not None,
        exam_name=first["name"] if first else None,
        allow_registration=first["allow_registration"] if first else False,
    )


@router.get("/active-exams", response_model=list[ActiveExamInfo])
async def list_active_exams(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[ActiveExamInfo]:
    """Kiosk-gated (AD-91): returns the single section currently open (model is
    at-most-one active globally). RegisterScreen displays "you're signing up for
    X" from this response. A plain browser gets 403 kiosk_required like /status."""
    enforce_exam_client(request)
    rows = list(await db.scalars(
        select(Exam).where(Exam.status == ExamStatus.ACTIVE.value).order_by(Exam.name)
    ))
    return [ActiveExamInfo.model_validate(e) for e in rows]


