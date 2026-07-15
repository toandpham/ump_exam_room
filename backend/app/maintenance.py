"""Kiểm tra AN TOÀN trước khi TỰ ĐỘNG cập nhật server (AD-87).

Auto-update phải build lại image (5–10 phút, ngốn CPU/RAM) + chạy migration DB —
làm nhầm lúc là **sập cả phòng thi**, mà lại không có ai đứng đó để cứu. Nên nó chỉ
được phép chạy khi CHẮC CHẮN không đụng tới kỳ thi nào.

"Không có ai đang thi" là điều kiện QUÁ YẾU: 7h50 sáng ngày thi, thí sinh đang lục
tục đăng nhập thì số phiên `in_progress` vẫn = 0. Nên chặn theo 4 lớp:

  1. Không phiên nào còn sống (chờ / sẵn sàng / đang làm) — có người đã đăng nhập.
  2. Không buổi thi nào đang mở.
  3. Không kỳ thi nào đang mở có ngày thi trong khoảng ±1 ngày.
  4. Không buổi thi nào (chưa đóng) hẹn trong khoảng ±1 ngày.

Khung giờ đêm do scripts/auto-update.sh lo (ở đây chỉ xét dữ liệu).
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Exam, ExamSession, Sitting
from app.models.enums import ExamStatus, SessionStatus, SittingStatus

# Không tự cập nhật nếu có kỳ thi/buổi thi trong khoảng bấy nhiêu ngày quanh hôm nay.
BLACKOUT_DAYS = 1

# Phiên "còn sống" = đã có người đăng nhập và chưa xong.
LIVE_SESSION_STATUSES = (
    SessionStatus.WAITING.value,
    SessionStatus.READY.value,
    SessionStatus.IN_PROGRESS.value,
)


async def update_safety(db: AsyncSession, today: date | None = None) -> tuple[bool, str]:
    """(an_toàn, lý_do). Chỉ trả True khi KHÔNG có dấu hiệu nào của kỳ thi đang/sắp diễn ra."""
    today = today or date.today()
    lo, hi = today - timedelta(days=BLACKOUT_DAYS), today + timedelta(days=BLACKOUT_DAYS)

    n = await db.scalar(
        select(func.count()).select_from(ExamSession)
        .where(ExamSession.status.in_(LIVE_SESSION_STATUSES))
    )
    if n:
        return False, f"có {n} thí sinh đang trong phiên thi (đã đăng nhập)"

    n = await db.scalar(
        select(func.count()).select_from(Sitting)
        .where(Sitting.status == SittingStatus.ACTIVE.value)
    )
    if n:
        return False, f"có {n} buổi thi đang mở"

    n = await db.scalar(
        select(func.count()).select_from(Exam).where(
            Exam.status == ExamStatus.ACTIVE.value,
            Exam.exam_date.is_not(None),
            Exam.exam_date.between(lo, hi),
        )
    )
    if n:
        return False, f"có {n} kỳ thi có ngày thi trong vòng {BLACKOUT_DAYS} ngày"

    n = await db.scalar(
        select(func.count()).select_from(Sitting).where(
            Sitting.status != SittingStatus.CLOSED.value,
            Sitting.scheduled_date.is_not(None),
            Sitting.scheduled_date.between(lo, hi),
        )
    )
    if n:
        return False, f"có {n} buổi thi hẹn trong vòng {BLACKOUT_DAYS} ngày"

    return True, "không có kỳ thi nào đang/sắp diễn ra"
