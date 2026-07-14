"""Candidate authentication: whitelist-only CCCD login, confirm, dispute."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_seb, get_current_candidate
from app.config import settings
from app.core.limiter import client_ip, device_id, limiter
from app.core.redis import redis_client
from app.core import device_lock
from app.core.identifier import classify_identifier
from app.core.security import create_candidate_token, decode_token
from app.database import get_db
from app.models import Candidate, Exam, ExamSession
from app.models.enums import EventType, ExamStatus, SessionStatus
from app.schemas.exam_session import (
    ActiveExamInfo,
    CandidateInfo,
    CandidateLoginResponse,
    CCCDLogin,
    ExamInfo,
    ExamRunningStatus,
    RegisterRequest,
    SessionStateOut,
)
from app.services import session_service
from app.websocket.manager import manager

router = APIRouter()

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


@router.post("/login", response_model=CandidateLoginResponse)
@limiter.limit(settings.exam_login_rate, key_func=_login_rate_key)
async def candidate_login(
    request: Request,
    body: CCCDLogin,
    db: AsyncSession = Depends(get_db),
) -> CandidateLoginResponse:
    enforce_seb(request)
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
    candidates to the login screen. SEB-gated: a plain browser gets 403 seb_required
    here, so opening /thisinh/ outside SEB shows the SEB-required screen (AD-56)."""
    enforce_seb(request)
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
    """SEB-gated (AD-55 I3): returns the single section currently open (model is
    at-most-one active globally). RegisterScreen displays "you're signing up for
    X" from this response. A plain browser gets 403 seb_required like /status."""
    enforce_seb(request)
    rows = list(await db.scalars(
        select(Exam).where(Exam.status == ExamStatus.ACTIVE.value).order_by(Exam.name)
    ))
    return [ActiveExamInfo.model_validate(e) for e in rows]


@router.post("/register", response_model=CandidateLoginResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.exam_login_rate, key_func=_login_rate_key)
async def candidate_register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> CandidateLoginResponse:
    """On-the-spot registration: a candidate fills the form on exam day and
    is added to the whitelist + assigned to an active exam in one go.

    Duplicate CCCD (already registered for ANY exam) is rejected with 409 and
    broadcast to admins as a security warning — possible cheating attempt.
    """
    enforce_seb(request)
    ip = client_ip(request)

    # Accept a CCCD (12 digits) or a passport (6–9 alnum), AD-58.
    try:
        cccd, id_type = classify_identifier(body.cccd)
    except ValueError as exc:
        await session_service.log_event_commit(
            db, event_type=EventType.LOGIN_ATTEMPT_INVALID_CCCD.value,
            cccd=body.cccd.strip(), ip=ip,
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # Pick the target section. At most one section is active at any time
    # (enforced in create_exam), so the single active section is THE target.
    if body.exam_id is not None:
        exam = await db.get(Exam, body.exam_id)
        if exam is None or exam.status != ExamStatus.ACTIVE.value:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kỳ thi không hợp lệ hoặc chưa mở.")
    else:
        exam = await db.scalar(
            select(Exam).where(Exam.status == ExamStatus.ACTIVE.value).limit(1)
        )
        if exam is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                "Hiện chưa có kỳ thi nào đang mở. Liên hệ giám thị.")

    # Section must allow on-the-spot registration (AD-33).
    if not exam.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
            "Kỳ thi này không cho đăng ký tại chỗ. Vui lòng liên hệ giám thị.")

    # One machine = one account: block on-the-spot registration from a browser
    # that already has a live session in this exam (same rule as login 4b).
    await _assert_device_free(
        db, exam_id=exam.id, dev=device_id(request), cccd=cccd,
        full_name=body.full_name, ip=ip,
    )

    # Duplicate CCCD? Three cases:
    #   - already in THIS section → real duplicate, reject + WS alert
    #   - in a different section that's still ACTIVE → reject (cheat suspicion)
    #   - in a section that's draft/closed → "release & move": rebind the
    #     existing record to the new section, refresh info. This is the
    #     ergonomic path so the same person can sit a later sitting.
    existing = await db.scalar(select(Candidate).where(Candidate.cccd == cccd))
    if existing is not None:
        old_exam = await db.get(Exam, existing.exam_id) if existing.exam_id else None
        same_section = old_exam is not None and old_exam.id == exam.id
        old_active = old_exam is not None and old_exam.status == ExamStatus.ACTIVE.value
        if same_section or old_active:
            await session_service.log_event_commit(
                db, event_type=EventType.REGISTER_DUPLICATE_CCCD.value, cccd=cccd, ip=ip,
                metadata={
                    "attempted_name": body.full_name,
                    "existing_name": existing.full_name,
                    "existing_candidate_id": str(existing.id),
                    "existing_exam_id": str(existing.exam_id) if existing.exam_id else None,
                    "target_exam_id": str(exam.id),
                },
            )
            await manager.publish(
                "admin", "register_duplicate_cccd", exam_id=exam.id,
                data={
                    "cccd": cccd, "attempted_name": body.full_name,
                    "existing_name": existing.full_name, "client_ip": ip,
                },
            )
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"CCCD {cccd} đã được đăng ký dưới tên \"{existing.full_name}\" "
                "cho kỳ thi đang diễn ra. Vui lòng liên hệ giám thị.",
            )
        # Release & move: rebind to the new section + refresh info.
        existing.exam_id = exam.id
        existing.id_type = id_type
        existing.full_name = body.full_name.strip()
        existing.birth_date = body.birth_date
        existing.unit = body.unit.strip()
        existing.category = body.category.strip()
        existing.attempt_number = body.attempt_number
        existing.graduation_year = body.graduation_year
        existing.major = body.major.strip() if body.major else None
        existing.self_registered = True
        db.add(session_service.make_event(
            event_type=EventType.REGISTER_SUCCESS.value, cccd=cccd, ip=ip,
            metadata={"candidate_id": str(existing.id), "exam_id": str(exam.id),
                      "moved_from_exam_id": str(old_exam.id) if old_exam else None,
                      "reason": "released-from-closed-section"},
        ))
        await db.commit()
        await db.refresh(existing)
        await manager.publish(
            "admin", "candidate_register", exam_id=exam.id,
            data={"cccd": cccd, "full_name": existing.full_name, "unit": existing.unit},
        )
        token, _ = create_candidate_token(str(existing.id), str(exam.id))
        return CandidateLoginResponse(
            token=token,
            candidate=CandidateInfo.model_validate(existing),
            exam=ExamInfo.model_validate(exam),
            session_status=None,
        )

    candidate = Candidate(
        cccd=cccd,
        id_type=id_type,
        full_name=body.full_name.strip(),
        birth_date=body.birth_date,
        unit=body.unit.strip(),
        category=body.category.strip(),
        attempt_number=body.attempt_number,
        graduation_year=body.graduation_year,
        major=body.major.strip() if body.major else None,
        photo_path=None,  # self-registration has no photo
        exam_id=exam.id,
        self_registered=True,
    )
    db.add(candidate)
    await db.flush()
    db.add(session_service.make_event(
        event_type=EventType.REGISTER_SUCCESS.value, cccd=cccd, ip=ip,
        metadata={"candidate_id": str(candidate.id), "exam_id": str(exam.id)},
    ))
    await db.commit()
    await db.refresh(candidate)

    await manager.publish(
        "admin", "candidate_register", exam_id=exam.id,
        data={"cccd": cccd, "full_name": candidate.full_name, "unit": candidate.unit},
    )

    token, _ = create_candidate_token(str(candidate.id), str(exam.id))
    return CandidateLoginResponse(
        token=token,
        candidate=CandidateInfo.model_validate(candidate),
        exam=ExamInfo.model_validate(exam),
        session_status=None,
    )


@router.post("/confirm", response_model=SessionStateOut)
async def confirm_info(
    request: Request,
    candidate: Candidate = Depends(get_current_candidate),
    db: AsyncSession = Depends(get_db),
) -> SessionStateOut:
    """Candidate confirms displayed info is correct -> create (or resume) the
    session for the currently-open sitting (buổi đang mở)."""
    exam = await db.get(Exam, candidate.exam_id) if candidate.exam_id else None
    if exam is None or exam.status != ExamStatus.ACTIVE.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kỳ thi không còn hoạt động.")
    sitting = await session_service.get_active_sitting(db, exam.id)
    if sitting is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chưa có buổi thi nào được mở.")

    session = await db.scalar(
        select(ExamSession).where(
            ExamSession.candidate_id == candidate.id, ExamSession.sitting_id == sitting.id
        )
    )
    if session is None:
        # Tự nạp lại đề nếu Redis payload đã hết TTL giữa buổi (mở sớm/cộng giờ) —
        # nếu không, thí sinh vào trễ không xác nhận được dù buổi vẫn đang chạy.
        payload = await session_service.ensure_sitting_payload(db, redis_client, sitting)
        if payload is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Đề thi chưa sẵn sàng.")
        # Thí sinh đi trễ: nếu buổi đã bắt đầu (đã có phiên nào được set started_at
        # qua "Bắt đầu thi" / "Duyệt vào thi") thì cho vào thi NGAY với đồng hồ riêng
        # (full thời lượng tính từ bây giờ — AD-47 đồng hồ per-candidate), khỏi chờ
        # giám thị bấm "Duyệt vào thi" từng người. Chưa bắt đầu → "sẵn sàng" như cũ.
        now = datetime.now(timezone.utc)
        already_started = bool(await db.scalar(
            select(func.count()).select_from(ExamSession).where(
                ExamSession.sitting_id == sitting.id,
                ExamSession.started_at.is_not(None),
            )
        ))
        session = ExamSession(
            candidate_id=candidate.id,
            sitting_id=sitting.id,
            exam_id=exam.id,
            # SP-2b: xác nhận xong là "sẵn sàng" luôn (tự phát đề) — máy con tải đề
            # ngầm ngay, chủ tịch chỉ còn bấm "Bắt đầu thi". Thứ tự trộn vẫn tính ngay
            # dưới đây (build_orders) nên mỗi thí sinh một đề trộn riêng.
            status=(SessionStatus.IN_PROGRESS.value if already_started
                    else SessionStatus.READY.value),
            started_at=(now if already_started else None),
            end_time=(now + timedelta(minutes=sitting.duration_minutes)
                      if already_started else None),
            client_ip=client_ip(request),
            device_id=device_id(request),
            user_agent=request.headers.get("user-agent", "")[:512],
        )
        db.add(session)
        await db.flush()
        q_order, o_order = session_service.build_orders(
            str(session.id), payload, sitting.shuffle_questions, sitting.shuffle_options
        )
        session.question_order = q_order
        session.option_order = o_order
        db.add(session_service.make_event(
            event_type=EventType.INFO_CONFIRM.value, session_id=session.id,
            cccd=candidate.cccd, ip=client_ip(request),
        ))
        await db.commit()
        await db.refresh(session)
        await manager.publish(
            "admin", "candidate_login", exam_id=exam.id, session_id=session.id,
            data={"cccd": candidate.cccd, "full_name": candidate.full_name,
                  "status": session.status},
        )

    return _session_state(session)


@router.post("/dispute")
async def dispute_info(
    request: Request,
    candidate: Candidate = Depends(get_current_candidate),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Candidate reports their displayed info is wrong -> log + alert the proctor
    so they can fix it in the Thí sinh tab."""
    await manager.publish(
        "admin", "candidate_info_dispute", exam_id=candidate.exam_id,
        data={"cccd": candidate.cccd, "full_name": candidate.full_name,
              "candidate_id": str(candidate.id)},
    )
    await session_service.log_event_commit(
        db, event_type=EventType.INFO_DISPUTE.value, cccd=candidate.cccd,
        ip=client_ip(request),
        metadata={"candidate_id": str(candidate.id)},
    )
    return {"detail": "Đã ghi nhận. Vui lòng chờ giám thị kiểm tra."}


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
