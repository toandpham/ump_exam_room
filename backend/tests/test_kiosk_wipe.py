"""SP-4: đóng buổi → cờ kiosk wipe bật; mở buổi → cờ tắt; command trả wipe."""

import pytest

from app.core.redis import redis_client
from app.models.enums import AdminRole
from app.services import session_service
from tests.conftest import auth, qenc, qenc_code
from tests.test_qti_import import _build_qti_zip

pytestmark = pytest.mark.asyncio


async def test_end_sitting_sets_wipe_then_open_clears(client, factory):
    admin, ptok = await factory.admin(role=AdminRole.PROCTOR.value)
    # active_exam(questions, duration=45, owner_id) → (exam, sitting, payload)
    exam, sitting, _payload = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}], owner_id=admin.id)
    wipe_key = session_service.kiosk_wipe_key(exam.id)

    # Chưa đóng buổi → chưa có cờ → command wipe=false.
    assert await redis_client.get(wipe_key) is None
    cmd = (await client.get("/api/exam/kiosk/command")).json()
    assert cmd["wipe"] is False and "quit" in cmd

    # Đóng buổi → cờ wipe bật → command wipe=true.
    assert (await client.post(f"/api/admin/sittings/{sitting.id}/end", headers=auth(ptok))).status_code == 200
    assert await redis_client.get(wipe_key) is not None
    cmd = (await client.get("/api/exam/kiosk/command")).json()
    assert cmd["wipe"] is True


async def test_open_sitting_clears_wipe_flag(client, factory):
    admin, ptok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting = await factory.empty_active_exam(admin.id)
    # Giả lập cờ wipe còn sót từ buổi trước.
    await redis_client.set(session_service.kiosk_wipe_key(exam.id), "1", ex=300)
    # Nạp đề + mở buổi → cờ wipe phải bị xoá (đề mới không được wipe ngay).
    await client.post(f"/api/admin/sittings/{sitting.id}/import-qti",
                      files={"file": ("e.qenc", qenc(_build_qti_zip()), "application/octet-stream")},
                      data={"code": qenc_code()}, headers=auth(ptok))
    assert (await client.post(f"/api/admin/sittings/{sitting.id}/open", headers=auth(ptok))).status_code == 200
    assert await redis_client.get(session_service.kiosk_wipe_key(exam.id)) is None
