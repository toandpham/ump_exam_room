"""AD-92: 'Khởi động lại máy thi' không được bắn khi còn người đang làm bài.

Lệnh này làm máy thi RESTART Windows (AD-77c). Bấm nhầm lúc đang thi = reboot cả
phòng đang làm bài, nên máy chủ chặn cứng; muốn vẫn gửi thì phải ``force=true``.
"""

import pytest

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


async def test_chan_khi_con_thi_sinh_dang_lam_bai(client, db, factory):
    admin, token = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    await _session(db, factory, exam, sitting, SessionStatus.IN_PROGRESS.value)

    r = await client.post(f"/api/admin/exams/{exam.id}/kiosk-quit", headers=auth(token))
    assert r.status_code == 409
    assert "ĐANG LÀM BÀI" in r.json()["detail"]
    # Không có cờ nào được đặt → máy thi không reboot.
    from app.core.redis import redis_client
    assert not await redis_client.exists(session_service.kiosk_quit_key(exam.id))


async def test_cho_phep_khi_ca_phong_da_nop(client, db, factory):
    admin, token = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    await _session(db, factory, exam, sitting, SessionStatus.SUBMITTED.value)

    r = await client.post(f"/api/admin/exams/{exam.id}/kiosk-quit", headers=auth(token))
    assert r.status_code == 200
    from app.core.redis import redis_client
    assert await redis_client.exists(session_service.kiosk_quit_key(exam.id))
    await redis_client.delete(session_service.kiosk_quit_key(exam.id))


async def test_force_van_gui_duoc_khi_can(client, db, factory):
    admin, token = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    await _session(db, factory, exam, sitting, SessionStatus.IN_PROGRESS.value)

    r = await client.post(f"/api/admin/exams/{exam.id}/kiosk-quit?force=true", headers=auth(token))
    assert r.status_code == 200
    from app.core.redis import redis_client
    await redis_client.delete(session_service.kiosk_quit_key(exam.id))
