"""Server-driven kiosk quit (AD-66): chủ tịch bấm 'Thoát tất cả máy thi' → Redis
flag → kiosk polls GET /api/exam/kiosk/command và tự đóng."""
import pytest

from app.models.enums import AdminRole
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


async def test_kiosk_quit_sets_flag_and_command_reflects(client, factory):
    admin, tok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, _sitting, _payload = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}], owner_id=admin.id)

    # Trước khi bấm: kiosk command = no quit
    cmd = await client.get("/api/exam/kiosk/command")
    assert cmd.status_code == 200
    assert cmd.json() == {"quit": False, "wipe": False}

    # Chủ tịch bấm thoát
    r = await client.post(f"/api/admin/exams/{exam.id}/kiosk-quit", headers=auth(tok))
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["ttl"] == 60

    # Kiosk thấy lệnh quit
    cmd2 = await client.get("/api/exam/kiosk/command")
    assert cmd2.json() == {"quit": True, "wipe": False}


async def test_kiosk_quit_ownership_gated(client, factory):
    owner, _ = await factory.admin(role=AdminRole.PROCTOR.value)
    other, otok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, _s, _p = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}], owner_id=owner.id)
    # Proctor khác (không sở hữu) → 404 (giấu sự tồn tại, AD-30)
    r = await client.post(f"/api/admin/exams/{exam.id}/kiosk-quit", headers=auth(otok))
    assert r.status_code == 404
