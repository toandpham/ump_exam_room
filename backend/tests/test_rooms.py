"""Rooms (phòng thi), giám thị accounts, seating, and per-room pause scoping (AD-47)."""

from app.models.enums import AdminRole
from tests.conftest import auth


def xff(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


async def test_chairman_creates_and_assigns_room_proctor(client, factory):
    """A chủ tịch (proctor) creates a giám thị account, a room, and assigns the
    giám thị to it; the giám thị then sees the room via /my-rooms."""
    chair, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam = await factory.owned_exam(chair.id)

    # Create a giám thị account. Unique username: the test runs against the live
    # dev DB, so a fixed name would 409 if an earlier run died before cleanup.
    import uuid as _uuid
    gt_username = f"tst_gt_{_uuid.uuid4().hex[:8]}"
    r = await client.post("/api/admin/admins/room-proctors",
                          json={"username": gt_username, "password": "pw123456",
                                "full_name": "Giám thị 1"}, headers=auth(ctok))
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "room_proctor"
    rp_id = r.json()["id"]

    # It shows in the giám thị list.
    lst = (await client.get("/api/admin/admins/room-proctors", headers=auth(ctok))).json()
    assert any(a["id"] == rp_id for a in lst)

    # Create a room + assign the giám thị.
    r = await client.post(f"/api/admin/exams/{exam.id}/rooms",
                          json={"name": "Phòng A", "proctor_id": rp_id}, headers=auth(ctok))
    assert r.status_code == 201, r.text
    assert r.json()["proctor_name"] == "Giám thị 1"

    # The giám thị logs in and sees the room.
    _, rptok = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    # Re-point the just-created room to THIS proctor token's admin for the view test.
    rooms = (await client.get(f"/api/admin/exams/{exam.id}/rooms", headers=auth(ctok))).json()
    room_id = rooms[0]["id"]
    # Assign to the room_proctor whose token we hold.
    me = (await client.get("/api/admin/auth/me", headers=auth(rptok))).json()
    await client.patch(f"/api/admin/rooms/{room_id}",
                       json={"proctor_id": me["id"]}, headers=auth(ctok))
    mine = (await client.get("/api/admin/my-rooms", headers=auth(rptok))).json()
    assert any(m["room_id"] == room_id for m in mine)

    # Rooms of CLOSED (archived) exams disappear from /my-rooms — the giám thị
    # pool accounts are reused, so old rooms must not pile up.
    from app.database import AsyncSessionLocal as _ASL
    from app.models import Exam as _Exam
    from app.models.enums import ExamStatus as _ES
    async with _ASL() as s:
        ex = await s.get(_Exam, exam.id)
        ex.status = _ES.CLOSED.value
        await s.commit()
    mine = (await client.get("/api/admin/my-rooms", headers=auth(rptok))).json()
    assert not any(m["room_id"] == room_id for m in mine)

    # Clean up extra account.
    from app.database import AsyncSessionLocal
    from app.models import Admin
    from sqlalchemy import delete as _del
    async with AsyncSessionLocal() as s:
        await s.execute(_del(Admin).where(Admin.username == gt_username))
        await s.commit()


async def test_create_exam_with_structure(client, factory):
    """The create wizard declares structure up front: room_count + sittings are
    generated in one call (AD-47 setup flow). The at-most-1-active invariant is
    global, so we temporarily archive any pre-existing active exam (e.g. a manual
    one in the dev DB) and restore it afterwards — non-destructive."""
    from sqlalchemy import select as _sel
    from app.database import AsyncSessionLocal
    from app.models import Exam
    from app.models.enums import ExamStatus

    _, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    async with AsyncSessionLocal() as s:
        saved = [e.id for e in await s.scalars(
            _sel(Exam).where(Exam.status == ExamStatus.ACTIVE.value))]
        for eid in saved:
            (await s.get(Exam, eid)).status = ExamStatus.CLOSED.value
        await s.commit()

    created_id = None
    try:
        r = await client.post("/api/admin/exams", json={
            "name": "TST_struct", "duration_minutes": 60, "room_count": 3,
            "sittings": [
                {"name": "Sáng 03/06", "scheduled_date": "2026-06-03"},
                {"name": "Chiều 03/06", "scheduled_date": "2026-06-03", "duration_minutes": 90},
            ],
        }, headers=auth(ctok))
        assert r.status_code == 201, r.text
        created_id = r.json()["id"]
        assert r.json()["sitting_count"] == 2

        rooms = (await client.get(f"/api/admin/exams/{created_id}/rooms", headers=auth(ctok))).json()
        assert sorted(x["name"] for x in rooms) == ["Phòng 1", "Phòng 2", "Phòng 3"]

        sittings = (await client.get(f"/api/admin/exams/{created_id}/sittings", headers=auth(ctok))).json()
        assert [s["name"] for s in sittings] == ["Sáng 03/06", "Chiều 03/06"]
        assert sittings[0]["duration_minutes"] == 60   # inherits exam default
        assert sittings[1]["duration_minutes"] == 90   # own override
    finally:
        async with AsyncSessionLocal() as s:
            if created_id:
                e = await s.get(Exam, created_id)
                if e:
                    await s.delete(e)
            for eid in saved:
                e = await s.get(Exam, eid)
                if e:
                    e.status = ExamStatus.ACTIVE.value
            await s.commit()


async def test_kiosk_endpoints_removed(client, factory):
    """Chế độ kiosk (link theo máy + auto-login theo ghế) đã bị gỡ (AD-53)."""
    chair, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=chair.id)
    # Endpoint link-theo-máy không còn.
    r = await client.get(f"/api/admin/exams/{exam.id}/seat-logins", headers=auth(ctok))
    assert r.status_code in (404, 405), r.text
    # Endpoint auto-login theo ghế không còn.
    r2 = await client.post("/api/exam/auth/seat-login",
                           json={"room_token": "whatever-token", "seat": 1})
    assert r2.status_code in (404, 405), r2.text


async def test_my_rooms_returns_shared_countdown(client, factory):
    """/my-rooms trả đồng hồ thi CHUNG (AD-78): cohort_end_time = deadline sớm
    nhất của phiên đang làm trong buổi active + server_time để neo đếm ngược."""
    from datetime import datetime, timedelta, timezone
    from app.database import AsyncSessionLocal
    from app.models import ExamSession
    from app.models.enums import SessionStatus

    gt, rptok = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    chair, _ = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=chair.id)
    room = await factory.room(exam.id, proctor_id=gt.id, name="P-timer")
    cand = await factory.candidate(exam.id, room_id=room.id)

    # Chưa có phiên đang làm → cohort_end_time null, server_time có.
    mine = (await client.get("/api/admin/my-rooms", headers=auth(rptok))).json()
    row = next(m for m in mine if m["room_id"] == str(room.id))
    assert row["cohort_end_time"] is None
    assert row["server_time"] is not None

    # Tạo 1 phiên in_progress với end_time 30 phút nữa.
    end = datetime.now(timezone.utc) + timedelta(minutes=30)
    async with AsyncSessionLocal() as s:
        s.add(ExamSession(
            candidate_id=cand.id, sitting_id=sitting.id, exam_id=exam.id,
            status=SessionStatus.IN_PROGRESS.value, end_time=end,
        ))
        await s.commit()

    mine = (await client.get("/api/admin/my-rooms", headers=auth(rptok))).json()
    row = next(m for m in mine if m["room_id"] == str(room.id))
    assert row["cohort_end_time"] is not None
    # Trả về đúng end_time đã đặt (chênh < 5s).
    got = datetime.fromisoformat(row["cohort_end_time"])
    assert abs((got - end).total_seconds()) < 5


async def test_reset_room_proctor_pin(client, factory):
    """Chủ tịch đặt lại mật khẩu giám thị về 6 số; giám thị đăng nhập được bằng PIN (AD-48)."""
    gt, _ = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    _, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    r = await client.post(f"/api/admin/admins/room-proctors/{gt.id}/reset-pin", headers=auth(ctok))
    assert r.status_code == 200, r.text
    pin = r.json()["pin"]
    assert len(pin) == 6 and pin.isdigit()
    lr = await client.post("/api/admin/auth/login", json={"username": gt.username, "password": pin})
    assert lr.status_code == 200 and lr.json()["access_token"]


async def test_room_proctor_cannot_operate_exams(client, factory):
    """A giám thị (room_proctor) has no exam-control powers (403)."""
    _, rptok = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    assert (await client.post("/api/admin/exams",
            json={"name": "TST_x", "duration_minutes": 30}, headers=auth(rptok))).status_code == 403
    assert (await client.get("/api/admin/admins/room-proctors", headers=auth(rptok))).status_code == 403


async def test_assign_rooms_room_only(client, factory):
    """Chủ tịch "Chia thí sinh vào phòng" chỉ gán PHÒNG (AD-53: bỏ vị trí ngồi/ghế).
    Giám thị xem được danh sách thí sinh phòng mình. Endpoint xếp ghế đã gỡ."""
    chair, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    gt, gttok = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=chair.id)
    r1 = await factory.room(exam.id, proctor_id=gt.id, name="P1")
    r2 = await factory.room(exam.id, name="P2")
    for _ in range(5):
        await factory.candidate(exam.id)

    r = await client.post(f"/api/admin/exams/{exam.id}/assign-rooms",
                          json={"seed": "fixed"}, headers=auth(ctok))
    assert r.status_code == 200 and r.json()["total"] == 5, r.text
    counts = {row["room_id"]: row["count"] for row in r.json()["rooms"]}
    assert counts[str(r1.id)] + counts[str(r2.id)] == 5
    assert abs(counts[str(r1.id)] - counts[str(r2.id)]) <= 1

    # Giám thị xem danh sách thí sinh phòng mình (không còn cột ghế).
    seating = (await client.get(f"/api/admin/rooms/{r1.id}/seating", headers=auth(gttok))).json()
    assert len(seating) == counts[str(r1.id)]
    assert all("seat_number" not in s for s in seating)

    # Endpoint xếp ghế đã bị gỡ.
    gone = await client.post(f"/api/admin/rooms/{r1.id}/assign-seats", json={}, headers=auth(gttok))
    assert gone.status_code in (404, 405), gone.text

    # Excel export danh sách phòng vẫn chạy.
    x = await client.get(f"/api/admin/exams/{exam.id}/seating.xlsx", headers=auth(ctok))
    assert x.status_code == 200 and len(x.content) > 0


async def test_assign_rooms_explicit_counts(client, factory):
    """Chủ tịch tự nhập số thí sinh mỗi phòng (≤ sức chứa); tổng ≤ số thí sinh,
    phần dư để chưa xếp. Vượt sức chứa / vượt tổng → 400 (AD-49)."""
    chair, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, _sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=chair.id)
    from sqlalchemy import select as _sel
    from app.database import AsyncSessionLocal
    from app.models import Room as _Room

    r1 = await factory.room(exam.id, name="P1")
    r2 = await factory.room(exam.id, name="P2")
    async with AsyncSessionLocal() as s:
        for room in await s.scalars(_sel(_Room).where(_Room.exam_id == exam.id)):
            room.capacity = 3
        await s.commit()
    for _ in range(5):
        await factory.candidate(exam.id)

    # Nhập 2 + 2 (tổng 4 ≤ 5) → 1 thí sinh chưa xếp.
    r = await client.post(f"/api/admin/exams/{exam.id}/assign-rooms", json={"counts": [
        {"room_id": str(r1.id), "count": 2}, {"room_id": str(r2.id), "count": 2}]}, headers=auth(ctok))
    assert r.status_code == 200, r.text
    counts = {row["room_id"]: row["count"] for row in r.json()["rooms"]}
    assert counts[str(r1.id)] == 2 and counts[str(r2.id)] == 2
    assert r.json()["total"] == 5  # 1 còn lại chưa xếp

    # Vượt sức chứa (4 > 3) → 400.
    over = await client.post(f"/api/admin/exams/{exam.id}/assign-rooms", json={"counts": [
        {"room_id": str(r1.id), "count": 4}]}, headers=auth(ctok))
    assert over.status_code == 400 and "vượt sức chứa" in over.json()["detail"]

    # Tổng vượt số thí sinh (3 + 3 = 6 > 5) → 400.
    toomany = await client.post(f"/api/admin/exams/{exam.id}/assign-rooms", json={"counts": [
        {"room_id": str(r1.id), "count": 3}, {"room_id": str(r2.id), "count": 3}]}, headers=auth(ctok))
    assert toomany.status_code == 400 and "vượt số thí sinh" in toomany.json()["detail"]


async def test_close_exam_archives(client, factory):
    """Đóng kỳ thi (lưu trữ): chủ tịch đóng kỳ thi không có buổi đang mở → 200 +
    status=closed. (Verify the bug 'Đã có lỗi xảy ra' is FE-only, not backend.)"""
    from sqlalchemy import select as _sel
    from app.database import AsyncSessionLocal
    from app.models import Exam
    from app.models.enums import ExamStatus

    _, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    async with AsyncSessionLocal() as s:
        saved = [e.id for e in await s.scalars(
            _sel(Exam).where(Exam.status == ExamStatus.ACTIVE.value))]
        for eid in saved:
            (await s.get(Exam, eid)).status = ExamStatus.CLOSED.value
        await s.commit()
    created = None
    try:
        r = await client.post("/api/admin/exams",
                              json={"name": "TST_close", "duration_minutes": 30}, headers=auth(ctok))
        assert r.status_code == 201, r.text
        created = r.json()["id"]
        r2 = await client.post(f"/api/admin/exams/{created}/close", headers=auth(ctok))
        assert r2.status_code == 200, r2.text
        detail = (await client.get(f"/api/admin/exams/{created}", headers=auth(ctok))).json()
        assert detail["status"] == "closed"
    finally:
        async with AsyncSessionLocal() as s:
            if created:
                e = await s.get(Exam, created)
                if e:
                    await s.delete(e)
            for eid in saved:
                e = await s.get(Exam, eid)
                if e:
                    e.status = ExamStatus.ACTIVE.value
            await s.commit()


async def test_only_super_admin_deletes_sitting(client, factory):
    """Xoá buổi thi là quyền của Quản trị (super_admin); chủ tịch (proctor) — kể cả
    người sở hữu kỳ thi — KHÔNG xoá được (403). (AD-49)"""
    chair, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    _, stok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)
    exam, sitting = await factory.empty_active_exam(chair.id)

    # Chủ tịch sở hữu kỳ thi nhưng KHÔNG xoá được buổi.
    r = await client.delete(f"/api/admin/sittings/{sitting.id}", headers=auth(ctok))
    assert r.status_code == 403, r.text
    # Quản trị xoá được.
    r2 = await client.delete(f"/api/admin/sittings/{sitting.id}", headers=auth(stok))
    assert r2.status_code == 204, r2.text


async def test_room_proctor_real_name_persists(client, factory):
    """Chủ tịch đặt TÊN THẬT của giám thị cho phòng (account là pool cố định dùng
    chung); tên lưu DB để tra cứu, sửa được, và phòng của kỳ thi mới bắt đầu trống
    (auto-reset theo từng lần thi) (AD-49)."""
    chair, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    gt, _ = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    exam = await factory.owned_exam(chair.id)

    # Tạo phòng kèm tên giám thị thật.
    r = await client.post(f"/api/admin/exams/{exam.id}/rooms",
                          json={"name": "Phòng A", "proctor_id": str(gt.id),
                                "proctor_real_name": "Nguyễn Văn A"}, headers=auth(ctok))
    assert r.status_code == 201, r.text
    room_id = r.json()["id"]
    assert r.json()["proctor_real_name"] == "Nguyễn Văn A"

    # Sửa tên thật.
    u = await client.patch(f"/api/admin/rooms/{room_id}",
                           json={"proctor_real_name": "Trần Thị B"}, headers=auth(ctok))
    assert u.status_code == 200 and u.json()["proctor_real_name"] == "Trần Thị B"
    # Xoá trống (chuỗi rỗng → null).
    u2 = await client.patch(f"/api/admin/rooms/{room_id}",
                            json={"proctor_real_name": "  "}, headers=auth(ctok))
    assert u2.json()["proctor_real_name"] is None

    # Phòng tạo mặc định (không gửi tên) → trống.
    r2 = await client.post(f"/api/admin/exams/{exam.id}/rooms",
                           json={"name": "Phòng B"}, headers=auth(ctok))
    assert r2.json()["proctor_real_name"] is None


async def test_import_assigns_rooms_from_excel(client, factory):
    """Import Excel có cột "Phòng" → tự gán thí sinh vào phòng; tên phòng chưa có
    thì tự tạo (AD-54 — chủ tịch không cần chia phòng thủ công)."""
    import io
    from openpyxl import Workbook

    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    chair, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam = await factory.owned_exam(chair.id)  # draft → import không bị khoá
    existing = await factory.room(exam.id, name="Phòng 1")

    wb = Workbook(); ws = wb.active
    ws.append(["CCCD", "Họ tên", "Ngày sinh", "Đơn vị", "Năm", "Ngành", "Đối tượng", "Lần", "Phòng"])
    ws.append(["079200000801", "TS A", "2000-01-01", "ĐV", "", "", "ĐT1", 1, "Phòng 1"])
    ws.append(["079200000802", "TS B", "2000-01-01", "ĐV", "", "", "ĐT1", 1, "Phòng 2"])  # auto-create
    bio = io.BytesIO(); wb.save(bio)

    pr = await client.post("/api/admin/candidates/import/preview",
                           files={"file": ("ts.xlsx", bio.getvalue(), xlsx)}, headers=auth(ctok))
    assert pr.status_code == 200, pr.text
    token = pr.json()["token"]
    cm = await client.post("/api/admin/candidates/import/commit",
                           json={"token": token, "exam_id": str(exam.id)}, headers=auth(ctok))
    assert cm.status_code == 200 and cm.json()["created"] == 2, cm.text

    rooms = (await client.get(f"/api/admin/exams/{exam.id}/rooms", headers=auth(ctok))).json()
    assert "Phòng 2" in {r["name"] for r in rooms}  # tự tạo
    seat1 = (await client.get(f"/api/admin/rooms/{existing.id}/seating", headers=auth(ctok))).json()
    assert any(s["cccd"] == "079200000801" for s in seat1)


async def test_giam_thi_add_candidate_to_room(client, factory):
    """Giám thị thêm 1 thí sinh lẻ vào phòng MÌNH (kể cả kỳ thi đang chạy); không
    thêm được phòng khác (404). Chủ tịch thêm được mọi phòng (AD-54)."""
    chair, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    gt, gttok = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=chair.id)
    mine = await factory.room(exam.id, proctor_id=gt.id, name="P-mine")
    other = await factory.room(exam.id, name="P-other")

    body = {"cccd": "079200000811", "full_name": "Walk In", "birth_date": "2000-01-01",
            "unit": "ĐV", "category": "ĐT1", "attempt_number": 1}
    r = await client.post(f"/api/admin/rooms/{mine.id}/candidates", json=body, headers=auth(gttok))
    assert r.status_code == 201, r.text
    # vào đúng phòng giám thị
    seats = (await client.get(f"/api/admin/rooms/{mine.id}/seating", headers=auth(gttok))).json()
    assert any(s["cccd"] == "079200000811" for s in seats)

    # giám thị KHÔNG thêm được phòng khác
    body2 = {**body, "cccd": "079200000812"}
    assert (await client.post(f"/api/admin/rooms/{other.id}/candidates",
            json=body2, headers=auth(gttok))).status_code == 404
    # chủ tịch thêm được phòng khác
    assert (await client.post(f"/api/admin/rooms/{other.id}/candidates",
            json=body2, headers=auth(ctok))).status_code == 201

    # dọn 2 thí sinh vừa thêm (không qua factory)
    from sqlalchemy import delete as _del
    from app.database import AsyncSessionLocal
    from app.models import Candidate as _C
    async with AsyncSessionLocal() as s:
        await s.execute(_del(_C).where(_C.cccd.in_(["079200000811", "079200000812"])))
        await s.commit()


async def test_room_proctor_pause_only_own_room(client, factory):
    """A giám thị may pause a candidate in THEIR room but not another room (404);
    the chủ tịch may pause any candidate of their exam."""
    chair, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    gt, gttok = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    exam, sitting, payload = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=chair.id)
    mine = await factory.room(exam.id, proctor_id=gt.id, name="Phòng tôi")
    other = await factory.room(exam.id, name="Phòng khác")

    in_room = await factory.candidate(exam.id, room_id=mine.id)
    out_room = await factory.candidate(exam.id, room_id=other.id)

    async def run(cand, ip):
        tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=xff(ip))).json()["token"]
        ch = {**auth(tok), **xff(ip)}
        await client.post("/api/exam/auth/confirm", headers=ch)
        return (await client.get("/api/exam/state", headers=ch)).json()["session_id"]

    sid_in = await run(in_room, "10.20.0.1")
    sid_out = await run(out_room, "10.20.0.2")
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ctok))

    # Giám thị pauses the candidate in their own room → OK.
    assert (await client.post(f"/api/admin/sessions/{sid_in}/pause", headers=auth(gttok))).status_code == 200
    # …but not a candidate in another room → 404 (hidden).
    assert (await client.post(f"/api/admin/sessions/{sid_out}/pause", headers=auth(gttok))).status_code == 404
    # Chủ tịch can pause either.
    assert (await client.post(f"/api/admin/sessions/{sid_out}/pause", headers=auth(ctok))).status_code == 200
    # Giám thị resumes their own.
    assert (await client.post(f"/api/admin/sessions/{sid_in}/resume", headers=auth(gttok))).status_code == 200
