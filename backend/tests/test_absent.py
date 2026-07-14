"""Vắng thi: giám thị/chủ tịch đánh dấu thí sinh vắng theo buổi (AD-68)."""
import pytest
from app.models.enums import AdminRole, SessionStatus
from app.models import ExamSession
from sqlalchemy import select
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


async def test_mark_absent_creates_session_for_not_logged_in(client, factory, db):
    admin, tok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=admin.id)
    cand = await factory.candidate(exam.id)
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/candidates/{cand.id}/absent",
        json={"absent": True}, headers=auth(tok))
    assert r.status_code == 200 and r.json()["absent"] is True
    row = (await db.execute(select(ExamSession).where(
        ExamSession.sitting_id == sitting.id, ExamSession.candidate_id == cand.id))).scalar_one()
    assert row.status == SessionStatus.ABSENT.value


async def test_unmark_absent_removes_session(client, factory, db):
    admin, tok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=admin.id)
    cand = await factory.candidate(exam.id)
    await client.post(f"/api/admin/sittings/{sitting.id}/candidates/{cand.id}/absent",
                      json={"absent": True}, headers=auth(tok))
    r = await client.post(f"/api/admin/sittings/{sitting.id}/candidates/{cand.id}/absent",
                          json={"absent": False}, headers=auth(tok))
    assert r.status_code == 200 and r.json()["absent"] is False
    rows = (await db.execute(select(ExamSession).where(
        ExamSession.sitting_id == sitting.id, ExamSession.candidate_id == cand.id))).scalars().all()
    assert rows == []


async def test_roster_absent_total_and_logged_in_excludes_absent(client, factory):
    admin, tok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=admin.id)
    cand = await factory.candidate(exam.id)
    await client.post(f"/api/admin/sittings/{sitting.id}/candidates/{cand.id}/absent",
                      json={"absent": True}, headers=auth(tok))
    roster = (await client.get(f"/api/admin/sittings/{sitting.id}/roster", headers=auth(tok))).json()
    assert roster["absent_total"] == 1
    assert roster["logged_in"] == 0  # absent không tính là đã đăng nhập


async def test_giam_thi_cannot_mark_absent_other_room(client, factory):
    chair, ctok = await factory.admin(role=AdminRole.PROCTOR.value)
    gt, gtok = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=chair.id)
    room = await factory.room(exam.id, proctor_id=gt.id, name="P1")
    other = await factory.room(exam.id, name="P2")
    cand = await factory.candidate(exam.id, room_id=other.id)
    r = await client.post(f"/api/admin/sittings/{sitting.id}/candidates/{cand.id}/absent",
                          json={"absent": True}, headers=auth(gtok))
    assert r.status_code == 404


async def test_cannot_mark_absent_in_progress(client, factory, db):
    """409 when candidate already has an in_progress session (data-integrity guard)."""
    admin, tok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=admin.id)
    cand = await factory.candidate(exam.id)
    db.add(ExamSession(
        candidate_id=cand.id, sitting_id=sitting.id, exam_id=exam.id,
        status=SessionStatus.IN_PROGRESS.value,
    ))
    await db.commit()
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/candidates/{cand.id}/absent",
        json={"absent": True}, headers=auth(tok))
    assert r.status_code == 409
    # Session must still be in_progress — endpoint must not have mutated it.
    row = (await db.execute(select(ExamSession).where(
        ExamSession.sitting_id == sitting.id,
        ExamSession.candidate_id == cand.id,
    ))).scalar_one()
    assert row.status == SessionStatus.IN_PROGRESS.value


@pytest.mark.parametrize("logged_in_status", [
    SessionStatus.WAITING.value,
    SessionStatus.READY.value,
    SessionStatus.SUBMITTED.value,
])
async def test_cannot_mark_absent_when_logged_in(client, factory, db, logged_in_status):
    """AD-69: a candidate who has logged in (any live session — chờ/sẵn sàng/đã nộp)
    is PRESENT, so marking absent is rejected (409) and the session is untouched."""
    admin, tok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=admin.id)
    cand = await factory.candidate(exam.id)
    db.add(ExamSession(
        candidate_id=cand.id, sitting_id=sitting.id, exam_id=exam.id,
        status=logged_in_status,
    ))
    await db.commit()
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/candidates/{cand.id}/absent",
        json={"absent": True}, headers=auth(tok))
    assert r.status_code == 409
    row = (await db.execute(select(ExamSession).where(
        ExamSession.sitting_id == sitting.id,
        ExamSession.candidate_id == cand.id,
    ))).scalar_one()
    assert row.status == logged_in_status   # unchanged


async def test_unmark_does_not_delete_real_session(client, factory, db):
    """absent=False on a non-absent session must leave the real session intact."""
    admin, tok = await factory.admin(role=AdminRole.PROCTOR.value)
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}], owner_id=admin.id)
    cand = await factory.candidate(exam.id)
    db.add(ExamSession(
        candidate_id=cand.id, sitting_id=sitting.id, exam_id=exam.id,
        status=SessionStatus.IN_PROGRESS.value,
    ))
    await db.commit()
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/candidates/{cand.id}/absent",
        json={"absent": False}, headers=auth(tok))
    assert r.status_code == 200
    assert r.json()["absent"] is False
    # The in_progress row must still exist — only ABSENT rows are removed on unmark.
    rows = (await db.execute(select(ExamSession).where(
        ExamSession.sitting_id == sitting.id,
        ExamSession.candidate_id == cand.id,
    ))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == SessionStatus.IN_PROGRESS.value
