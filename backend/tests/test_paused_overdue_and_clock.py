"""Phiên tạm dừng quá giờ phải NHÌN THẤY được, và đồng hồ chung phải nói đúng
(đợt 1, lỗ AD-121 #2 và #3).

#2 — Vòng quét tự nộp cố ý bỏ qua phiên đang tạm dừng (đúng: không nộp thay người
đang bị dừng). Nhưng nếu không ai bấm Tiếp tục thì phiên nằm đó mãi mà bảng giám
sát không hiện gì bất thường. Ta không tự nộp — ta làm cho nó nổi lên.

#3 — Đồng hồ chung lấy min(end_time) của mọi phiên đang làm, hiển thị dưới nhãn
"thời gian thi còn lại". Sai hai chỗ: phiên đang tạm dừng có đồng hồ đóng băng mà
vẫn được tính vào min; và khi một người được cộng giờ riêng thì min là người kết
thúc SỚM NHẤT, khiến chủ tịch tưởng cả phòng sắp hết giờ.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import ExamSession
from tests.conftest import auth, fast_forward_start


async def _join(client, factory, exam, sitting, ptok, ip):
    cand = await factory.candidate(exam.id)
    xff = {"X-Forwarded-For": ip}
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                             headers=xff)).json()["token"]
    ch = {**auth(tok), **xff}
    await client.post("/api/exam/auth/confirm", headers=ch)
    return cand


async def test_session_flags_paused_past_end_time(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    await _join(client, factory, exam, sitting, ptok, "10.72.0.1")
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)
    sid = (await db.scalar(select(ExamSession).where(
        ExamSession.sitting_id == sitting.id))).id

    async def row():
        r = await client.get(f"/api/admin/sittings/{sitting.id}/sessions", headers=auth(ptok))
        return r.json()[0]

    # Tạm dừng khi CÒN giờ → bình thường, không phải cảnh báo.
    await client.post(f"/api/admin/sessions/{sid}/pause", headers=auth(ptok))
    r = await row()
    assert r["paused"] is True
    assert r["overdue_paused"] is False

    # Tạm dừng mà đồng hồ đã trôi qua → treo, phải nổi lên cho chủ tịch thấy.
    s = await db.get(ExamSession, sid)
    s.end_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.commit()
    assert (await row())["overdue_paused"] is True


async def test_clock_ignores_paused_and_reports_the_last_finisher(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}],
                                                 owner_id=admin.id)
    await _join(client, factory, exam, sitting, ptok, "10.72.0.2")
    await _join(client, factory, exam, sitting, ptok, "10.72.0.3")
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)

    sessions = list(await db.scalars(
        select(ExamSession).where(ExamSession.sitting_id == sitting.id)
        .order_by(ExamSession.created_at)))
    assert len(sessions) == 2
    now = datetime.now(timezone.utc)
    early, late = sessions
    early.end_time = now + timedelta(minutes=10)
    late.end_time = now + timedelta(minutes=40)     # người này được cộng giờ
    await db.commit()

    r = (await client.get(f"/api/admin/sittings/{sitting.id}/roster",
                          headers=auth(ptok))).json()
    assert r["earliest_end_time"] is not None
    assert r["latest_end_time"] is not None
    assert r["earliest_end_time"] < r["latest_end_time"], \
        "phải phân biệt được người xong sớm nhất với người xong muộn nhất"

    # Tạm dừng người sắp hết giờ: đồng hồ của họ đóng băng nên KHÔNG được kéo
    # đồng hồ chung xuống theo.
    await client.post(f"/api/admin/sessions/{early.id}/pause", headers=auth(ptok))
    r2 = (await client.get(f"/api/admin/sittings/{sitting.id}/roster",
                           headers=auth(ptok))).json()
    assert r2["earliest_end_time"] == r2["latest_end_time"], \
        "chỉ còn một người đang chạy đồng hồ"
    assert r2["earliest_end_time"] > r["earliest_end_time"], \
        "đồng hồ chung không được lấy theo người đang tạm dừng"
