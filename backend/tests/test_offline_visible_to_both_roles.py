"""Chủ tịch và giám thị phải thấy CÙNG cờ mất kết nối (AD-128).

Thực địa 03-08 báo "giám thị thấy mà chủ tịch không thấy". Test này chốt phía máy
chủ: cùng một thí sinh im lặng quá ngưỡng thì ``offline`` phải bật cho CẢ HAI vai —
chủ tịch chỉ khác ở chỗ thấy thêm thí sinh phòng khác, không được thiếu ai.
"""

import json

import pytest

from app.core import device_lock
from app.core.redis import redis_client
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


async def _go_silent(candidate_id, seconds):
    """Giả lập máy im lặng: đẩy nhịp tim lùi về quá khứ."""
    key = f"cand_active:{candidate_id}"
    raw = await redis_client.get(key)
    beat = json.loads(raw) if raw else {"jti": "x", "ip": "1.1.1.1"}
    import time
    beat["ts"] = time.time() - seconds
    await redis_client.set(key, json.dumps(beat), ex=3600)


async def test_chu_tich_va_giam_thi_cung_thay_co_mat_ket_noi(client, factory, db):
    chair, ctok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}], owner_id=chair.id)
    gt, gtok = await factory.admin(role="room_proctor")
    room = await factory.room(exam.id, proctor_id=gt.id, name="Phòng A")
    cand = await factory.candidate(exam.id, room_id=room.id)

    tok = (await client.post("/api/exam/auth/login",
                             json={"cccd": cand.cccd},
                             headers={"X-Device-Id": "dev-1"})).json()["token"]
    await client.post("/api/exam/auth/confirm",
                      headers={**auth(tok), "X-Device-Id": "dev-1"})

    await _go_silent(cand.id, device_lock.OFFLINE_ALERT_SECONDS + 30)

    url = f"/api/admin/sittings/{sitting.id}/sessions"
    as_chair = (await client.get(url, headers=auth(ctok))).json()
    as_gt = (await client.get(url, headers=auth(gtok))).json()

    mine_chair = next(s for s in as_chair if s["cccd"] == cand.cccd)
    mine_gt = next(s for s in as_gt if s["cccd"] == cand.cccd)
    assert mine_gt["offline"] is True, mine_gt
    assert mine_chair["offline"] is True, mine_chair   # đây là chỗ thực địa báo thiếu


async def test_khong_bao_dong_khi_may_van_dang_goi_ve(client, factory, db):
    """Máy còn gọi về đều đặn thì KHÔNG được báo mất kết nối (tránh nhấp nháy cả bảng)."""
    chair, ctok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}], owner_id=chair.id)
    cand = await factory.candidate(exam.id)

    tok = (await client.post("/api/exam/auth/login",
                             json={"cccd": cand.cccd},
                             headers={"X-Device-Id": "dev-2"})).json()["token"]
    await client.post("/api/exam/auth/confirm",
                      headers={**auth(tok), "X-Device-Id": "dev-2"})

    rows = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions",
                             headers=auth(ctok))).json()
    assert next(s for s in rows if s["cccd"] == cand.cccd)["offline"] is False
