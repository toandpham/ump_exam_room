"""Dữ liệu hành vi làm bài + phát hiện chép bài (đợt 4).

``answered_at`` bị ghi đè mỗi lần đổi đáp án, nên hiện không có cách nào biết thí
sinh quyết định lúc nào và đã đổi ý mấy lần. Hai cột mới giữ lại điều đó.

Chỉ số trùng khớp dùng phép đếm kinh điển: hai bài CÙNG SAI MỘT KIỂU mới đáng ngờ —
cùng đúng là chuyện bình thường của người học được bài. Chỉ so trong CÙNG PHÒNG vì
ngồi cạnh nhau mới chép được nhau, và vì so toàn kỳ là 125.000 cặp thay vì ~1.200.
"""

from sqlalchemy import select

from app.models import Answer, ExamSession
from tests.conftest import auth, fast_forward_start

QUESTIONS = [
    {"text": "Q1", "correct": "A"},
    {"text": "Q2", "correct": "A"},
    {"text": "Q3", "correct": "A"},
    {"text": "Q4", "correct": "A"},
]


async def _join(client, factory, exam, ip, room_id=None):
    cand = await factory.candidate(exam.id, room_id=room_id)
    xff = {"X-Forwarded-For": ip}
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                             headers=xff)).json()["token"]
    ch = {**auth(tok), **xff}
    await client.post("/api/exam/auth/confirm", headers=ch)
    return cand, ch


async def test_first_answer_time_and_change_count(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    _, ch = await _join(client, factory, exam, "10.75.0.1")
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)
    qid = (await client.get("/api/exam/questions", headers=ch)).json()["questions"][0]["id"]

    await client.post("/api/exam/answer", json={"question_id": qid, "selected_option": "A"},
                      headers=ch)
    a = await db.scalar(select(Answer).where(Answer.question_id == qid))
    first = a.first_answered_at
    assert first is not None
    assert a.change_count == 0

    # Chọn LẠI cùng đáp án = không phải đổi ý.
    await client.post("/api/exam/answer", json={"question_id": qid, "selected_option": "A"},
                      headers=ch)
    db.expire_all()
    a = await db.scalar(select(Answer).where(Answer.question_id == qid))
    assert a.change_count == 0, "chọn lại cùng đáp án không tính là đổi"

    # Đổi sang đáp án khác = đổi ý, nhưng mốc quyết định ĐẦU giữ nguyên.
    await client.post("/api/exam/answer", json={"question_id": qid, "selected_option": "B"},
                      headers=ch)
    db.expire_all()
    a = await db.scalar(select(Answer).where(Answer.question_id == qid))
    assert a.change_count == 1
    assert a.first_answered_at == first, "mốc quyết định đầu tiên không được ghi đè"
    assert a.answered_at > first


async def test_bulk_save_tracks_changes_too(client, factory, db):
    """Máy thí sinh đẩy đáp án theo lô — đường này cũng phải đếm đúng."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    _, ch = await _join(client, factory, exam, "10.75.0.2")
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)
    qs = (await client.get("/api/exam/questions", headers=ch)).json()["questions"]
    qid = qs[0]["id"]

    await client.post("/api/exam/answers",
                      json={"answers": [{"question_id": qid, "selected_option": "A"}]},
                      headers=ch)
    await client.post("/api/exam/answers",
                      json={"answers": [{"question_id": qid, "selected_option": "C"}]},
                      headers=ch)
    db.expire_all()
    a = await db.scalar(select(Answer).where(Answer.question_id == qid))
    assert a.change_count == 1
    assert a.first_answered_at is not None


async def test_monitor_shows_answered_and_viewed_counts(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    _, ch = await _join(client, factory, exam, "10.75.0.3")
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)
    qs = (await client.get("/api/exam/questions", headers=ch)).json()["questions"]

    await client.post("/api/exam/answers", json={
        "answers": [{"question_id": qs[0]["id"], "selected_option": "A"},
                    {"question_id": qs[1]["id"], "selected_option": "B"}],
        "viewed_count": 3,
    }, headers=ch)

    row = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions",
                            headers=auth(ptok))).json()[0]
    assert row["answered_count"] == 2
    assert row["viewed_count"] == 3
    assert row["question_total"] == 4


async def test_viewed_count_never_goes_backwards(client, factory, db):
    """Thí sinh quay lại câu 1 không có nghĩa là họ 'chưa xem' các câu sau."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    _, ch = await _join(client, factory, exam, "10.75.0.4")
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)
    qs = (await client.get("/api/exam/questions", headers=ch)).json()["questions"]
    body = {"answers": [{"question_id": qs[0]["id"], "selected_option": "A"}]}

    await client.post("/api/exam/answers", json={**body, "viewed_count": 4}, headers=ch)
    await client.post("/api/exam/answers", json={**body, "viewed_count": 1}, headers=ch)
    # Phiên CSDL của test giữ giao dịch mở từ trước lúc endpoint ghi → đọc bằng
    # phiên mới.
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as fresh:
        s = await fresh.scalar(select(ExamSession).where(ExamSession.sitting_id == sitting.id))
        assert s.viewed_count == 4


async def test_collusion_counts_shared_wrong_answers_in_the_same_room(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    room = await factory.room(exam.id, name="Phòng 1")
    c1, ch1 = await _join(client, factory, exam, "10.75.0.5", room_id=room.id)
    c2, ch2 = await _join(client, factory, exam, "10.75.0.6", room_id=room.id)
    c3, ch3 = await _join(client, factory, exam, "10.75.0.7", room_id=room.id)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)

    async def answer(ch, opts):
        qs = (await client.get("/api/exam/questions", headers=ch)).json()["questions"]
        # Đề trộn nên phải gửi theo ĐÚNG câu, không theo vị trí — map bằng id.
        by_text = {q["id"]: q for q in qs}
        await client.post("/api/exam/answers", json={"answers": [
            {"question_id": qid, "selected_option": opt}
            for qid, opt in zip(by_text.keys(), opts)
        ]}, headers=ch)

    # Đáp án đúng đều là A. c1 và c2 sai GIỐNG HỆT ở 3 câu; c3 làm đúng hết.
    await answer(ch1, ["B", "C", "D", "A"])
    await answer(ch2, ["B", "C", "D", "A"])
    await answer(ch3, ["A", "A", "A", "A"])
    await client.post("/api/exam/submit", headers=ch1)
    await client.post("/api/exam/submit", headers=ch2)
    await client.post("/api/exam/submit", headers=ch3)
    await client.post(f"/api/admin/sittings/{sitting.id}/end?force=true", headers=auth(ptok))

    pairs = (await client.get(f"/api/admin/sittings/{sitting.id}/collusion",
                              headers=auth(ptok))).json()
    assert pairs, "phải phát hiện được cặp cùng sai một kiểu"
    top = pairs[0]
    names = {top["a_cccd"], top["b_cccd"]}
    assert names == {c1.cccd, c2.cccd}
    assert top["shared_wrong"] == 3
    assert top["room_name"] == "Phòng 1"
    # Người làm đúng hết không được kéo vào danh sách.
    assert all(c3.cccd not in {p["a_cccd"], p["b_cccd"]} for p in pairs)


async def test_collusion_does_not_pair_across_rooms(client, factory, db):
    """Ngồi khác phòng thì không chép được nhau — so làm gì cho tốn."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    r1 = await factory.room(exam.id, name="Phòng 1")
    r2 = await factory.room(exam.id, name="Phòng 2")
    _, ch1 = await _join(client, factory, exam, "10.75.0.8", room_id=r1.id)
    _, ch2 = await _join(client, factory, exam, "10.75.0.9", room_id=r2.id)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)

    for ch in (ch1, ch2):
        qs = (await client.get("/api/exam/questions", headers=ch)).json()["questions"]
        await client.post("/api/exam/answers", json={"answers": [
            {"question_id": q["id"], "selected_option": "D"} for q in qs
        ]}, headers=ch)
        await client.post("/api/exam/submit", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/end?force=true", headers=auth(ptok))

    pairs = (await client.get(f"/api/admin/sittings/{sitting.id}/collusion",
                              headers=auth(ptok))).json()
    assert pairs == [], "hai người khác phòng không được ghép cặp"


async def test_collusion_refuses_while_the_sitting_is_still_open(client, factory):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    r = await client.get(f"/api/admin/sittings/{sitting.id}/collusion", headers=auth(ptok))
    assert r.status_code == 409, "đây là việc hậu kiểm, không chạy giữa giờ thi"


async def test_collusion_is_owner_scoped_and_chairman_only(client, factory, db):
    from app.models.enums import AdminRole
    admin, ptok = await factory.admin()
    other, otok = await factory.admin()
    gt, gtok = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)

    assert (await client.get(f"/api/admin/sittings/{sitting.id}/collusion",
                             headers=auth(otok))).status_code == 404
    assert (await client.get(f"/api/admin/sittings/{sitting.id}/collusion",
                             headers=auth(gtok))).status_code == 403
