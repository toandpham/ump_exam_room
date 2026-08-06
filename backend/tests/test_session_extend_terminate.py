"""Điều hành từng thí sinh: cộng giờ riêng và đình chỉ thi (đợt 2).

Trước đây chỉ cộng giờ được cho CẢ BUỔI — một máy treo mười phút thì phải cộng giờ
cho cả phòng, ai cũng được thêm. Và không có đường nào dừng hẳn bài của một người bị
bắt gian lận: tạm dừng thì còn tiếp tục được, đăng xuất thì giữ nguyên phiên để họ
vào máy khác làm tiếp.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Answer, ExamSession
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
    return cand, ch


async def test_extend_one_candidate_only(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    await _running(client, factory, exam, sitting, ptok, "10.73.0.1")
    await _running(client, factory, exam, sitting, ptok, "10.73.0.2")

    rows = list(await db.scalars(select(ExamSession).where(ExamSession.sitting_id == sitting.id)
                                 .order_by(ExamSession.created_at)))
    lucky, other = rows
    before_lucky, before_other = lucky.end_time, other.end_time

    r = await client.post(f"/api/admin/sessions/{lucky.id}/extend",
                          json={"minutes": 15}, headers=auth(ptok))
    assert r.status_code == 200, r.text
    assert r.json()["minutes"] == 15

    await db.refresh(lucky)
    await db.refresh(other)
    assert lucky.end_time - before_lucky == timedelta(minutes=15)
    assert other.end_time == before_other, "chỉ người được chọn mới được cộng giờ"


async def test_extend_reopens_a_session_that_already_ran_out(client, factory, db):
    """Máy treo khiến thí sinh mất giờ — phải bù được cả khi đồng hồ đã về 0."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch = await _running(client, factory, exam, sitting, ptok, "10.73.0.3")
    s = await db.scalar(select(ExamSession).where(ExamSession.sitting_id == sitting.id))
    s.end_time = datetime.now(timezone.utc) - timedelta(minutes=2)
    await db.commit()

    # Hết giờ → không ghi được đáp án nữa.
    qid = (await client.get("/api/exam/questions", headers=ch)).json()["questions"][0]["id"]
    assert (await client.post("/api/exam/answer",
                              json={"question_id": qid, "selected_option": "A"},
                              headers=ch)).status_code == 409

    await client.post(f"/api/admin/sessions/{s.id}/extend", json={"minutes": 10},
                      headers=auth(ptok))
    assert (await client.post("/api/exam/answer",
                              json={"question_id": qid, "selected_option": "A"},
                              headers=ch)).status_code == 200


async def test_extend_rejects_bad_minutes_and_finished_session(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch = await _running(client, factory, exam, sitting, ptok, "10.73.0.4")
    s = await db.scalar(select(ExamSession).where(ExamSession.sitting_id == sitting.id))

    assert (await client.post(f"/api/admin/sessions/{s.id}/extend", json={"minutes": 0},
                              headers=auth(ptok))).status_code == 422
    assert (await client.post(f"/api/admin/sessions/{s.id}/extend", json={"minutes": 999},
                              headers=auth(ptok))).status_code == 422

    await client.post("/api/exam/submit", headers=ch)
    r = await client.post(f"/api/admin/sessions/{s.id}/extend", json={"minutes": 5},
                          headers=auth(ptok))
    assert r.status_code == 409, "bài đã nộp thì không cộng giờ được nữa"


async def test_terminate_scores_what_was_done_and_locks_the_candidate_out(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(
        [{"text": "Q1", "correct": "A"}, {"text": "Q2", "correct": "B"}], owner_id=admin.id)
    _, ch = await _running(client, factory, exam, sitting, ptok, "10.73.0.5")
    qs = (await client.get("/api/exam/questions", headers=ch)).json()["questions"]
    await client.post("/api/exam/answer",
                      json={"question_id": qs[0]["id"], "selected_option": "A"}, headers=ch)
    s = await db.scalar(select(ExamSession).where(ExamSession.sitting_id == sitting.id))

    r = await client.post(f"/api/admin/sessions/{s.id}/terminate",
                          json={"reason": "Mang tài liệu vào phòng thi"}, headers=auth(ptok))
    assert r.status_code == 200, r.text

    await db.refresh(s)
    assert s.status == "terminated"
    assert s.terminated_reason == "Mang tài liệu vào phòng thi"
    assert s.submitted_at is not None
    assert s.total_correct == 1, "vẫn chấm với những gì đã làm"
    assert s.results_hash, "phải niêm phong như mọi bài khác"

    # Không làm bài tiếp được.
    assert (await client.post("/api/exam/answer",
                              json={"question_id": qs[1]["id"], "selected_option": "B"},
                              headers=ch)).status_code == 409
    assert (await client.post("/api/exam/submit", headers=ch)).status_code == 409


async def test_terminated_candidate_can_still_see_their_result(client, factory, db):
    """Bỏ sót trạng thái mới ở một chỗ là thí sinh kẹt màn 'chưa có kết quả'."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch = await _running(client, factory, exam, sitting, ptok, "10.73.0.6")
    s = await db.scalar(select(ExamSession).where(ExamSession.sitting_id == sitting.id))
    await client.post(f"/api/admin/sessions/{s.id}/terminate",
                      json={"reason": "Vi phạm quy chế"}, headers=auth(ptok))

    st = (await client.get("/api/exam/state", headers=ch)).json()
    assert st["status"] == "terminated"
    r = await client.get("/api/exam/result", headers=ch)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "terminated"


async def test_terminated_session_is_checked_by_integrity(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch = await _running(client, factory, exam, sitting, ptok, "10.73.0.7")
    s = await db.scalar(select(ExamSession).where(ExamSession.sitting_id == sitting.id))
    await client.post(f"/api/admin/sessions/{s.id}/terminate",
                      json={"reason": "Trao đổi bài"}, headers=auth(ptok))

    r = (await client.get(f"/api/admin/sittings/{sitting.id}/integrity",
                          headers=auth(ptok))).json()
    assert r["checked"] == 1 and r["ok"] == 1, "bài đình chỉ vẫn phải được kiểm niêm phong"


async def test_terminated_session_appears_in_the_report(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    cand, ch = await _running(client, factory, exam, sitting, ptok, "10.73.0.8")
    s = await db.scalar(select(ExamSession).where(ExamSession.sitting_id == sitting.id))
    await client.post(f"/api/admin/sessions/{s.id}/terminate",
                      json={"reason": "Dùng điện thoại"}, headers=auth(ptok))

    # Dựng báo cáo bằng MỘT phiên CSDL mới: phiên của test đang giữ giao dịch mở
    # từ trước lúc endpoint ghi, nên đọc lại trong đó vẫn ra bản cũ.
    from app.database import AsyncSessionLocal
    from app.models import Sitting
    from app.services.report_service import build_report
    async with AsyncSessionLocal() as fresh:
        data = await build_report(fresh, await fresh.get(Sitting, sitting.id), exam.name)
    rows = [r for r in data["rows"] if r["cccd"] == cand.cccd]
    assert rows, "thí sinh bị đình chỉ không được biến mất khỏi báo cáo"
    assert rows[0]["status"] == "terminated"


async def test_terminate_requires_a_reason_and_a_running_session(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch = await _running(client, factory, exam, sitting, ptok, "10.73.0.9")
    s = await db.scalar(select(ExamSession).where(ExamSession.sitting_id == sitting.id))

    assert (await client.post(f"/api/admin/sessions/{s.id}/terminate", json={"reason": "  "},
                              headers=auth(ptok))).status_code == 422
    await client.post(f"/api/admin/sessions/{s.id}/terminate",
                      json={"reason": "Vi phạm quy chế"}, headers=auth(ptok))
    r = await client.post(f"/api/admin/sessions/{s.id}/terminate",
                          json={"reason": "Lần hai"}, headers=auth(ptok))
    assert r.status_code == 409, "không đình chỉ được bài đã chốt"


async def test_giam_thi_cannot_extend_or_terminate(client, factory, db):
    """Giữ đúng phạm vi quyền giám thị (AD-124): chỉ Tạm dừng / Tiếp tục."""
    from app.models.enums import AdminRole
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    room = await factory.room(exam.id)
    gt, gtok = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    room.proctor_id = gt.id
    await db.commit()
    await _running(client, factory, exam, sitting, ptok, "10.73.0.10")
    s = await db.scalar(select(ExamSession).where(ExamSession.sitting_id == sitting.id))

    assert (await client.post(f"/api/admin/sessions/{s.id}/extend", json={"minutes": 5},
                              headers=auth(gtok))).status_code == 403
    assert (await client.post(f"/api/admin/sessions/{s.id}/terminate",
                              json={"reason": "abc"},
                              headers=auth(gtok))).status_code == 403


async def test_terminate_keeps_the_answers_already_saved(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    _, ch = await _running(client, factory, exam, sitting, ptok, "10.73.0.11")
    qs = (await client.get("/api/exam/questions", headers=ch)).json()["questions"]
    await client.post("/api/exam/answer",
                      json={"question_id": qs[0]["id"], "selected_option": "A"}, headers=ch)
    s = await db.scalar(select(ExamSession).where(ExamSession.sitting_id == sitting.id))
    await client.post(f"/api/admin/sessions/{s.id}/terminate",
                      json={"reason": "Quay cóp"}, headers=auth(ptok))

    kept = list(await db.scalars(select(Answer).where(Answer.session_id == s.id)))
    assert len(kept) == 1 and kept[0].selected_option == "A"
