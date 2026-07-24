"""AD-110: gate 'Bắt đầu thi' theo tiến độ tải đề.

Máy thí sinh tải xong toàn bộ ảnh đề lúc CHỜ → ``POST /exam/preload-done`` đặt cờ
Redis theo phiên; ``GET /admin/sittings/{id}/sessions`` trả ``preloaded`` để chủ
tịch chỉ bắt đầu khi mọi máy sẵn đề (hết cảnh khúc đầu buổi thi ì vì tải nền).
"""

from tests.conftest import auth


def xff(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


async def test_preload_done_sets_flag_visible_to_admin(client, factory):
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, proc = await factory.admin()
    ip = xff("10.11.0.1")

    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)   # SP-2b: → READY

    # Chưa báo → preloaded=False.
    rows = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions", headers=auth(proc))).json()
    assert rows[0]["preloaded"] is False

    # Máy báo đã tải xong (idempotent — gọi 2 lần vẫn OK).
    assert (await client.post("/api/exam/preload-done", headers=ch)).status_code == 200
    assert (await client.post("/api/exam/preload-done", headers=ch)).status_code == 200

    rows = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions", headers=auth(proc))).json()
    assert rows[0]["preloaded"] is True
    assert rows[0]["status"] == "ready"


async def test_preload_done_ignored_while_waiting(client, factory, monkeypatch):
    """Phiên chưa READY (chưa xác nhận xong / chưa phát đề) → không đặt cờ."""
    from app.models.enums import SessionStatus
    from app.models import ExamSession
    from sqlalchemy import select
    from tests.conftest import AsyncSessionLocal

    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, proc = await factory.admin()
    ip = xff("10.11.0.2")
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)

    # Ép phiên về WAITING rồi báo tải xong → cờ KHÔNG được đặt.
    async with AsyncSessionLocal() as s:
        sess = await s.scalar(select(ExamSession).where(ExamSession.candidate_id == cand.id))
        sess.status = SessionStatus.WAITING.value
        await s.commit()
    assert (await client.post("/api/exam/preload-done", headers=ch)).status_code == 200
    rows = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions", headers=auth(proc))).json()
    assert rows[0]["preloaded"] is False
