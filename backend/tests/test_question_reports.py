"""Thí sinh khiếu nại về một câu hỏi, gắn vào bài thi (đợt 3).

Hiện trường: "câu 47 thiếu hình", "câu 12 không có đáp án đúng" — thí sinh giơ tay,
giám thị ghi ra giấy, đến lúc chấm thì thất lạc. "Báo giám thị" sẵn có (AD-122) chỉ
dùng cho sai thông tin cá nhân, không mang được nội dung.

Ranh giới quyền giữ nguyên AD-124: chủ tịch xem và xử lý danh sách; giám thị chỉ
thấy NHÃN trên dòng thí sinh trong phòng mình.
"""

from sqlalchemy import select

from app.models import QuestionReport
from app.models.enums import AdminRole
from tests.conftest import auth, fast_forward_start


async def _running(client, factory, exam, sitting, ptok, ip):
    cand = await factory.candidate(exam.id)
    xff = {"X-Forwarded-For": ip}
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                             headers=xff)).json()["token"]
    ch = {**auth(tok), **xff}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)
    qs = (await client.get("/api/exam/questions", headers=ch)).json()["questions"]
    return cand, ch, qs


async def test_candidate_reports_a_question_and_chairman_sees_it(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}, {"text": "Q2", "correct": "B"}], owner_id=admin.id)
    cand, ch, qs = await _running(client, factory, exam, sitting, ptok, "10.74.0.1")

    r = await client.post("/api/exam/question-report",
                          json={"question_id": qs[1]["id"],
                                "content": "Câu này thiếu hình chụp X-quang"},
                          headers=ch)
    assert r.status_code == 200, r.text
    assert r.json()["received"] is True

    lst = (await client.get(f"/api/admin/sittings/{sitting.id}/question-reports",
                            headers=auth(ptok))).json()
    assert len(lst) == 1
    item = lst[0]
    assert item["content"] == "Câu này thiếu hình chụp X-quang"
    assert item["full_name"] == cand.full_name
    assert item["cccd"] == cand.cccd
    assert item["question_number"] == 2, "số thứ tự câu TRONG ĐỀ CỦA THÍ SINH ĐÓ"
    assert item["resolved_at"] is None


async def test_report_rejects_a_question_outside_the_candidates_paper(client, factory):
    import uuid as _uuid
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q1", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch, _ = await _running(client, factory, exam, sitting, ptok, "10.74.0.2")
    r = await client.post("/api/exam/question-report",
                          json={"question_id": str(_uuid.uuid4()), "content": "abc xyz"},
                          headers=ch)
    assert r.status_code == 400


async def test_report_requires_content_and_is_capped(client, factory, db):
    """Chặn nghịch: một phiên tối đa 20 khiếu nại."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q1", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch, qs = await _running(client, factory, exam, sitting, ptok, "10.74.0.3")
    qid = qs[0]["id"]

    assert (await client.post("/api/exam/question-report",
                              json={"question_id": qid, "content": "   "},
                              headers=ch)).status_code == 422

    for i in range(20):
        assert (await client.post("/api/exam/question-report",
                                  json={"question_id": qid, "content": f"Lỗi số {i}"},
                                  headers=ch)).status_code == 200
    r = await client.post("/api/exam/question-report",
                          json={"question_id": qid, "content": "quá nhiều"}, headers=ch)
    assert r.status_code == 429


async def test_chairman_resolves_a_report(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q1", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch, qs = await _running(client, factory, exam, sitting, ptok, "10.74.0.4")
    await client.post("/api/exam/question-report",
                      json={"question_id": qs[0]["id"], "content": "Đề in mờ"}, headers=ch)
    rid = (await client.get(f"/api/admin/sittings/{sitting.id}/question-reports",
                            headers=auth(ptok))).json()[0]["id"]

    r = await client.post(f"/api/admin/question-reports/{rid}/resolve",
                          json={"resolution": "Đã kiểm tra, đề đúng"}, headers=auth(ptok))
    assert r.status_code == 200

    item = (await client.get(f"/api/admin/sittings/{sitting.id}/question-reports",
                             headers=auth(ptok))).json()[0]
    assert item["resolved_at"] is not None
    assert item["resolution"] == "Đã kiểm tra, đề đúng"
    assert item["resolved_by_name"]


async def test_report_shows_as_a_flag_on_the_monitor_row(client, factory, db):
    """Giám thị không có danh sách, nhưng phải thấy được là em này vừa báo lỗi."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q1", "correct": "A"}],
                                                 owner_id=admin.id)
    room = await factory.room(exam.id)
    gt, gtok = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    room.proctor_id = gt.id
    await db.commit()
    cand, ch, qs = await _running(client, factory, exam, sitting, ptok, "10.74.0.5")
    cand.room_id = room.id
    await db.commit()

    before = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions",
                               headers=auth(gtok))).json()[0]
    assert before["open_question_reports"] == 0

    await client.post("/api/exam/question-report",
                      json={"question_id": qs[0]["id"], "content": "Thiếu hình"}, headers=ch)
    after = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions",
                              headers=auth(gtok))).json()[0]
    assert after["open_question_reports"] == 1

    # Danh sách vẫn là việc của chủ tịch (giữ đúng phạm vi quyền AD-124).
    assert (await client.get(f"/api/admin/sittings/{sitting.id}/question-reports",
                             headers=auth(gtok))).status_code == 403


async def test_reports_are_owner_scoped(client, factory, db):
    """Chủ tịch khác không đọc được khiếu nại của kỳ thi không phải của mình."""
    admin, ptok = await factory.admin()
    other, otok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q1", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch, qs = await _running(client, factory, exam, sitting, ptok, "10.74.0.6")
    await client.post("/api/exam/question-report",
                      json={"question_id": qs[0]["id"], "content": "Sai đề"}, headers=ch)

    assert (await client.get(f"/api/admin/sittings/{sitting.id}/question-reports",
                             headers=auth(otok))).status_code == 404


async def test_report_needs_a_running_session(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q1", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch, qs = await _running(client, factory, exam, sitting, ptok, "10.74.0.7")
    await client.post("/api/exam/submit", headers=ch)

    r = await client.post("/api/exam/question-report",
                          json={"question_id": qs[0]["id"], "content": "Sau khi nộp"},
                          headers=ch)
    assert r.status_code == 409


async def test_report_survives_for_the_council_after_the_sitting_closes(client, factory, db):
    """Khiếu nại phải còn để hội đồng đọc lúc chấm — kể cả sau khi đề bị xoá."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q1", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch, qs = await _running(client, factory, exam, sitting, ptok, "10.74.0.8")
    await client.post("/api/exam/question-report",
                      json={"question_id": qs[0]["id"], "content": "Câu này hai đáp án đúng"},
                      headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/end?force=true", headers=auth(ptok))

    lst = (await client.get(f"/api/admin/sittings/{sitting.id}/question-reports",
                            headers=auth(ptok))).json()
    assert len(lst) == 1 and "hai đáp án đúng" in lst[0]["content"]

    rows = list(await db.scalars(select(QuestionReport).where(
        QuestionReport.sitting_id == sitting.id)))
    assert len(rows) == 1
