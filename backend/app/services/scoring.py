"""Chấm điểm + niêm phong kết quả (tách từ session_service, refactor đợt 3).

Gồm: hash tamper-evident của kết quả (AD-22), chấm 1 phiên, và bảng đáp án đúng
lấy theo thứ tự ưu tiên snapshot → Redis → giải mã DB (AD-69 C1).
Re-export qua ``app.services.session_service``."""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Answer, ExamSession, Sitting
from app.models.enums import EventType

from app.services import exam_package

from .session_payload import (
    get_sitting_payload,
    sitting_payload_blob,
    storage_key,
)
from .events import make_event

logger = logging.getLogger("exam.session")


def compute_results_hash(session: ExamSession, answers: list[Answer]) -> str:
    """Canonical SHA-256 over the bits that constitute the final result.

    Used as a tamper-evident seal: if anyone later edits ``score``,
    ``total_correct``, ``submitted_at`` or an answer row, the hash recomputed
    from the stored data will diverge from the stored ``results_hash``.

    Canonical form is deterministic — answers are sorted by ``question_id``."""
    answer_part = ";".join(
        f"{a.question_id}={a.selected_option or ''}"
        for a in sorted(answers, key=lambda a: str(a.question_id))
    )
    # Normalise score to a fixed 2-decimal string so the seal survives a DB
    # round-trip: at seal time score is a Python float ("10.0") but reloads from
    # the Numeric(6,2) column as Decimal ("10.00"). Without this, /integrity
    # would falsely flag every session as tampered.
    score_str = "" if session.score is None else f"{float(session.score):.2f}"
    h = hashlib.sha256()
    h.update(str(session.id).encode())
    h.update(b"|")
    h.update(score_str.encode())
    h.update(b"|")
    h.update(f"{session.total_correct}".encode())
    h.update(b"|")
    h.update((session.submitted_at.isoformat() if session.submitted_at else "").encode())
    h.update(b"|")
    h.update(answer_part.encode())
    return h.hexdigest()


def verify_results_hash(session: ExamSession, answers: list[Answer]) -> bool:
    """True iff stored ``results_hash`` matches a fresh compute. False also when
    a finalised session has no stored hash (older row pre-sealing)."""
    if not session.results_hash:
        return False
    return compute_results_hash(session, answers) == session.results_hash


async def score_session(
    db: AsyncSession, session: ExamSession, correct_map: dict[str, str]
) -> None:
    """Compute total_correct + score (0..10 scale) from stored answers, then
    seal the result with a SHA-256 hash for tamper detection."""
    answers = list(await db.scalars(select(Answer).where(Answer.session_id == session.id)))
    total_correct = sum(
        1 for a in answers
        if a.selected_option and correct_map.get(str(a.question_id)) == a.selected_option
    )
    total_questions = len(correct_map) or 1
    session.total_correct = total_correct
    session.score = round(total_correct / total_questions * 10, 2)
    session.results_hash = compute_results_hash(session, answers)
    db.add(make_event(
        event_type=EventType.RESULT_SEALED.value, session_id=session.id,
        metadata={"score": float(session.score), "total_correct": total_correct,
                  "total_questions": total_questions, "hash": session.results_hash},
    ))


def correct_map_from_payload(payload: dict | None) -> dict[str, str]:
    if not payload:
        return {}
    return {q["id"]: q["correct_option"] for q in payload["questions"]}


async def correct_map_for_sitting(db: AsyncSession, redis, sitting: Sitting) -> dict[str, str]:
    """{question_id: correct_option} dùng để CHẤM ĐIỂM, lấy theo nguồn bền vững nhất.

    Thứ tự ưu tiên (AD-47):
      1. ``sitting.report_snapshot`` — ghi cố định lúc nạp đề QTI, KHÔNG phụ thuộc
         TTL của payload trên Redis và sống sót sau khi purge đề.
      2. Payload còn sống trên Redis (buổi đang mở).
      3. Giải mã ``encrypted_payload`` lưu tại DB (phương án cuối).

    Sửa lỗi điểm-0-âm-thầm (AD-55): trước đây mọi callers chấm điểm chỉ đọc payload
    Redis; nếu TTL hết trước khi chấm (mở buổi sớm / cộng giờ / duyệt vào trễ đẩy
    end_time vượt TTL) thì ``correct_map`` rỗng → mọi thí sinh bị niêm phong 0 điểm
    trong khi report_snapshot vẫn đúng. Đọc snapshot trước nên không còn lệ thuộc TTL.
    """
    if sitting is not None and sitting.report_snapshot:
        return {
            q["id"]: q["correct_option"]
            for q in sitting.report_snapshot
            if q.get("correct_option")
        }
    payload = await get_sitting_payload(redis, sitting.id) if sitting is not None else None
    if payload:
        return correct_map_from_payload(payload)
    blob = await sitting_payload_blob(db, sitting.id) if sitting is not None else None
    if blob:
        try:
            file_obj = exam_package.parse_exam_file(blob)
            payload = exam_package.decrypt_exam_file(file_obj, storage_key())
            return correct_map_from_payload(payload)
        except Exception as exc:  # noqa: BLE001 — đề hỏng/ngoại lai: để map rỗng
            logger.error("correct_map_for_sitting: không giải mã được đề buổi %s: %s",
                         sitting.id, exc)
    return {}

