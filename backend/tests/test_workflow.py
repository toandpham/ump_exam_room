"""End-to-end test của QUY TRÌNH THI MỚI (AD-47/AD-48), đi đúng thứ tự vận hành thật.

Khác với test_rooms.py (kiểm thử từng mảnh riêng lẻ), bài này stitch toàn bộ một
mạch như chủ tịch + giám thị + thí sinh làm trong ngày thi:

  1. Chủ tịch tạo kỳ thi có CẤU TRÚC (wizard): 2 phòng (sức chứa) + buổi.
  2. Hệ thống TỰ GÁN giám thị cố định giamthi1/giamthi2 vào Phòng 1/Phòng 2 (AD-48).
  3. Chủ tịch đặt lại PIN 6 số cho giám thị → giám thị đăng nhập bằng PIN.
  4. Chủ tịch nhập danh sách thí sinh → chia thí sinh vào PHÒNG (assign-rooms).
  5. Chia phòng CHỈ gán phòng (AD-53 — bỏ vị trí ngồi/ghế).
  6. Chủ tịch nạp đề QTI vào buổi → mở buổi.
  7. Thí sinh phòng 1 đăng nhập bằng CCCD → xác nhận.
  8. Chủ tịch phát đề → bắt đầu → thí sinh trả lời → nộp.
  9. Giám thị tạm dừng/tiếp tục thí sinh trong phòng mình.
 10. Báo cáo buổi → đóng buổi (purge đề) → đóng kỳ thi (lưu trữ).

Chạy thật qua Postgres/Redis (ASGITransport). Dùng marker TST_ và dọn sạch.
"""

from __future__ import annotations

from sqlalchemy import delete as sa_delete
from sqlalchemy import select as sa_select

from app.bootstrap import ensure_room_proctors, room_proctor_username
from app.database import AsyncSessionLocal
from app.models import Admin, Answer, Candidate, Exam, ExamSession, Room, Sitting
from app.models.enums import AdminRole, ExamStatus
from tests.conftest import auth, fast_forward_start, qenc, QENC_PASSWORD
from tests.test_qti_import import _build_qti_zip


def xff(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


async def _archive_active_exams() -> list:
    """Tạm lưu trữ mọi kỳ thi đang active (giữ at-most-1-active invariant) → trả id
    để khôi phục sau test. Non-destructive."""
    async with AsyncSessionLocal() as s:
        saved = [e.id for e in await s.scalars(
            sa_select(Exam).where(Exam.status == ExamStatus.ACTIVE.value))]
        for eid in saved:
            (await s.get(Exam, eid)).status = ExamStatus.CLOSED.value
        await s.commit()
    return saved


async def _restore_active_exams(saved: list) -> None:
    async with AsyncSessionLocal() as s:
        for eid in saved:
            e = await s.get(Exam, eid)
            if e:
                e.status = ExamStatus.ACTIVE.value
        await s.commit()


async def _purge_exam(exam_id) -> None:
    """Xoá sạch 1 kỳ thi do test tạo (qua API nên không được factory theo dõi):
    answers → sessions → candidates → rooms → sittings → exam (FK-safe)."""
    async with AsyncSessionLocal() as s:
        sess_ids = list(await s.scalars(
            sa_select(ExamSession.id).where(ExamSession.exam_id == exam_id)))
        if sess_ids:
            await s.execute(sa_delete(Answer).where(Answer.session_id.in_(sess_ids)))
            await s.execute(sa_delete(ExamSession).where(ExamSession.id.in_(sess_ids)))
        await s.execute(sa_delete(Candidate).where(Candidate.exam_id == exam_id))
        await s.execute(sa_delete(Room).where(Room.exam_id == exam_id))
        await s.execute(sa_delete(Sitting).where(Sitting.exam_id == exam_id))
        e = await s.get(Exam, exam_id)
        if e:
            await s.delete(e)
        await s.commit()


async def test_full_council_workflow(client, factory):
    """Toàn bộ quy trình thi mới, một mạch từ tạo kỳ thi đến đóng kỳ thi."""
    await ensure_room_proctors()  # đảm bảo pool giamthi1..10 tồn tại
    _, ctok = await factory.admin(role=AdminRole.PROCTOR.value)  # chủ tịch
    saved = await _archive_active_exams()
    exam_id = None
    try:
        # ── 1. Chủ tịch tạo kỳ thi có cấu trúc (wizard) — 2 phòng (sức chứa 5), 1 buổi.
        r = await client.post("/api/admin/exams", json={
            "name": "TST_workflow", "duration_minutes": 60,
            "room_count": 2, "room_capacity": 5,
            "sittings": [{"name": "Buổi sáng", "scheduled_date": "2026-06-03"}],
        }, headers=auth(ctok))
        assert r.status_code == 201, r.text
        exam_id = r.json()["id"]
        assert r.json()["sitting_count"] == 1

        # ── 2. Hai phòng tự gán giamthi1 / giamthi2 (AD-48).
        rooms = (await client.get(f"/api/admin/exams/{exam_id}/rooms", headers=auth(ctok))).json()
        rooms.sort(key=lambda x: x["name"])
        assert [x["name"] for x in rooms] == ["Phòng 1", "Phòng 2"]
        async with AsyncSessionLocal() as s:
            gt1 = await s.scalar(sa_select(Admin).where(
                Admin.username == room_proctor_username(1)))
            gt2 = await s.scalar(sa_select(Admin).where(
                Admin.username == room_proctor_username(2)))
        assert rooms[0]["proctor_id"] == str(gt1.id)
        assert rooms[1]["proctor_id"] == str(gt2.id)
        room1_id = rooms[0]["id"]

        # ── 3. Chủ tịch đặt lại PIN 6 số cho giám thị phòng 1 → giám thị login bằng PIN.
        pr = await client.post(
            f"/api/admin/admins/room-proctors/{gt1.id}/reset-pin", headers=auth(ctok))
        assert pr.status_code == 200, pr.text
        pin = pr.json()["pin"]
        assert len(pin) == 6 and pin.isdigit()
        lr = await client.post("/api/admin/auth/login",
                               json={"username": gt1.username, "password": pin})
        assert lr.status_code == 200, lr.text
        gttok = lr.json()["access_token"]

        # ── 4. Nhập danh sách thí sinh (4) → chia vào phòng.
        for _ in range(4):
            await factory.candidate(exam_id)
        ar = await client.post(f"/api/admin/exams/{exam_id}/assign-rooms",
                               json={"seed": "fixed"}, headers=auth(ctok))
        assert ar.status_code == 200 and ar.json()["total"] == 4, ar.text

        # ── 5. Chia phòng chỉ gán PHÒNG (AD-53: không còn ghế). Lấy 1 thí sinh phòng 1.
        seating = (await client.get(
            f"/api/admin/rooms/{room1_id}/seating", headers=auth(gttok))).json()
        assert seating and all("seat_number" not in s for s in seating)
        cand_cccd = seating[0]["cccd"]

        # ── 6. Nạp đề QTI vào buổi → mở buổi.
        sittings = (await client.get(
            f"/api/admin/exams/{exam_id}/sittings", headers=auth(ctok))).json()
        sitting_id = sittings[0]["id"]
        iq = await client.post(
            f"/api/admin/sittings/{sitting_id}/import-qti",
            files={"file": ("exam.qenc", qenc(_build_qti_zip()), "application/octet-stream")},
            data={"password": QENC_PASSWORD}, headers=auth(ctok))
        assert iq.status_code == 200 and iq.json()["question_count"] == 2, iq.text
        op = await client.post(f"/api/admin/sittings/{sitting_id}/open", headers=auth(ctok))
        assert op.status_code == 200 and op.json()["status"] == "active", op.text

        # ── 7. Thí sinh phòng 1 đăng nhập bằng CCCD → xác nhận.
        login_ch = {"X-Forwarded-For": "10.40.0.1", "X-Device-Id": "DEV-R1"}
        kl = await client.post("/api/exam/auth/login",
                               json={"cccd": cand_cccd}, headers=login_ch)
        assert kl.status_code == 200, kl.text
        ch = {**auth(kl.json()["token"]), **login_ch}
        assert (await client.post("/api/exam/auth/confirm", headers=ch)).status_code == 200

        # ── 8. Bắt đầu → trả lời → nộp (SP-2b: confirm đặt READY, bỏ distribute).
        assert (await client.post(
            f"/api/admin/sittings/{sitting_id}/start", headers=auth(ctok))
        ).json()["started"] >= 1
        await fast_forward_start(sitting_id)  # SP-2c: bỏ qua đếm ngược để trả lời ngay

        qs = (await client.get("/api/exam/questions", headers=ch)).json()
        assert len(qs["questions"]) == 2
        sid = (await client.get("/api/exam/state", headers=ch)).json()["session_id"]
        for q in qs["questions"]:
            assert (await client.post("/api/exam/answer",
                    json={"question_id": q["id"], "selected_option": "A"},
                    headers=ch)).status_code == 200

        # ── 9. Giám thị tạm dừng / tiếp tục thí sinh trong phòng mình.
        assert (await client.post(
            f"/api/admin/sessions/{sid}/pause", headers=auth(gttok))).status_code == 200
        # Khi đang tạm dừng, không ghi đáp án được.
        paused = await client.post("/api/exam/answer",
                                   json={"question_id": qs["questions"][0]["id"],
                                         "selected_option": "B"}, headers=ch)
        assert paused.status_code == 409, paused.text
        assert (await client.post(
            f"/api/admin/sessions/{sid}/resume", headers=auth(gttok))).status_code == 200

        body = (await client.post("/api/exam/submit", headers=ch)).json()
        assert body["total"] == 2 and body["total_correct"] == 2

        # ── 10. Báo cáo buổi → đóng buổi (purge đề) → đóng kỳ thi (lưu trữ).
        rep = (await client.get(
            f"/api/admin/sittings/{sitting_id}/report", headers=auth(ctok))).json()
        # AD-68: new 2-sheet report structure
        assert rep["meta"]["question_count"] == 2
        assert any(row["cccd"] == cand_cccd and row["total_correct"] == 2
                   for row in rep["rows"])

        assert (await client.post(
            f"/api/admin/sittings/{sitting_id}/end", headers=auth(ctok))).status_code == 200
        # Đề đã purge → không phục vụ câu hỏi nữa.
        assert (await client.get("/api/exam/questions", headers=ch)).status_code == 409

        cl = await client.post(f"/api/admin/exams/{exam_id}/close", headers=auth(ctok))
        assert cl.status_code == 200, cl.text
        detail = (await client.get(
            f"/api/admin/exams/{exam_id}", headers=auth(ctok))).json()
        assert detail["status"] == "closed"
    finally:
        if exam_id:
            await _purge_exam(exam_id)
        await _restore_active_exams(saved)


async def test_assign_rooms_rejects_overflow_capacity(client, factory):
    """Chia phòng khi tổng số máy < số thí sinh → 400 (báo thiếu chỗ), không gán nửa vời."""
    chair, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, _sitting, _ = await factory.active_exam(
        [{"text": "Q", "correct": "A"}], owner_id=chair.id)
    await factory.room(exam.id, name="P1")  # capacity mặc định 0 → set lại =2
    await factory.room(exam.id, name="P2")
    # Đặt capacity nhỏ hơn số thí sinh.
    async with AsyncSessionLocal() as s:
        for room in await s.scalars(sa_select(Room).where(Room.exam_id == exam.id)):
            room.capacity = 2
        await s.commit()
    for _ in range(5):  # 5 thí sinh > 4 máy
        await factory.candidate(exam.id)

    r = await client.post(f"/api/admin/exams/{exam.id}/assign-rooms",
                          json={"seed": "fixed"}, headers=auth(ctok))
    assert r.status_code == 400, r.text
    assert "Không đủ chỗ" in r.json()["detail"]
