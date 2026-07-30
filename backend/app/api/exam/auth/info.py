"""Xác nhận thông tin trước khi thi + báo sai thông tin cho giám thị (AD-31)."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_candidate
from app.core.limiter import client_ip, device_id
from app.core.redis import redis_client
from app.database import get_db
from app.models import Candidate, Exam, ExamSession
from app.models.enums import EventType, ExamStatus, SessionStatus
from app.schemas.exam_session import (
    SessionStateOut,
)
from app.services import session_service
from app.websocket.manager import manager

router = APIRouter()


from ._common import _session_state


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
    so they can fix it in the Thí sinh tab.

    AD-122: cờ được ghi vào HỒ SƠ THÍ SINH, không chỉ phát WebSocket. Bộ nghe WS
    phía quản trị đã bị gỡ cùng box Thông báo (AD-77) nên tín hiệu cũ rơi vào hư
    không — giám thị không hề biết có người báo sai (hiện trường 30-07).
    """
    candidate.info_disputed_at = datetime.now(timezone.utc)
    await db.commit()
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


