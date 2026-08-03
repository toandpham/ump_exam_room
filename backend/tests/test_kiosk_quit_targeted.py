"""Thoát kiosk theo TỪNG THÍ SINH và theo PHÒNG (AD-128).

Trước đây chỉ có lệnh cấp cả kỳ thi (AD-66) — giám thị muốn đóng một máy lẻ (thí
sinh đã nộp, đứng dậy về) thì không có cách nào. Nay cờ Redis đặt theo
``device_id`` của máy: kiosk khai máy mình khi hỏi lệnh nên server trả đúng máy đó.

Giới hạn CỐ Ý: máy chưa ai đăng nhập thì hệ thống chưa biết ``device_id`` → không
nhắm được. Đóng cả phòng vẫn còn cho trường hợp đó.
"""

import pytest

from app.api.admin.monitor.control import KIOSK_QUIT_TTL_SECONDS
from app.core.redis import redis_client
from app.services import session_service
from tests.conftest import auth

pytestmark = pytest.mark.asyncio

DEV_A = "device-aaa-111"
DEV_B = "device-bbb-222"


async def _login(client, cand, device):
    """Đăng nhập + xác nhận để phiên ghi lại device_id của máy."""
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                             headers={"X-Device-Id": device})).json()["token"]
    await client.post("/api/exam/auth/confirm",
                      headers={**auth(tok), "X-Device-Id": device})
    return tok


async def test_quit_one_candidate_targets_only_that_machine(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}], owner_id=admin.id)
    c1 = await factory.candidate(exam.id, cccd="011111111111")
    c2 = await factory.candidate(exam.id, cccd="022222222222")
    await _login(client, c1, DEV_A)
    await _login(client, c2, DEV_B)

    sessions = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions",
                                 headers=auth(ptok))).json()
    sid = next(s["session_id"] for s in sessions if s["cccd"] == c1.cccd)

    r = await client.post(f"/api/admin/sessions/{sid}/kiosk-quit", headers=auth(ptok))
    assert r.status_code == 200, r.text

    # Máy của c1 nhận lệnh thoát; máy c2 KHÔNG (nếu sai thì cả phòng bị đóng oan).
    assert (await client.get(f"/api/exam/kiosk/command?device={DEV_A}")).json()["quit"] is True
    assert (await client.get(f"/api/exam/kiosk/command?device={DEV_B}")).json()["quit"] is False
    # Kiosk bản CŨ (không khai máy) cũng không bị ảnh hưởng.
    assert (await client.get("/api/exam/kiosk/command")).json()["quit"] is False


async def test_quit_whole_room_targets_every_machine_in_it(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}], owner_id=admin.id)
    room = await factory.room(exam.id, name="Phòng 1")
    other = await factory.room(exam.id, name="Phòng 2")
    c1 = await factory.candidate(exam.id, cccd="031111111111", room_id=room.id)
    c2 = await factory.candidate(exam.id, cccd="042222222222", room_id=other.id)
    await _login(client, c1, DEV_A)
    await _login(client, c2, DEV_B)

    r = await client.post(f"/api/admin/rooms/{room.id}/kiosk-quit", headers=auth(ptok))
    assert r.status_code == 200, r.text
    assert r.json()["machines"] == 1

    assert (await client.get(f"/api/exam/kiosk/command?device={DEV_A}")).json()["quit"] is True
    assert (await client.get(f"/api/exam/kiosk/command?device={DEV_B}")).json()["quit"] is False


async def test_giam_thi_may_quit_only_machines_in_their_own_room(client, factory, db):
    admin, _ = await factory.admin()
    exam, sitting, _ = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}], owner_id=admin.id)
    gt, gtok = await factory.admin(role="room_proctor")
    mine = await factory.room(exam.id, proctor_id=gt.id, name="Phòng mình")
    theirs = await factory.room(exam.id, name="Phòng khác")

    c1 = await factory.candidate(exam.id, cccd="051111111111", room_id=mine.id)
    c2 = await factory.candidate(exam.id, cccd="062222222222", room_id=theirs.id)
    await _login(client, c1, DEV_A)
    await _login(client, c2, DEV_B)

    assert (await client.post(f"/api/admin/rooms/{mine.id}/kiosk-quit",
                              headers=auth(gtok))).status_code == 200
    # Phòng của người khác → 404 (giấu sự tồn tại), KHÔNG được đóng máy phòng đó.
    assert (await client.post(f"/api/admin/rooms/{theirs.id}/kiosk-quit",
                              headers=auth(gtok))).status_code == 404
    assert (await client.get(f"/api/exam/kiosk/command?device={DEV_B}")).json()["quit"] is False


async def test_quit_is_allowed_while_candidates_are_still_working(client, factory, db):
    """Theo yêu cầu vận hành 02-08: thoát được BẤT KỲ LÚC NÀO (chốt chặn 409 của
    AD-92 gỡ bỏ) — an toàn giờ nằm ở hộp xác nhận phía giao diện."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}], owner_id=admin.id)
    cand = await factory.candidate(exam.id)
    await _login(client, cand, DEV_A)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))

    r = await client.post(f"/api/admin/exams/{exam.id}/kiosk-quit", headers=auth(ptok))
    assert r.status_code == 200, r.text
    assert await redis_client.get(session_service.kiosk_quit_key(exam.id)) is not None


async def test_device_flag_expires_so_a_later_boot_is_not_closed(client, factory, db):
    """Cờ phải có hạn ngắn: máy bật lại sau đó KHÔNG được tự đóng."""
    admin, ptok = await factory.admin()
    exam, _, _ = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}], owner_id=admin.id)
    del ptok
    cand = await factory.candidate(exam.id)
    await _login(client, cand, DEV_A)

    key = session_service.kiosk_quit_device_key(DEV_A)
    await redis_client.set(key, "1", ex=KIOSK_QUIT_TTL_SECONDS)
    ttl = await redis_client.ttl(key)
    assert 0 < ttl <= KIOSK_QUIT_TTL_SECONDS
