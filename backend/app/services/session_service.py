"""Exam session helpers — FACADE.

Refactor đợt 3 tách phần thân ra 3 module con, file này GIỮ NGUYÊN đường import
cũ (``from app.services import session_service``) nên mọi call site + test không
phải đổi:

  - ``session_payload.py`` — khoá Redis, nạp/giải mã payload đề, cache kỳ thi/buổi mở
  - ``scoring.py``          — hash niêm phong kết quả, chấm điểm, bảng đáp án đúng
  - ``session_jobs.py``     — tác vụ nền: tự nộp quá giờ, reconcile lúc khởi động

Phần còn lại ở đây là những helper nhỏ dùng khắp nơi: đồng hồ, xáo trộn
deterministic, ghi sự kiện."""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from app.models import ExamSession
from app.models.enums import EventType, SessionStatus  # noqa: F401 — re-export cho call site cũ

# --- re-export: giữ nguyên API công khai của session_service ------------------
from .session_payload import (  # noqa: F401
    cached_active_exams,
    cached_active_sitting_id,
    ensure_sitting_payload,
    get_active_sitting,
    get_sitting_payload,
    kiosk_quit_key,
    kiosk_wipe_key,
    payload_key,
    preload_key,
    report_cache_key,
    sitting_has_payload,
    sitting_payload_blob,
    storage_key,
)
# Hằng nội bộ nhưng test/conftest dọn cache dùng tới → re-export luôn.
from .session_payload import _ACTIVE_EXAMS_CACHE_KEY  # noqa: F401
from .scoring import (  # noqa: F401
    SCORE_BATCH,
    batched,
    compute_results_hash,
    correct_map_for_sitting,
    correct_map_from_payload,
    score_session,
    verify_results_hash,
)
from .session_jobs import (  # noqa: F401
    auto_submit_expired,
    reconcile_active_sittings,
)
from .events import log_event_commit, make_event  # noqa: F401

logger = logging.getLogger("exam.session")


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
