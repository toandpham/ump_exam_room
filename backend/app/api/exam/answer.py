"""Candidate question delivery, answer auto-save, and submit."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_candidate
from app.core.redis import redis_client
from app.database import get_db
from app.models import Answer, Candidate, ExamSession, Sitting
from app.models.enums import EventType, SessionStatus
from app.schemas.answer import (
    AnswerIn,
    AnswerOut,
    AnswersBulkIn,
    AnswersBulkOut,
    ExamBlock,
    ExamQuestion,
    ExamQuestionOption,
    ExamQuestionsOut,
    ExamResult,
    SubmitResult,
)
from app.services import session_service
from app.websocket.manager import manager

router = APIRouter()


async def _current_session(db: AsyncSession, candidate: Candidate) -> ExamSession:
    # Scope to the candidate's session in the currently-open sitting (AD-47), so a
    # leftover session from a previous (closed) buổi can't shadow the new one.
    session = None
    if candidate.exam_id:
        active = await session_service.get_active_sitting(db, candidate.exam_id)
        if active is not None:
            session = await db.scalar(
                select(ExamSession).where(
                    ExamSession.candidate_id == candidate.id,
                    ExamSession.sitting_id == active.id,
                )
            )
    if session is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chưa có phiên thi. Hãy xác nhận thông tin.")
    return session


def _data_url(b64: str | None, mime: str | None) -> str | None:
    if not b64:
        return None
    return f"data:{mime or 'image/jpeg'};base64,{b64}"


def _image_pairs(obj: dict) -> list[tuple[str, str]]:
    """Normalize a question/option's images into ``[(full, thumb), ...]``.

    SP-1: ưu tiên ``url`` tĩnh (Caddy) nếu có; fallback data URL base64 cho
    payload cũ / chưa materialize. Còn accept field legacy ``image_b64``.
    AD-107: ``thumb`` = bản nhỏ hiển thị trong bài (``thumb_url``); payload cũ
    chưa có → thumb = bản đầy đủ (hành vi như trước).
    """
    out: list[tuple[str, str]] = []
    for im in obj.get("images") or []:
        # SP-1: ảnh đã materialize → dùng URL tĩnh (Caddy phục vụ); payload cũ/
        # chưa materialize → fallback data URL base64.
        src = im.get("url") or _data_url(im.get("b64"), im.get("mime"))
        if src:
            out.append((src, im.get("thumb_url") or src))
    if not out:
        legacy = _data_url(obj.get("image_b64"), obj.get("image_mime"))
        if legacy:
            out.append((legacy, legacy))
    return out


@router.get("/questions", response_model=ExamQuestionsOut)
async def get_questions(
    candidate: Candidate = Depends(get_current_candidate),
    db: AsyncSession = Depends(get_db),
) -> ExamQuestionsOut:
    """Deliver the candidate's shuffled questions (correct answers stripped)."""
    session = await _current_session(db, candidate)
    # SP-2b: cho tải đề ở trạng thái READY (prefetch trước giờ) — vẫn ẩn correct_option,
    # time_remaining=None (đồng hồ chỉ chạy khi IN_PROGRESS). WAITING vẫn bị chặn.
    if session.status not in {SessionStatus.READY.value, SessionStatus.IN_PROGRESS.value,
                              SessionStatus.SUBMITTED.value, SessionStatus.TIMEOUT.value}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chưa đến giờ làm bài.")

    # Tự nạp lại đề nếu Redis payload đã hết TTL giữa buổi (mở sớm/cộng giờ/vào trễ)
    # — nếu không, máy vào trễ / reload sẽ 409 dù buổi vẫn đang chạy.
    sitting = await db.get(Sitting, session.sitting_id)
    payload = await session_service.ensure_sitting_payload(db, redis_client, sitting) if sitting else None
    if payload is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề thi không khả dụng.")
    by_id = {q["id"]: q for q in payload["questions"]}

    question_order = session.question_order or [q["id"] for q in payload["questions"]]
    option_order = session.option_order or {}

    # Self-heal stale shuffle: question_order is frozen at confirm-time against
    # the payload that was loaded then. If the admin re-uploads the đề (each QTI
    # parse mints fresh question UUIDs), the saved order points at IDs that no
    # longer exist in the current payload → every lookup misses → the candidate
    # gets a blank screen. Detect that mismatch and recompute the deterministic
    # order against the live payload, dropping now-orphaned answers (they
    # reference the deleted question set and can't be scored).
    if not any(qid in by_id for qid in question_order):
        sitting = await db.get(Sitting, session.sitting_id)
        q_order, o_order = session_service.build_orders(
            str(session.id), payload,
            sitting.shuffle_questions if sitting else False,
            sitting.shuffle_options if sitting else False,
        )
        session.question_order = q_order
        session.option_order = o_order
        await db.execute(delete(Answer).where(Answer.session_id == session.id))
        await db.commit()
        question_order = q_order
        option_order = o_order

    questions: list[ExamQuestion] = []
    for qid in question_order:
        q = by_id.get(qid)
        if q is None:
            continue
        opts_by_id = {o["id"]: o for o in q.get("options", [])}
        ordered_ids = option_order.get(qid) or [o["id"] for o in q.get("options", [])]
        options = []
        for oid in ordered_ids:
            o_pairs = _image_pairs(opts_by_id.get(oid, {}))
            options.append(ExamQuestionOption(
                id=oid,
                text=opts_by_id.get(oid, {}).get("text", ""),
                images=[p[0] for p in o_pairs],
                thumbs=[p[1] for p in o_pairs],
            ))
        q_pairs = _image_pairs(q)
        q_images = [p[0] for p in q_pairs]
        # Khối có thứ tự (AD-98): khối ảnh mang ``index`` trỏ vào ``images`` → đổi
        # thành URL đã materialize (kèm thumb hiển thị, AD-107). Đề cũ không có
        # ``blocks`` → để rỗng, FE lùi về hiển thị text rồi images như trước.
        blocks: list[ExamBlock] = []
        for b in q.get("blocks") or []:
            if b.get("type") == "image":
                idx = b.get("index", 0)
                if 0 <= idx < len(q_pairs):
                    blocks.append(ExamBlock(type="image", src=q_pairs[idx][0], thumb=q_pairs[idx][1]))
            elif b.get("text"):
                blocks.append(ExamBlock(type="text", text=b["text"]))
        questions.append(ExamQuestion(
            id=qid,
            text=q["text"],
            images=q_images,
            thumbs=[p[1] for p in q_pairs],
            blocks=blocks,
            options=options,
        ))

    saved = await db.scalars(select(Answer).where(Answer.session_id == session.id))
    answers = {str(a.question_id): a.selected_option for a in saved if a.selected_option}

    return ExamQuestionsOut(
        status=session.status,
        time_remaining_seconds=session_service.time_remaining(session),
        total=len(questions),
        answers=answers,
        questions=questions,
    )


@router.post("/preload-done")
async def preload_done(
    candidate: Candidate = Depends(get_current_candidate),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """AD-110: máy thí sinh báo 'đã tải xong toàn bộ ảnh đề về cache'. Bảng giám
    sát đếm cờ này → chủ tịch chỉ bấm 'Bắt đầu thi' khi mọi máy đã sẵn đề.
    Idempotent; TTL 12h (sống hết buổi, tự dọn)."""
    session = await _current_session(db, candidate)
    if session.status in {SessionStatus.READY.value, SessionStatus.IN_PROGRESS.value}:
        await redis_client.set(session_service.preload_key(session.id), "1", ex=12 * 3600)
    return {"ok": True}


@router.post("/answer", response_model=AnswerOut)
async def save_answer(
    body: AnswerIn,
    candidate: Candidate = Depends(get_current_candidate),
    db: AsyncSession = Depends(get_db),
) -> AnswerOut:
    session = await _current_session(db, candidate)
    if session.status != SessionStatus.IN_PROGRESS.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Phiên thi không trong trạng thái làm bài.")
    # SP-2c: trong lúc đếm ngược (started_at ở tương lai) chưa được nộp đáp án.
    if session.started_at is not None and datetime.now(timezone.utc) < session.started_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chưa tới giờ bắt đầu làm bài.")
    # Per-candidate pause (AD-47): only THIS candidate is frozen.
    if session.paused_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bài thi của bạn đang tạm dừng — vui lòng chờ giám thị.")
    # Past end_time = locked. The background sweep will auto-submit shortly; until
    # then we reject writes (a paused candidate is excluded above, so a frozen
    # clock never trips this).
    if session.end_time is not None and datetime.now(timezone.utc) > session.end_time:
        raise HTTPException(status.HTTP_409_CONFLICT, "Đã hết giờ làm bài.")
    if str(body.question_id) not in (session.question_order or []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Câu hỏi không thuộc đề của bạn.")

    # Upsert on the unique (session_id, question_id) constraint.
    stmt = pg_insert(Answer).values(
        session_id=session.id,
        question_id=body.question_id,
        selected_option=body.selected_option,
    ).on_conflict_do_update(
        constraint="uq_answer_session_question",
        set_={"selected_option": body.selected_option, "answered_at": datetime.now(timezone.utc)},
    )
    await db.execute(stmt)
    await db.commit()
    await manager.publish(
        "admin", "candidate_answer", exam_id=session.exam_id, session_id=session.id,
        data={"question_id": str(body.question_id), "answered": body.selected_option is not None},
    )
    return AnswerOut(question_id=body.question_id, selected_option=body.selected_option)


@router.post("/answers", response_model=AnswersBulkOut)
async def save_answers_bulk(
    body: AnswersBulkIn,
    candidate: Candidate = Depends(get_current_candidate),
    db: AsyncSession = Depends(get_db),
) -> AnswersBulkOut:
    """Lưu NHIỀU đáp án trong 1 request (AD-69) — client gộp đáp án đẩy theo lô ~mỗi
    20–30s thay vì POST mỗi lần chọn → giảm mạnh số request + WS khi ~1000 máy.
    Một transaction, một commit, MỘT thông báo WS (không per-answer). Câu lạ bị bỏ
    qua thay vì làm hỏng cả lô."""
    session = await _current_session(db, candidate)
    if session.status != SessionStatus.IN_PROGRESS.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Phiên thi không trong trạng thái làm bài.")
    # SP-2c: trong lúc đếm ngược (started_at ở tương lai) chưa được nộp đáp án.
    if session.started_at is not None and datetime.now(timezone.utc) < session.started_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chưa tới giờ bắt đầu làm bài.")
    if session.paused_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bài thi của bạn đang tạm dừng — vui lòng chờ giám thị.")
    if session.end_time is not None and datetime.now(timezone.utc) > session.end_time:
        raise HTTPException(status.HTTP_409_CONFLICT, "Đã hết giờ làm bài.")
    order = set(session.question_order or [])
    now = datetime.now(timezone.utc)
    saved = 0
    for a in body.answers:
        if str(a.question_id) not in order:
            continue
        await db.execute(
            pg_insert(Answer).values(
                session_id=session.id, question_id=a.question_id,
                selected_option=a.selected_option,
            ).on_conflict_do_update(
                constraint="uq_answer_session_question",
                set_={"selected_option": a.selected_option, "answered_at": now},
            )
        )
        saved += 1
    await db.commit()
    if saved:
        await manager.publish(
            "admin", "candidate_answer", exam_id=session.exam_id, session_id=session.id,
            data={"answered": True, "bulk": saved},
        )
    return AnswersBulkOut(saved=saved)


@router.post("/submit", response_model=SubmitResult)
async def submit_exam(
    candidate: Candidate = Depends(get_current_candidate),
    db: AsyncSession = Depends(get_db),
) -> SubmitResult:
    session = await _current_session(db, candidate)
    if session.status != SessionStatus.IN_PROGRESS.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Phiên thi không thể nộp ở trạng thái hiện tại.")
    # SP-2c: trong lúc đếm ngược (started_at ở tương lai) chưa được nộp bài.
    if session.started_at is not None and datetime.now(timezone.utc) < session.started_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chưa tới giờ bắt đầu làm bài.")

    sitting = await db.get(Sitting, session.sitting_id)
    correct_map = await session_service.correct_map_for_sitting(db, redis_client, sitting)
    session.status = SessionStatus.SUBMITTED.value
    session.submitted_at = datetime.now(timezone.utc)
    await session_service.score_session(db, session, correct_map)
    db.add(session_service.make_event(
        event_type=EventType.SUBMIT.value, session_id=session.id, cccd=candidate.cccd,
    ))
    await db.commit()

    answered = len(list(await db.scalars(
        select(Answer).where(Answer.session_id == session.id, Answer.selected_option.is_not(None))
    )))
    total = len(session.question_order or [])
    await manager.publish(
        "admin", "candidate_submit", exam_id=session.exam_id, session_id=session.id,
        data={"status": session.status, "score": float(session.score) if session.score is not None else None,
              "total_correct": session.total_correct, "answered": answered},
    )
    return SubmitResult(
        status=session.status, submitted_at=session.submitted_at,
        answered=answered, total=total,
        total_correct=session.total_correct,
    )


@router.get("/result", response_model=ExamResult)
async def get_result(
    candidate: Candidate = Depends(get_current_candidate),
    db: AsyncSession = Depends(get_db),
) -> ExamResult:
    """Final result for the candidate — only available after submit/timeout.
    Score is computed server-side at scoring time; this endpoint only reads."""
    # Unlike the in-exam endpoints, the result must stay readable after the
    # sitting is closed (candidates force-submitted by "Đóng buổi" reload this
    # screen when no sitting is active anymore) — fall back to the candidate's
    # most recent session instead of requiring an active sitting.
    try:
        session = await _current_session(db, candidate)
    except HTTPException:
        session = await db.scalar(
            select(ExamSession)
            .where(ExamSession.candidate_id == candidate.id)
            .order_by(ExamSession.created_at.desc())
            .limit(1)
        )
        if session is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Chưa có phiên thi. Hãy xác nhận thông tin.")
    if session.status not in {SessionStatus.SUBMITTED.value, SessionStatus.TIMEOUT.value}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chưa có kết quả — bạn chưa nộp bài.")
    answered = len(list(await db.scalars(
        select(Answer).where(Answer.session_id == session.id, Answer.selected_option.is_not(None))
    )))
    total = len(session.question_order or [])
    return ExamResult(
        status=session.status, submitted_at=session.submitted_at,
        total=total, answered=answered,
        total_correct=session.total_correct or 0,
    )
