"""Đăng ký tại chỗ (self-register) — AD-33."""


from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_exam_client
from app.config import settings
from app.core.limiter import client_ip, device_id, limiter
from app.core.identifier import classify_identifier
from app.core.security import create_candidate_token
from app.database import get_db
from app.models import Candidate, Exam
from app.models.enums import EventType, ExamStatus
from app.schemas.exam_session import (
    CandidateInfo,
    CandidateLoginResponse,
    ExamInfo,
    RegisterRequest,
)
from app.services import session_service
from app.websocket.manager import manager

router = APIRouter()


from ._common import _assert_device_free, _login_rate_key


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
    enforce_exam_client(request)
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


