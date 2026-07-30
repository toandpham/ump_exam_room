"""R4 — chấm theo LÔ: một bản ghi lỗi không được chặn cả phòng.

Trước bản vá, cả hai đường chốt bài (vòng quét tự-nộp và "Đóng buổi") chấm TOÀN BỘ
phiên trong MỘT giao dịch duy nhất. 500 thí sinh ≈ 1.500 câu lệnh, một lần ghi: bất
kỳ dòng nào lỗi là rollback tất cả → KHÔNG AI được nộp, và vòng lặp 5 giây lặp lại
đúng lỗi đó mãi mãi. Tệ hơn, "Đóng buổi" dùng cùng khuôn nên bấm cũng gãy y hệt →
không còn nút nào trong giao diện chốt được buổi thi.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import ExamSession, Sitting
from app.models.enums import SessionStatus, SittingStatus
from tests.conftest import auth, fast_forward_start


def xff(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


async def _three_candidates_mid_exam(client, factory):
    """3 thí sinh đang làm bài trong cùng một buổi; trả về (sitting, ptok, [session_id])."""
    exam, sitting, payload = await factory.active_exam([{"text": "Q", "correct": "A"}])
    _, ptok = await factory.admin()
    q = payload["questions"][0]["id"]

    sids = []
    for i in range(3):
        cand = await factory.candidate(exam.id)
        ip = f"10.44.0.{i + 1}"
        tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                                 headers=xff(ip))).json()["token"]
        ch = {**auth(tok), **xff(ip)}
        await client.post("/api/exam/auth/confirm", headers=ch)
        sids.append((ch, q))

    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)
    out = []
    for ch, q in sids:
        await client.post("/api/exam/answer", json={"question_id": q, "selected_option": "A"},
                          headers=ch)
        out.append((await client.get("/api/exam/state", headers=ch)).json()["session_id"])
    return sitting, ptok, out


async def _statuses(sitting_id) -> dict[str, str]:
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(ExamSession).where(ExamSession.sitting_id == sitting_id))).scalars()
        return {str(r.id): r.status for r in rows}


async def test_auto_submit_isolates_one_bad_session(client, factory, monkeypatch):
    """Vòng quét: một phiên chấm lỗi → HAI phiên còn lại vẫn được nộp và niêm phong."""
    import app.services.session_jobs as jobs
    from app.core.redis import redis_client

    sitting, _ptok, sids = await _three_candidates_mid_exam(client, factory)
    bad = sids[1]

    # Đẩy đồng hồ của cả ba về quá khứ → vòng quét phải xử lý cả ba.
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with AsyncSessionLocal() as s:
        for sess in (await s.execute(
                select(ExamSession).where(ExamSession.sitting_id == sitting.id))).scalars():
            sess.end_time = past
        await s.commit()

    real_score = jobs.score_session

    async def flaky(db, session, correct_map):
        if str(session.id) == bad:
            raise RuntimeError("bản ghi hỏng — mô phỏng lỗi chấm 1 phiên")
        await real_score(db, session, correct_map)

    monkeypatch.setattr(jobs, "score_session", flaky)
    # Lô nhỏ để test đi qua nhiều lô mà không phải dựng 60 thí sinh.
    monkeypatch.setattr(jobs, "SCORE_BATCH", 2)

    n = await jobs.auto_submit_expired(redis_client)

    assert n == 2, f"phải nộp được 2 phiên lành, nhận {n}"
    st = await _statuses(sitting.id)
    assert st[bad] == SessionStatus.IN_PROGRESS.value          # phiên lỗi bị bỏ lại
    good = [v for k, v in st.items() if k != bad]
    assert good == [SessionStatus.TIMEOUT.value] * 2, st       # hai phiên kia đã nộp


async def test_end_sitting_isolates_one_bad_session(client, factory, monkeypatch):
    """Đóng buổi: một phiên chấm lỗi → các phiên kia vẫn nộp và BUỔI VẪN ĐÓNG được
    (trước đây một dòng lỗi là cả nút Đóng buổi cũng gãy)."""
    from app.services import session_service

    sitting, ptok, sids = await _three_candidates_mid_exam(client, factory)
    bad = sids[0]

    real_score = session_service.score_session

    async def flaky(db, session, correct_map):
        if str(session.id) == bad:
            raise RuntimeError("bản ghi hỏng — mô phỏng lỗi chấm 1 phiên")
        await real_score(db, session, correct_map)

    monkeypatch.setattr(session_service, "score_session", flaky)

    r = await client.post(f"/api/admin/sittings/{sitting.id}/end", headers=auth(ptok))
    assert r.status_code == 200, r.text

    st = await _statuses(sitting.id)
    good = [v for k, v in st.items() if k != bad]
    assert good == [SessionStatus.SUBMITTED.value] * 2, st
    async with AsyncSessionLocal() as s:
        assert (await s.get(Sitting, sitting.id)).status == SittingStatus.CLOSED.value
