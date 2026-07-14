"""SP-2c: start đặt mốc start_at tương lai (đếm ngược) + chặn nộp trước giờ."""
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models import ExamSession
from app.models.enums import AdminRole, SessionStatus
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


async def _confirm(client, factory, exam):
    cand = await factory.candidate(exam.id)
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd})).json()["token"]
    ch = auth(tok)
    await client.post("/api/exam/auth/confirm", headers=ch)
    return cand, ch


async def test_start_sets_future_start_at(client, factory):
    admin, ptok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q1", "correct": "A"}], owner_id=admin.id)
    cand, ch = await _confirm(client, factory, exam)  # → READY
    before = datetime.now(timezone.utc)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    async with AsyncSessionLocal() as db:
        s = await db.scalar(select(ExamSession).where(ExamSession.candidate_id == cand.id))
    # started_at ở TƯƠNG LAI (đếm ngược lead 30s), end_time = started_at + thời lượng.
    assert s.status == SessionStatus.IN_PROGRESS.value
    assert before + timedelta(seconds=20) < s.started_at < before + timedelta(seconds=40)
    assert abs((s.end_time - s.started_at).total_seconds() - sitting.duration_minutes * 60) < 2


async def test_answer_blocked_before_start_then_allowed(client, factory):
    admin, ptok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q1", "correct": "A"}], owner_id=admin.id)
    cand, ch = await _confirm(client, factory, exam)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    qs = (await client.get("/api/exam/questions", headers=ch)).json()["questions"]
    qid = qs[0]["id"]
    # Đang đếm ngược (started_at tương lai) → nộp bị chặn.
    r = await client.post("/api/exam/answer", json={"question_id": qid, "selected_option": "A"}, headers=ch)
    assert r.status_code == 409
    # Giả lập đã tới giờ: kéo started_at về quá khứ.
    async with AsyncSessionLocal() as db:
        await db.execute(update(ExamSession)
                         .where(ExamSession.candidate_id == cand.id)
                         .values(started_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    r2 = await client.post("/api/exam/answer", json={"question_id": qid, "selected_option": "A"}, headers=ch)
    assert r2.status_code == 200, r2.text
