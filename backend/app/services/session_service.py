"""Exam session helpers: Redis payload access, deterministic shuffle, scoring,
event logging, and startup reconciliation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Answer, Exam, ExamEvent, ExamSession, Sitting
from app.models.enums import EventType, ExamStatus, SessionStatus, SittingStatus
from app.services import exam_assets, exam_package

logger = logging.getLogger("exam.session")


def payload_key(sitting_id) -> str:
    """Redis key holding a sitting's decrypted đề payload (AD-47)."""
    return f"sitting:{sitting_id}:payload"


def kiosk_quit_key(exam_id) -> str:
    """Redis flag asking all kiosk machines of this exam to quit (AD-66).
    Short TTL so a machine booted after the window is not closed unexpectedly."""
    return f"kiosk_quit:{exam_id}"


def kiosk_wipe_key(exam_id) -> str:
    """Redis flag yêu cầu mọi máy kiosk của kỳ thi này XOÁ đề + đáp án local
    (HTTP cache + storage) rồi về đăng nhập (SP-4). Set khi đóng buổi, xoá khi
    mở buổi. Khác `kiosk_quit_key` (thoát hẳn máy)."""
    return f"kiosk_wipe:{exam_id}"


def report_cache_key(sitting_id) -> str:
    """Redis key for a sitting's lazily-built answer-key cache (reports)."""
    return f"sitting:{sitting_id}:report"


def preload_key(session_id) -> str:
    """Cờ 'máy đã tải xong toàn bộ ảnh đề' của một phiên (AD-110). Máy thí sinh
    báo về khi tải đủ lúc CHỜ bắt đầu; bảng giám sát đếm để chủ tịch chỉ bấm
    'Bắt đầu thi' khi mọi máy đã sẵn đề (hết cảnh khúc đầu buổi thi ì vì tải nền)."""
    return f"preload_done:{session_id}"


async def get_sitting_payload(redis, sitting_id) -> dict | None:
    """Load and parse a sitting's decrypted đề payload from Redis (None if absent)."""
    raw = await redis.get(payload_key(sitting_id))
    if raw is None:
        return None
    return json.loads(raw)


def _payload_ttl(sitting: Sitting) -> int:
    return sitting.duration_minutes * 60 + 1800


def _rebuild_payload_sync(sitting_id, blob: bytes) -> dict:
    """Giải mã + materialize ảnh — CPU-bound, PHẢI chạy trong thread (to_thread)."""
    file_obj = exam_package.parse_exam_file(blob)
    payload = exam_package.decrypt_exam_file(file_obj, storage_key())
    return exam_assets.materialize_payload_images(sitting_id, payload)


async def ensure_sitting_payload(db: AsyncSession, redis, sitting: Sitting) -> dict | None:
    """Return the sitting's live đề payload, self-healing if Redis lost it.

    Redis payload có TTL (đặt lúc mở buổi = duration·60+1800). Nếu buổi mở sớm rồi
    lâu sau mới "Bắt đầu thi" (hoặc cộng giờ / thí sinh vào trễ), đồng hồ thi có thể
    chạy QUÁ mốc TTL → payload biến mất giữa buổi. Khi Redis trống ta giải mã lại từ
    ``encrypted_payload`` (bền tại DB tới khi đóng buổi), materialize ảnh tĩnh, nạp
    lại Redis. Trả None nếu đề đã bị purge (đóng buổi).

    Chống thundering-herd (AD-75): N request /questions cùng lúc phát hiện Redis
    trống sẽ KHÔNG cùng giải mã (PBKDF2 600k + blob trăm MB, từng nghẽn event loop
    13-07) — chỉ 1 request giữ khoá Redis dựng lại (trong thread), số còn lại chờ
    rồi đọc kết quả. Đọc trúng payload cũng GIA HẠN TTL trượt để không bao giờ hết
    hạn giữa lúc còn người thi."""
    payload = await get_sitting_payload(redis, sitting.id)
    if payload is not None:
        try:
            await redis.expire(payload_key(sitting.id), _payload_ttl(sitting))
        except Exception:  # noqa: BLE001 — gia hạn hụt không được chặn request
            pass
        return payload

    lock_key = f"lock:payload_rebuild:{sitting.id}"
    got_lock = await redis.set(lock_key, "1", nx=True, ex=120)
    if not got_lock:
        # Người khác đang dựng — chờ tối đa ~20s rồi đọc lại.
        for _ in range(40):
            await asyncio.sleep(0.5)
            payload = await get_sitting_payload(redis, sitting.id)
            if payload is not None:
                return payload
            if not await redis.exists(lock_key):
                break  # người dựng xong (hoặc lỗi) — thử tự dựng bên dưới
        got_lock = await redis.set(lock_key, "1", nx=True, ex=120)
        if not got_lock:
            return await get_sitting_payload(redis, sitting.id)

    try:
        # Double-check sau khi có khoá: có thể vừa được dựng xong.
        payload = await get_sitting_payload(redis, sitting.id)
        if payload is not None:
            return payload
        blob = await sitting_payload_blob(db, sitting.id)
        if not blob:
            return None
        try:
            payload = await asyncio.to_thread(_rebuild_payload_sync, sitting.id, blob)
        except Exception as exc:  # noqa: BLE001 — bad/foreign blob, đừng làm sập request
            logger.error("ensure_sitting_payload: không giải mã được đề buổi %s: %s",
                         sitting.id, exc)
            return None
        await redis.set(payload_key(sitting.id),
                        json.dumps(payload, ensure_ascii=False), ex=_payload_ttl(sitting))
        logger.info("Tự nạp lại Redis payload cho buổi %s (TTL hết giữa buổi)", sitting.id)
        return payload
    finally:
        try:
            await redis.delete(lock_key)
        except Exception:  # noqa: BLE001
            pass


_ACTIVE_EXAMS_CACHE_KEY = "cache:active_exams"
_ACTIVE_EXAMS_TTL = 5   # giây — đổi trạng thái kỳ thi phản ánh chậm tối đa ngần này


async def cached_active_exams(db: AsyncSession, redis) -> list[dict]:
    """Danh sách kỳ thi đang ACTIVE, cache Redis ~5s (AD-69). Endpoint poll cực
    nhiều (/kiosk/command từ MỌI máy + /status từ máy chưa đăng nhập, mỗi 5s) trước
    đây đều chạy `SELECT exams WHERE active` xuống DB mỗi lần → query áp đảo gây treo
    pool khi đông. Kết quả giống nhau cho mọi máy & đổi rất hiếm nên cache an toàn.
    Lỗi Redis → tự lùi về truy vấn DB (không bao giờ chặn). Trả [{id,name,
    allow_registration}]."""
    try:
        raw = await redis.get(_ACTIVE_EXAMS_CACHE_KEY)
        if raw is not None:
            return json.loads(raw)
    except Exception:  # noqa: BLE001 — Redis trục trặc thì đọc DB
        pass
    rows = list(await db.scalars(
        select(Exam).where(Exam.status == ExamStatus.ACTIVE.value).order_by(Exam.name)
    ))
    data = [
        {"id": str(e.id), "name": e.name, "allow_registration": bool(e.allow_registration)}
        for e in rows
    ]
    try:
        await redis.set(_ACTIVE_EXAMS_CACHE_KEY, json.dumps(data, ensure_ascii=False),
                        ex=_ACTIVE_EXAMS_TTL)
    except Exception:  # noqa: BLE001
        pass
    return data


async def cached_active_sitting_id(db: AsyncSession, redis, exam_id) -> str | None:
    """ID buổi đang ACTIVE của kỳ thi, cache Redis ~3s (AD-69). Dùng cho ĐƯỜNG ĐỌC
    nóng `/state` — endpoint mọi thí sinh poll /5s, trước đây chạy `SELECT
    exam_sittings WHERE exam_id+active` xuống DB MỖI lần → query áp đảo ngốn CPU
    Postgres khi đông. Chỉ trả id (đủ cho /state tìm phiên). Các đường điều khiển
    (login/answer/đóng buổi) vẫn dùng get_active_sitting (DB, không cache) cho an
    toàn. Stale tối đa ~3s khi mở/đóng buổi — chấp nhận được. Lỗi Redis → đọc DB."""
    key = f"cache:active_sitting:{exam_id}"
    try:
        raw = await redis.get(key)
        if raw is not None:
            return raw or None   # "" = không có buổi active
    except Exception:  # noqa: BLE001
        pass
    sitting = await get_active_sitting(db, exam_id)
    sid = str(sitting.id) if sitting else ""
    try:
        await redis.set(key, sid, ex=3)
    except Exception:  # noqa: BLE001
        pass
    return sid or None


async def sitting_has_payload(db: AsyncSession, sitting_id) -> bool:
    """Đề đã nạp chưa — check IS NOT NULL, KHÔNG kéo blob (cột deferred)."""
    return bool(await db.scalar(
        select(Sitting.encrypted_payload.isnot(None)).where(Sitting.id == sitting_id)
    ))


async def sitting_payload_blob(db: AsyncSession, sitting_id) -> bytes | None:
    """Đọc blob đề mã hoá bằng SELECT tường minh (cột deferred trên model)."""
    return await db.scalar(
        select(Sitting.encrypted_payload).where(Sitting.id == sitting_id)
    )


async def get_active_sitting(db: AsyncSession, exam_id) -> Sitting | None:
    """The one ``active`` sitting (buổi đang mở) of an exam, if any (AD-47)."""
    return await db.scalar(
        select(Sitting).where(
            Sitting.exam_id == exam_id,
            Sitting.status == SittingStatus.ACTIVE.value,
        ).limit(1)
    )


def time_remaining(session: ExamSession) -> int | None:
    """Seconds left for an in_progress session, frozen at ``paused_at`` while the
    candidate is paused (AD-47). None when the clock isn't running."""
    if session.status != SessionStatus.IN_PROGRESS.value or not session.end_time:
        return None
    anchor = session.paused_at or datetime.now(timezone.utc)
    return max(0, int((session.end_time - anchor).total_seconds()))


def deterministic_shuffle(seed: str, items: list) -> list:
    rng = random.Random(seed)
    out = list(items)
    rng.shuffle(out)
    return out


def shuffle_keeping_fixed(seed: str, items: list, fixed_flags: list[bool]) -> list:
    """Deterministically shuffle ``items`` while honouring QTI ``fixed="true"``:
    any element whose ``fixed_flags`` entry is True stays at its original index;
    only the movable elements are permuted among the movable slots.

    ``fixed_flags`` must be the same length as ``items`` (a shorter/empty list is
    treated as all-movable for robustness against legacy payloads)."""
    if len(fixed_flags) != len(items):
        fixed_flags = [False] * len(items)
    movable_slots = [i for i, f in enumerate(fixed_flags) if not f]
    shuffled = deterministic_shuffle(seed, [items[i] for i in movable_slots])
    out = list(items)
    for slot, val in zip(movable_slots, shuffled):
        out[slot] = val
    return out


def build_orders(session_id: str, payload: dict, shuffle_q: bool, shuffle_o: bool):
    """Compute (question_order, option_order) for a session, seeded by its id.

    Honours QTI ``fixed="true"`` on both questions (qti-assessment-item-ref) and
    options (qti-simple-choice): a fixed element keeps its original position even
    when its shuffle flag is on."""
    questions = sorted(payload["questions"], key=lambda q: q["order_index"])
    qids = [q["id"] for q in questions]
    if shuffle_q:
        q_fixed = [bool(q.get("fixed")) for q in questions]
        question_order = shuffle_keeping_fixed(session_id, qids, q_fixed)
    else:
        question_order = qids

    base_opts = ["A", "B", "C", "D"]
    option_order: dict[str, list[str]] = {}
    for q in questions:
        opts = q.get("options", [])
        present = [o["id"] for o in opts] or base_opts
        if shuffle_o:
            o_fixed = [bool(o.get("fixed")) for o in opts]
            option_order[q["id"]] = shuffle_keeping_fixed(session_id + q["id"], present, o_fixed)
        else:
            option_order[q["id"]] = present
    return question_order, option_order


def make_event(*, event_type, cccd=None, ip=None, session_id=None, metadata=None) -> ExamEvent:
    # AD-75: cột cccd_attempted là String(12); input SAI ĐỊNH DẠNG 13-20 ký tự
    # (dán thừa số) từng nổ varchar overflow → thí sinh nhận 500 thay vì 400.
    return ExamEvent(
        session_id=session_id,
        cccd_attempted=(cccd or None) and str(cccd)[:12],
        client_ip=ip,
        event_type=event_type,
        event_metadata=metadata,
    )


async def log_event_commit(db: AsyncSession, **kwargs) -> None:
    """Persist a single event immediately (used on failed-login paths)."""
    db.add(make_event(**kwargs))
    await db.commit()


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


def storage_key() -> str:
    """Server-side key used to encrypt the QTI payload at rest. Derived from
    JWT_SECRET so it's unique per deployment and never exposed to admins."""
    return "qti-storage:" + settings.jwt_secret


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
