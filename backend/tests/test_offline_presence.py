"""Báo "mất kết nối" cho chủ tịch/giám thị — nhưng KHÔNG báo nhầm khi mạng chớp.

Chỉ báo cũ (AD-38) đã bị gỡ vì ngưỡng 25 giây quá nhạy: máy Win7 khựng một cái là
cả bảng nhấp nháy. Nay dùng ngưỡng RIÊNG 90 giây, tách khỏi ngưỡng 25 giây vốn dùng
cho việc phát hiện đăng nhập từ thiết bị khác (KHÔNG được đụng vào, đó là chống gian
lận). Máy thí sinh gọi về server mỗi 5–15 giây nên 90 giây = bỏ lỡ nhiều nhịp liền,
tức mất kết nối thật.
"""

import json
import time

from app.core import device_lock
from tests.conftest import auth, fast_forward_start


def xff(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


async def _seen_seconds_ago(candidate_id, seconds: int) -> None:
    """Vặn mốc nhịp tim của thí sinh về quá khứ (giả lập máy ngừng gọi về)."""
    raw = await device_lock.redis_client.get(device_lock._key(candidate_id))
    data = json.loads(raw)
    data["ts"] = int(time.time()) - seconds
    await device_lock.redis_client.set(device_lock._key(candidate_id), json.dumps(data))


async def test_offline_only_after_sustained_silence(client, factory):
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, ptok = await factory.admin()
    ip = "10.66.0.1"
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                             headers=xff(ip))).json()["token"]
    ch = {**auth(tok), **xff(ip)}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)

    async def row():
        r = await client.get(f"/api/admin/sittings/{sitting.id}/sessions", headers=auth(ptok))
        return r.json()[0]

    # Vừa gọi về → đang kết nối.
    assert (await row())["offline"] is False

    # Im 30 giây = chớp mạng / máy khựng → KHÔNG báo (đây là chỗ bản cũ báo nhầm).
    await _seen_seconds_ago(cand.id, 30)
    assert (await row())["offline"] is False, "30s chưa được coi là mất kết nối"

    # Im 120 giây = mất thật → báo, kèm số giây để giám thị biết mất bao lâu.
    await _seen_seconds_ago(cand.id, 120)
    r = await row()
    assert r["offline"] is True
    assert r["last_seen_seconds"] >= 120


async def test_no_offline_alert_for_finished_candidates(client, factory):
    """Nộp bài xong rồi tắt máy đi về là bình thường — không được báo mất kết nối."""
    exam, sitting, payload = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, ptok = await factory.admin()
    ip = "10.66.0.2"
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                             headers=xff(ip))).json()["token"]
    ch = {**auth(tok), **xff(ip)}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)
    await client.post("/api/exam/submit", headers=ch)

    await _seen_seconds_ago(cand.id, 600)      # đi về từ lâu
    r = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions",
                          headers=auth(ptok))).json()[0]
    assert r["status"] == "submitted"
    assert r["offline"] is False, "đã nộp bài thì không cần cảnh báo mất kết nối"
