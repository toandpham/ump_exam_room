"""Guard của auto-update (AD-87): chỉ cho tự cập nhật khi CHẮC CHẮN không đụng kỳ thi.

Auto-update build lại image + chạy migration, KHÔNG có ai đứng đó cứu → guard sai
một lần là sập cả phòng thi. Mỗi lớp chặn đều phải có test.

``update_safety`` đếm TOÀN CỤC (đúng bản chất: "cả máy chủ này có kỳ thi nào không?"),
nên test phải khởi đầu từ trạng thái sạch — DB dev dùng chung hay còn phiên rác của
các lần chạy trước.
"""
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update

from app.database import AsyncSessionLocal
from app.maintenance import BLACKOUT_DAYS, LIVE_SESSION_STATUSES, update_safety
from app.models import Answer, Exam, ExamSession, Sitting
from app.models.enums import ExamStatus, SessionStatus, SittingStatus

pytestmark = pytest.mark.asyncio

TODAY = date(2026, 8, 20)   # "hôm nay" giả định, xa dữ liệu test khác
FAR = date(2026, 12, 31)    # ngoài vùng cấm


def _exam(admin_id, name, status, exam_date):
    return Exam(name=name, status=status, exam_date=exam_date,
                duration_minutes=45, created_by=admin_id)


@pytest_asyncio.fixture(autouse=True)
async def _clear_stale_blockers():
    """Đưa guard về trạng thái sạch TRƯỚC mỗi test.

    DB dev dùng chung: vừa có phiên rác của lần chạy trước, vừa có dữ liệu do chính
    các test trong file này tạo ra (mỗi test tạo kỳ thi/buổi rồi để lại). Dọn cả hai:
    phiên còn sống, buổi đang mở, và mọi kỳ thi/buổi rơi vào cửa sổ ngày quanh TODAY.
    """
    lo = TODAY - timedelta(days=BLACKOUT_DAYS)
    hi = TODAY + timedelta(days=BLACKOUT_DAYS)
    async with AsyncSessionLocal() as db:
        live = (await db.scalars(
            select(ExamSession.id).where(ExamSession.status.in_(LIVE_SESSION_STATUSES))
        )).all()
        if live:
            await db.execute(delete(Answer).where(Answer.session_id.in_(live)))
            await db.execute(delete(ExamSession).where(ExamSession.id.in_(live)))
        await db.execute(update(Sitting)
                         .where(Sitting.status == SittingStatus.ACTIVE.value)
                         .values(status=SittingStatus.CLOSED.value))
        await db.execute(update(Exam)
                         .where(Exam.status == ExamStatus.ACTIVE.value,
                                Exam.exam_date.between(lo, hi))
                         .values(status=ExamStatus.CLOSED.value))
        await db.execute(update(Sitting)
                         .where(Sitting.status != SittingStatus.CLOSED.value,
                                Sitting.scheduled_date.between(lo, hi))
                         .values(status=SittingStatus.CLOSED.value))
        await db.commit()
    yield


async def test_safe_when_nothing_scheduled(factory):
    """Không phiên sống, không buổi mở, không lịch thi gần → cho update."""
    async with AsyncSessionLocal() as db:
        safe, reason = await update_safety(db, today=TODAY)
    assert safe is True, reason


async def test_blocked_by_live_session(factory):
    """Thí sinh mới đăng nhập (sẵn sàng) — CHƯA thi — vẫn phải chặn.

    Ca nguy hiểm nhất: 7h50 sáng ngày thi, in_progress = 0 nhưng người đã vào.
    """
    admin, _ = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=admin.id)
    cand = await factory.candidate(exam.id)
    async with AsyncSessionLocal() as db:
        db.add(ExamSession(candidate_id=cand.id, exam_id=exam.id, sitting_id=sitting.id,
                           status=SessionStatus.READY.value))
        await db.commit()
    async with AsyncSessionLocal() as db:
        safe, reason = await update_safety(db, today=TODAY)
    assert safe is False
    assert "phiên thi" in reason


async def test_blocked_by_open_sitting(factory):
    """Buổi thi đang mở (đề đã nạp, chờ bắt đầu) → chặn."""
    admin, _ = await factory.admin()
    await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=admin.id)
    async with AsyncSessionLocal() as db:
        safe, reason = await update_safety(db, today=TODAY)
    assert safe is False
    assert "buổi thi đang mở" in reason


async def test_blocked_by_exam_date_within_window(factory):
    """Kỳ thi mở có ngày thi hôm nay/ngày mai → chặn (dù chưa ai đăng nhập)."""
    admin, _ = await factory.admin()
    async with AsyncSessionLocal() as db:
        db.add(_exam(admin.id, "Kỳ thi sắp tới", ExamStatus.ACTIVE.value,
                     TODAY + timedelta(days=BLACKOUT_DAYS)))
        await db.commit()
    async with AsyncSessionLocal() as db:
        safe, reason = await update_safety(db, today=TODAY)
    assert safe is False
    assert "ngày thi" in reason


async def test_blocked_by_scheduled_sitting_within_window(factory):
    """Buổi thi (chưa đóng) hẹn ngày mai → chặn."""
    admin, _ = await factory.admin()
    async with AsyncSessionLocal() as db:
        exam = _exam(admin.id, "Kỳ thi X", ExamStatus.ACTIVE.value, FAR)
        db.add(exam)
        await db.flush()
        db.add(Sitting(exam_id=exam.id, name="Buổi 1", status=SittingStatus.DRAFT.value,
                       scheduled_date=TODAY + timedelta(days=1), duration_minutes=45))
        await db.commit()
    async with AsyncSessionLocal() as db:
        safe, reason = await update_safety(db, today=TODAY)
    assert safe is False
    assert "hẹn trong vòng" in reason


async def test_allowed_when_exam_far_away(factory):
    """Kỳ thi còn xa (ngoài vùng cấm) → vẫn cho update."""
    admin, _ = await factory.admin()
    async with AsyncSessionLocal() as db:
        exam = _exam(admin.id, "Kỳ thi xa", ExamStatus.ACTIVE.value, FAR)
        db.add(exam)
        await db.flush()
        db.add(Sitting(exam_id=exam.id, name="Buổi xa", status=SittingStatus.DRAFT.value,
                       scheduled_date=FAR, duration_minutes=45))
        await db.commit()
    async with AsyncSessionLocal() as db:
        safe, reason = await update_safety(db, today=TODAY)
    assert safe is True, reason


async def test_closed_exam_does_not_block(factory):
    """Kỳ thi đã đóng, dù ngày thi là hôm nay, không được chặn update."""
    admin, _ = await factory.admin()
    async with AsyncSessionLocal() as db:
        db.add(_exam(admin.id, "Kỳ thi đã xong", ExamStatus.CLOSED.value, TODAY))
        await db.commit()
    async with AsyncSessionLocal() as db:
        safe, reason = await update_safety(db, today=TODAY)
    assert safe is True, reason
