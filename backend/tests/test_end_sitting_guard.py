"""Đóng buổi không được cắt bài người còn giờ (đợt 1, lỗ AD-121 #1).

"Đóng buổi" ép nộp MỌI phiên đang làm mà không nhìn ai còn giờ. Bấm sớm là cắt bài
giữa chừng và không có cảnh báo nào — trước đây chỉ chống đỡ bằng quy trình ("chờ
giám thị báo phòng trống"), tức là dựa vào con người không bấm nhầm.

Cơ chế đúng không phải là CẤM đóng (chủ tịch phải đóng được trong mọi tình huống:
máy treo, thí sinh bỏ về) mà là BẮT NHÌN THẤY HẬU QUẢ rồi mới cho làm.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import ExamSession
from tests.conftest import auth, fast_forward_start


async def _running_candidate(client, factory, exam, sitting, ptok, ip="10.71.0.1"):
    """Một thí sinh đã vào thi, đồng hồ đang chạy."""
    cand = await factory.candidate(exam.id)
    xff = {"X-Forwarded-For": ip}
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                             headers=xff)).json()["token"]
    ch = {**auth(tok), **xff}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)
    return cand, ch


async def _set_end_time(db, sitting_id, when):
    for s in await db.scalars(select(ExamSession).where(ExamSession.sitting_id == sitting_id)):
        s.end_time = when
    await db.commit()


async def test_end_refuses_while_candidates_still_have_time(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    await _running_candidate(client, factory, exam, sitting, ptok)

    r = await client.post(f"/api/admin/sittings/{sitting.id}/end", headers=auth(ptok))
    assert r.status_code == 409, "còn người đang làm bài mà vẫn đóng buổi được"
    assert "1" in r.json()["detail"], "thông báo phải nêu rõ SỐ người sắp bị cắt bài"

    # Không được đụng vào bài của họ.
    await db.commit()   # bỏ ảnh chụp cũ của phiên test
    s = await db.scalar(select(ExamSession).where(ExamSession.sitting_id == sitting.id))
    assert s.status == "in_progress"
    assert s.submitted_at is None


async def test_end_refuses_while_a_candidate_is_paused(client, factory, db):
    """Người đang tạm dừng cũng phải được tính — họ chưa hết giờ, chỉ đang bị dừng."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    await _running_candidate(client, factory, exam, sitting, ptok, ip="10.71.0.2")
    # Hết giờ nhưng ĐANG tạm dừng → vòng quét tự nộp bỏ qua họ vĩnh viễn.
    await _set_end_time(db, sitting.id, datetime.now(timezone.utc) - timedelta(minutes=1))
    sid = (await db.scalar(select(ExamSession).where(
        ExamSession.sitting_id == sitting.id))).id
    await client.post(f"/api/admin/sessions/{sid}/pause", headers=auth(ptok))

    r = await client.post(f"/api/admin/sittings/{sitting.id}/end", headers=auth(ptok))
    assert r.status_code == 409
    assert "tạm dừng" in r.json()["detail"].lower()


async def test_end_force_closes_anyway(client, factory, db):
    """Chủ tịch vẫn phải đóng được khi thật sự cần (máy treo, phòng đã về)."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    await _running_candidate(client, factory, exam, sitting, ptok, ip="10.71.0.3")

    r = await client.post(f"/api/admin/sittings/{sitting.id}/end?force=true",
                          headers=auth(ptok))
    assert r.status_code == 200
    assert r.json()["submitted"] == 1


async def test_end_allows_when_everyone_is_out_of_time(client, factory, db):
    """Hết giờ hết rồi thì đóng thẳng, không bắt xác nhận thừa."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    await _running_candidate(client, factory, exam, sitting, ptok, ip="10.71.0.4")
    await _set_end_time(db, sitting.id, datetime.now(timezone.utc) - timedelta(minutes=5))

    r = await client.post(f"/api/admin/sittings/{sitting.id}/end", headers=auth(ptok))
    assert r.status_code == 200, "không còn ai đang làm bài thì không cần xác nhận"


async def test_end_allows_when_nobody_started(client, factory):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    r = await client.post(f"/api/admin/sittings/{sitting.id}/end", headers=auth(ptok))
    assert r.status_code == 200
