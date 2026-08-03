"""Thoát máy thi: gửi được BẤT KỲ LÚC NÀO (AD-128, đảo chốt chặn của AD-92).

AD-92 từng chặn cứng 409 khi còn người đang làm bài, vì lúc đó kiosk nhận lệnh sẽ
RESTART Windows — bấm nhầm là reboot cả phòng. Hai điều đã đổi kể từ đó:

* kiosk v1.3.0+ (AD-93) chỉ ĐÓNG phần mềm thi về desktop, không reboot nữa;
* yêu cầu vận hành 02-08: phải thoát được ngay cả giữa buổi (máy treo, dọn phòng
  gấp), chờ nộp xong mới thoát được là không dùng được.

Nên an toàn chuyển từ chặn ở máy chủ sang **hộp xác nhận ở giao diện** + ghi
``exam_events`` mỗi lần bấm (trang Nhật ký tra được ai bấm lúc nào).
"""

import pytest

from app.core.redis import redis_client
from app.models import ExamSession
from app.models.enums import AdminRole, SessionStatus
from app.services import session_service
from tests.conftest import auth

pytestmark = pytest.mark.asyncio

QUESTIONS = [{"text": "1+1?", "correct": "A", "options": ["A", "B", "C", "D"]}]


async def _session(db, factory, exam, sitting, status):
    cand = await factory.candidate(exam.id)
    db.add(ExamSession(candidate_id=cand.id, sitting_id=sitting.id,
                       exam_id=exam.id, status=status))
    await db.commit()


async def _quit(client, token, exam, suffix=""):
    r = await client.post(f"/api/admin/exams/{exam.id}/kiosk-quit{suffix}",
                          headers=auth(token))
    return r


async def test_gui_duoc_ngay_ca_khi_con_thi_sinh_dang_lam_bai(client, db, factory):
    admin, token = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    await _session(db, factory, exam, sitting, SessionStatus.IN_PROGRESS.value)

    assert (await _quit(client, token, exam)).status_code == 200
    assert await redis_client.exists(session_service.kiosk_quit_key(exam.id))
    await redis_client.delete(session_service.kiosk_quit_key(exam.id))


async def test_gui_duoc_khi_ca_phong_da_nop(client, db, factory):
    admin, token = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    await _session(db, factory, exam, sitting, SessionStatus.SUBMITTED.value)

    assert (await _quit(client, token, exam)).status_code == 200
    assert await redis_client.exists(session_service.kiosk_quit_key(exam.id))
    await redis_client.delete(session_service.kiosk_quit_key(exam.id))


async def test_force_cu_van_khong_gay_loi(client, db, factory):
    """Giao diện bản cũ còn gửi ``?force=true`` — không được vỡ sau khi bỏ chốt chặn."""
    admin, token = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    await _session(db, factory, exam, sitting, SessionStatus.IN_PROGRESS.value)

    assert (await _quit(client, token, exam, "?force=true")).status_code == 200
    await redis_client.delete(session_service.kiosk_quit_key(exam.id))


async def test_van_chan_nguoi_khong_so_huu_ky_thi(client, db, factory):
    """Bỏ chặn theo TRẠNG THÁI, nhưng cổng SỞ HỮU (AD-30) phải còn nguyên — chủ tịch
    khác không được đóng máy kỳ thi không phải của mình."""
    owner, _ = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=owner.id)
    await _session(db, factory, exam, sitting, SessionStatus.SUBMITTED.value)
    _, other_token = await factory.admin(role=AdminRole.PROCTOR.value)

    assert (await _quit(client, other_token, exam)).status_code == 404
    assert not await redis_client.exists(session_service.kiosk_quit_key(exam.id))
