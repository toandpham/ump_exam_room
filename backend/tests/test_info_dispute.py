"""Thí sinh bấm "Báo giám thị" (sai thông tin) thì chủ tịch/giám thị PHẢI thấy.

Lỗi hiện trường 30-07: endpoint vẫn chạy và vẫn ghi nhật ký, nhưng nó chỉ phát qua
WebSocket cho trang quản trị — mà bộ nghe (useAdminSocket + AlertsPanel) đã bị gỡ
cùng lúc với box Thông báo (AD-77). Tín hiệu vẫn gửi đi, không còn ai nghe.

Nay cờ được ghi vào hồ sơ thí sinh nên nó hiện trên chính dòng của người đó ở bảng
giám sát (chủ tịch) và bảng phòng (giám thị), qua nhịp poll sẵn có — không dựng lại
box feed cũ.
"""

from tests.conftest import auth


def xff(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


async def test_dispute_shows_on_monitor_and_clears_after_edit(client, factory):
    exam, sitting, _payload = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, ptok = await factory.admin()
    ip = "10.55.0.1"
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                             headers=xff(ip))).json()["token"]
    ch = {**auth(tok), **xff(ip)}

    # 1. CHƯA xác nhận (đang ở màn đối chiếu thông tin) → nằm trong danh sách
    #    "chưa đăng nhập" của roster; cờ phải hiện được ở đó.
    r = await client.post("/api/exam/auth/dispute", headers=ch)
    assert r.status_code == 200, r.text

    roster = (await client.get(f"/api/admin/sittings/{sitting.id}/roster",
                               headers=auth(ptok))).json()
    row = next(c for c in roster["not_logged_in"] if c["cccd"] == cand.cccd)
    assert row["info_disputed"] is True, row

    # 2. Sau khi xác nhận → có phiên → cờ theo sang bảng giám sát.
    await client.post("/api/exam/auth/confirm", headers=ch)
    sessions = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions",
                                 headers=auth(ptok))).json()
    assert sessions[0]["info_disputed"] is True, sessions[0]

    # 3. Chủ tịch sửa thông tin → cờ tự tắt (không phải bấm tay để dọn).
    r = await client.patch(f"/api/admin/candidates/{cand.id}",
                           json={"full_name": "Nguyễn Văn Đã Sửa"}, headers=auth(ptok))
    assert r.status_code == 200, r.text
    sessions = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions",
                                 headers=auth(ptok))).json()
    assert sessions[0]["info_disputed"] is False, sessions[0]


async def test_dispute_visible_to_room_proctor(client, factory):
    """Giám thị nhìn phòng của mình cũng phải thấy — họ mới là người sửa tại chỗ."""
    exam, _sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}])
    proctor, _ = await factory.admin(role="room_proctor")
    room = await factory.room(exam.id, proctor_id=proctor.id)
    cand = await factory.candidate(exam.id, room_id=room.id)
    ip = "10.55.0.2"
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                             headers=xff(ip))).json()["token"]
    await client.post("/api/exam/auth/dispute", headers={**auth(tok), **xff(ip)})

    _, ptok = await factory.admin()          # chủ tịch xem được mọi phòng
    seating = (await client.get(f"/api/admin/rooms/{room.id}/seating",
                                headers=auth(ptok))).json()
    row = next(c for c in seating if c["cccd"] == cand.cccd)
    assert row["info_disputed"] is True, row
