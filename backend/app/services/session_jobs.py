"""Tác vụ nền vòng đời phiên thi (tách từ session_service, refactor đợt 3).

- ``auto_submit_expired``: quét mỗi 5s, tự nộp + chấm phiên quá giờ (AD-47).
- ``reconcile_active_sittings``: khởi động lại server → nạp lại payload Redis,
  pause phiên đã quá giờ để chủ tịch quyết (AD-75).
Re-export qua ``app.services.session_service``."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import ExamSession, Sitting
from app.models.enums import EventType, SessionStatus, SittingStatus

from .session_payload import (
    _payload_ttl,
    _rebuild_payload_sync,
    payload_key,
    sitting_payload_blob,
)
from .events import make_event
from .scoring import correct_map_for_sitting, score_session

logger = logging.getLogger("exam.session")


async def auto_submit_expired(redis) -> int:
    """Per-candidate hard stop (AD-47): force-submit + score any in_progress
    session whose OWN clock has run out (``end_time < now``) and that is NOT
    paused. Each candidate finishes on their own independent timer; the chủ tịch
    no longer ends the cohort. Returns how many were auto-submitted.

    Runs on a short interval from the app lifespan. The monitor (8s poll) and the
    candidate client (5s /state poll) pick up the status flip without a WS push.
    """
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        sessions = list(await db.scalars(
            select(ExamSession).where(
                ExamSession.status == SessionStatus.IN_PROGRESS.value,
                ExamSession.paused_at.is_(None),
                ExamSession.end_time.is_not(None),
                ExamSession.end_time < now,
            )
        ))
        if not sessions:
            return 0
        correct_by_sitting: dict = {}
        for s in sessions:
            if s.sitting_id not in correct_by_sitting:
                sitting = await db.get(Sitting, s.sitting_id)
                correct_by_sitting[s.sitting_id] = await correct_map_for_sitting(db, redis, sitting)
            s.status = SessionStatus.TIMEOUT.value
            s.submitted_at = now
            await score_session(db, s, correct_by_sitting[s.sitting_id])
            db.add(make_event(event_type=EventType.TIMEOUT_SUBMIT.value, session_id=s.id,
                              metadata={"sitting_id": str(s.sitting_id)}))
        await db.commit()
    return len(sessions)


async def reconcile_active_sittings(redis) -> int:
    """On startup (e.g. after a reboot that cleared Redis), re-populate the
    decrypted payload into Redis for any active sitting (buổi đang mở) from its
    at-rest ``encrypted_payload``, so candidates can resume without admin
    intervention. Returns how many sittings were reloaded (AD-47).

    Skipped silently if Redis is unreachable — a transient blip must not disturb
    live exams.
    """
    try:
        await redis.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("reconcile_active_sittings skipped — Redis ping failed: %s", exc)
        return 0
    reloaded = 0
    async with AsyncSessionLocal() as db:
        # AD-75: sau mất điện/reboot, phiên in_progress đã trôi QUA end_time sẽ bị
        # sweep auto-submit ~5s sau khi server dậy — nộp "giấy trắng" phần thời gian
        # mất điện, không đường cứu (extend chỉ nhận in_progress). Pause chúng lại
        # TRƯỚC khi sweep chạy: chủ tịch Resume (tự dời end_time bù) hoặc đóng buổi.
        now = datetime.now(timezone.utc)
        overdue = list(await db.scalars(
            select(ExamSession).where(
                ExamSession.status == SessionStatus.IN_PROGRESS.value,
                ExamSession.paused_at.is_(None),
                ExamSession.end_time.is_not(None),
                ExamSession.end_time < now,
            )
        ))
        for s in overdue:
            s.paused_at = now
        if overdue:
            await db.commit()
            logger.warning(
                "reconcile: %d phiên in_progress đã quá end_time lúc khởi động — "
                "ĐÃ TẠM DỪNG thay vì auto-submit (mất điện?). Chủ tịch Resume/Cộng giờ "
                "hoặc Đóng buổi để chấm.", len(overdue),
            )

        actives = list(await db.scalars(
            select(Sitting).where(Sitting.status == SittingStatus.ACTIVE.value)
        ))
        for sitting in actives:
            blob = await sitting_payload_blob(db, sitting.id)
            if await redis.exists(payload_key(sitting.id)) or not blob:
                continue
            try:
                # SP-1: nạp lại sau reboot cũng phải materialize ảnh tĩnh, nếu
                # không /questions rơi về base64 (tái sinh cú spike CPU). Idempotent.
                payload = await asyncio.to_thread(_rebuild_payload_sync, sitting.id, blob)
            except Exception as exc:  # noqa: BLE001 — bad/foreign blob, leave it
                logger.error("Could not reload payload for sitting %s: %s", sitting.id, exc)
                continue
            await redis.set(payload_key(sitting.id),
                            json.dumps(payload, ensure_ascii=False), ex=_payload_ttl(sitting))
            reloaded += 1
            logger.info("Reloaded Redis payload for active sitting %s (%s)",
                        sitting.id, sitting.name)
    return reloaded
