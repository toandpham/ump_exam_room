"""Sitting run-control (AD-47).

Control is keyed by SITTING (buổi thi): distribute / start / extend / end act on a
sitting's sessions.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import exam_for_admin, sitting_for_admin
from app.core.redis import redis_client
from app.database import get_db
from app.models import Admin, ExamSession, Sitting
from app.models.enums import EventType, ExamStatus, SessionStatus, SittingStatus
from app.schemas.monitor import DistributeResult, EndResult, ExtendRequest, StartResult
from app.services import exam_assets, session_service
from app.websocket.manager import manager

from ._common import _require_open_sitting, _require_proctor

router = APIRouter()

# SP-2c: lead đếm ngược để mọi máy mở đề cùng lúc. Phải LỚN HƠN chu kỳ poll /state
# để máy nào rớt WS vẫn kịp nhận start_at trước mốc (ready poll = 5s, thường 15s → 30s
# cho biên rộng, chống giật lúc 500 máy cùng vào đề).
START_LEAD_SECONDS = 30


# --- sitting run-control ----------------------------------------------------

@router.post("/sittings/{sitting_id}/distribute", response_model=DistributeResult)
async def distribute(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> DistributeResult:
    """Phát đề: move all waiting sessions of the sitting to ready."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    await _require_open_sitting(db, sitting)
    result = await db.execute(
        update(ExamSession)
        .where(ExamSession.sitting_id == sitting_id, ExamSession.status == SessionStatus.WAITING.value)
        .values(status=SessionStatus.READY.value)
    )
    db.add(session_service.make_event(event_type=EventType.DISTRIBUTE.value,
                                      metadata={"sitting_id": str(sitting_id)}))
    await db.commit()
    await manager.publish("exam", "exam_distributed", exam_id=sitting.exam_id)
    return DistributeResult(updated=result.rowcount or 0)


@router.post("/sittings/{sitting_id}/start", response_model=StartResult)
async def start(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> StartResult:
    """Bắt đầu thi: move ready sessions to in_progress.

    SP-2c: mọi phiên bắt đầu tại MỐC CHUNG start_at (tương lai = now + START_LEAD_SECONDS)
    → máy con đếm ngược rồi mở đề đồng loạt; end_time = start_at + thời lượng nên thời gian
    làm bài bằng nhau. /answer bị chặn trong khi now < session.started_at."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    await _require_open_sitting(db, sitting)
    # SP-2c: mọi phiên bắt đầu tại MỐC CHUNG start_at (tương lai) → máy con đếm ngược
    # rồi mở đề đồng loạt; end_time = start_at + thời lượng nên thời gian làm bài bằng nhau.
    now = datetime.now(timezone.utc)
    start_at = now + timedelta(seconds=START_LEAD_SECONDS)
    end_time = start_at + timedelta(minutes=sitting.duration_minutes)
    result = await db.execute(
        update(ExamSession)
        .where(ExamSession.sitting_id == sitting_id, ExamSession.status == SessionStatus.READY.value)
        .values(status=SessionStatus.IN_PROGRESS.value, started_at=start_at, end_time=end_time)
    )
    db.add(session_service.make_event(event_type=EventType.START.value,
                                      metadata={"sitting_id": str(sitting_id)}))
    await db.commit()
    await manager.publish("exam", "exam_started", exam_id=sitting.exam_id,
                          data={"start_at": start_at.isoformat(), "end_time": end_time.isoformat()})
    return StartResult(started=result.rowcount or 0, end_time=end_time)


@router.post("/sittings/{sitting_id}/extend")
async def extend_time(
    sitting_id: uuid.UUID,
    body: ExtendRequest,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> dict:
    """Cộng giờ (cả buổi): gia hạn end_time cho mọi phiên in_progress của buổi
    thêm ``minutes`` phút (kể cả phiên đã hết giờ → mở lại làm tiếp)."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    delta = timedelta(minutes=body.minutes)
    sessions = list(await db.scalars(
        select(ExamSession).where(
            ExamSession.sitting_id == sitting_id,
            ExamSession.status == SessionStatus.IN_PROGRESS.value,
            ExamSession.end_time.is_not(None),
        )
    ))
    for s in sessions:
        s.end_time = s.end_time + delta
    db.add(session_service.make_event(
        event_type=EventType.START.value,
        metadata={"action": "extend_time", "minutes": body.minutes,
                  "admin": admin.username, "sitting_id": str(sitting_id)},
    ))
    await db.commit()
    await manager.publish("exam", "exam_extended", exam_id=sitting.exam_id,
                          data={"minutes": body.minutes})
    return {"extended": len(sessions), "minutes": body.minutes}


async def _finalize_in_progress(db: AsyncSession, sitting: Sitting) -> int:
    """Force-submit + score every in_progress session of the sitting. Does NOT
    commit — the caller commits after adding its own audit events."""
    correct_map = await session_service.correct_map_for_sitting(db, redis_client, sitting)
    sessions = list(await db.scalars(
        select(ExamSession).where(
            ExamSession.sitting_id == sitting.id,
            ExamSession.status == SessionStatus.IN_PROGRESS.value,
        )
    ))
    now = datetime.now(timezone.utc)
    for s in sessions:
        s.status = SessionStatus.SUBMITTED.value
        s.submitted_at = now
        await session_service.score_session(db, s, correct_map)
    return len(sessions)


@router.post("/sittings/{sitting_id}/end", response_model=EndResult)
async def end_sitting(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> EndResult:
    """Đóng buổi thi: force-submit + score all still-running sessions, then purge
    the sitting's đề (Redis payload + DB ciphertext) and mark it closed. Results +
    answers stay; ``report_snapshot`` + ``question_count`` survive for reports."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    n = await _finalize_in_progress(db, sitting)
    db.add(session_service.make_event(event_type=EventType.EXAM_END.value,
                                      metadata={"sitting_id": str(sitting_id), "submitted": n}))
    had_payload = await session_service.sitting_has_payload(db, sitting.id)
    redis_deleted = await redis_client.delete(session_service.payload_key(sitting.id))
    sitting.encrypted_payload = None
    # SP-1: xoá file ảnh tĩnh của buổi (đề bị purge → ảnh không được để lại trên đĩa).
    assets_wiped = exam_assets.wipe_sitting_assets(sitting.id)
    sitting.status = SittingStatus.CLOSED.value
    db.add(session_service.make_event(
        event_type=EventType.EXAM_PURGED.value,
        metadata={"sitting_id": str(sitting_id), "had_db_payload": had_payload,
                  "redis_payload_deleted": bool(redis_deleted),
                  "assets_wiped": assets_wiped},
    ))
    # SP-4: yêu cầu mọi máy kiosk xoá đề + đáp án local (âm thầm). Cờ sống 5'
    # để máy đang offline tạm thời quay lại vẫn xoá; mở buổi mới sẽ xoá cờ này.
    await redis_client.set(
        session_service.kiosk_wipe_key(sitting.exam_id), "1", ex=KIOSK_WIPE_TTL_SECONDS)
    await db.commit()
    await manager.publish("exam", "exam_ended", exam_id=sitting.exam_id)
    return EndResult(submitted=n)


@router.post("/exams/{exam_id}/close", response_model=EndResult)
async def close_exam(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> EndResult:
    """Đóng kỳ thi (lưu trữ): archive the exam so a new one can be created
    (at-most-one-active invariant). Refuses while any sitting is still open."""
    exam = await exam_for_admin(db, exam_id, admin)
    active = await session_service.get_active_sitting(db, exam_id)
    if active is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Buổi \"{active.name}\" còn đang mở — hãy đóng buổi trước.")
    exam.status = ExamStatus.CLOSED.value
    db.add(session_service.make_event(event_type=EventType.EXAM_END.value,
                                      metadata={"exam_id": str(exam_id), "action": "archive_exam"}))
    await db.commit()
    return EndResult(submitted=0)


KIOSK_QUIT_TTL_SECONDS = 60
# AD-114: cờ wipe sống TỚI KHI MỞ BUỔI KẾ (mở buổi chủ động xoá cờ — sittings.py).
# Bản cũ TTL 300s tạo lỗ hổng thật ngoài hiện trường: máy TẮT lúc đóng buổi, sáng
# hôm sau bật lên → cờ đã hết hạn → token cũ trong localStorage tự đăng nhập lại
# CCCD của thí sinh trước. TTL dài thì mọi máy boot trong khoảng "giữa 2 buổi" đều
# được xoá sạch (token + cache đề) về màn đăng nhập; không lo wipe nhầm giữa giờ
# thi vì cờ bị XOÁ ngay khi mở buổi.
KIOSK_WIPE_TTL_SECONDS = 48 * 3600


@router.post("/exams/{exam_id}/kiosk-quit")
async def kiosk_quit(
    exam_id: uuid.UUID,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> dict:
    """Thoát tất cả máy thi: set a short-lived Redis flag that every kiosk machine
    of this exam polls (GET /api/exam/kiosk/command). Ownership-gated (AD-30).

    LƯU Ý: kiosk từ v1.3.0 (AD-93) nhận lệnh này sẽ ĐÓNG phần mềm thi về desktop
    (KHÔNG reboot); máy chạy bản cũ hơn vẫn reboot. AD-92 chặn cứng khi CÒN NGƯỜI
    ĐANG THI — một cú bấm nhầm sẽ văng thí sinh khỏi bài toàn phòng. Muốn vẫn gửi
    (máy treo, cần dọn phòng gấp) thì gọi lại với ``force=true``.
    """
    await exam_for_admin(db, exam_id, admin)  # ownership gate (404 if not owner)
    if not force:
        running = await db.scalar(
            select(func.count(ExamSession.id)).where(
                ExamSession.exam_id == exam_id,
                ExamSession.status == SessionStatus.IN_PROGRESS.value,
            )
        ) or 0
        if running:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Còn {running} thí sinh ĐANG LÀM BÀI — lệnh này sẽ khởi động lại máy "
                "của họ. Hãy chờ nộp xong (hoặc đóng buổi thi) rồi mới thoát máy.",
            )
    await redis_client.set(
        session_service.kiosk_quit_key(exam_id), "1", ex=KIOSK_QUIT_TTL_SECONDS)
    db.add(session_service.make_event(
        event_type=EventType.EXAM_END.value,
        metadata={"action": "kiosk_quit", "admin": admin.username, "exam_id": str(exam_id)}))
    await db.commit()
    return {"ok": True, "ttl": KIOSK_QUIT_TTL_SECONDS}
