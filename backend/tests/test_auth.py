"""Admin auth: password login + role separation (super_admin vs proctor)."""

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Admin
from app.models.enums import AdminRole
from tests.conftest import auth


async def test_password_login(client, factory):
    admin, _ = await factory.admin(role=AdminRole.SUPER_ADMIN.value, password="pw123456")
    r = await client.post("/api/admin/auth/login",
                          json={"username": admin.username, "password": "pw123456"})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


async def test_wrong_password_is_401(client, factory):
    admin, _ = await factory.admin(password="pw123456")
    r = await client.post("/api/admin/auth/login",
                          json={"username": admin.username, "password": "wrong"})
    assert r.status_code == 401


async def test_role_guard_proctor_vs_super(client, factory):
    _, super_tok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)
    _, proc_tok = await factory.admin(role=AdminRole.PROCTOR.value)

    # super_admin must NOT operate exams …
    r = await client.post("/api/admin/exams", json={"name": "TST_x", "duration_minutes": 30},
                          headers=auth(super_tok))
    assert r.status_code == 403
    # … but may list them and manage accounts.
    assert (await client.get("/api/admin/exams", headers=auth(super_tok))).status_code == 200
    assert (await client.get("/api/admin/admins", headers=auth(super_tok))).status_code == 200

    # proctor may operate but NOT manage accounts.
    assert (await client.get("/api/admin/admins", headers=auth(proc_tok))).status_code == 403
    assert (await client.get("/api/admin/exams", headers=auth(proc_tok))).status_code == 200
    # delete exam is super-only
    fake = "00000000-0000-0000-0000-000000000000"
    assert (await client.delete(f"/api/admin/exams/{fake}", headers=auth(proc_tok))).status_code == 403


async def test_self_change_password(client, factory):
    admin, tok = await factory.admin(role=AdminRole.PROCTOR.value, password="oldpw123")
    # Wrong current password → 400.
    r = await client.post("/api/admin/auth/change-password",
                          json={"old_password": "nope", "new_password": "brandnew1"},
                          headers=auth(tok))
    assert r.status_code == 400
    # Correct current password → changed; new password logs in, old does not.
    r = await client.post("/api/admin/auth/change-password",
                          json={"old_password": "oldpw123", "new_password": "brandnew1"},
                          headers=auth(tok))
    assert r.status_code == 200, r.text
    assert (await client.post("/api/admin/auth/login",
            json={"username": admin.username, "password": "oldpw123"})).status_code == 401
    assert (await client.post("/api/admin/auth/login",
            json={"username": admin.username, "password": "brandnew1"})).status_code == 200


async def test_exam_ownership_isolation(client, factory):
    """A proctor sees/opens only their own exams; another proctor's exam is
    hidden (list) and 404 (get). super_admin sees all."""
    p1, t1 = await factory.admin(role=AdminRole.PROCTOR.value)
    _, t2 = await factory.admin(role=AdminRole.PROCTOR.value)
    _, st = await factory.admin(role=AdminRole.SUPER_ADMIN.value)

    # A draft exam owned by p1 (draft avoids the global at-most-one-active rule,
    # which could already be taken by a real active exam in the dev DB).
    exam = await factory.owned_exam(p1.id)
    exam_id = str(exam.id)

    # p1 sees it; p2 does not; super does.
    assert any(e["id"] == exam_id for e in (await client.get("/api/admin/exams", headers=auth(t1))).json())
    assert not any(e["id"] == exam_id for e in (await client.get("/api/admin/exams", headers=auth(t2))).json())
    assert any(e["id"] == exam_id for e in (await client.get("/api/admin/exams", headers=auth(st))).json())

    # p2 cannot open or operate it (404 hides existence); p1 can.
    assert (await client.get(f"/api/admin/exams/{exam_id}", headers=auth(t2))).status_code == 404
    assert (await client.get(f"/api/admin/exams/{exam_id}", headers=auth(t1))).status_code == 200
    assert (await client.get(f"/api/admin/exams/{exam_id}/sittings", headers=auth(t2))).status_code == 404
    assert (await client.get(f"/api/admin/exams/{exam_id}/sittings", headers=auth(t1))).status_code == 200


async def test_candidate_crud_ownership_isolation(client, factory):
    """AD-55 I2: single-candidate CRUD is ownership-gated like list/import. A
    proctor cannot read/edit/delete a candidate of an exam they don't own (404
    hides existence); the owner and super_admin can."""
    p1, t1 = await factory.admin(role=AdminRole.PROCTOR.value)
    _, t2 = await factory.admin(role=AdminRole.PROCTOR.value)
    exam = await factory.owned_exam(p1.id)
    cand = await factory.candidate(exam.id)
    cid = str(cand.id)

    # Non-owner proctor: 404 on every single-candidate endpoint (hides existence).
    assert (await client.get(f"/api/admin/candidates/{cid}", headers=auth(t2))).status_code == 404
    assert (await client.patch(f"/api/admin/candidates/{cid}",
            json={"full_name": "Hacker"}, headers=auth(t2))).status_code == 404
    assert (await client.delete(f"/api/admin/candidates/{cid}", headers=auth(t2))).status_code == 404

    # Owner can read + edit.
    assert (await client.get(f"/api/admin/candidates/{cid}", headers=auth(t1))).status_code == 200
    assert (await client.patch(f"/api/admin/candidates/{cid}",
            json={"full_name": "Đã sửa"}, headers=auth(t1))).status_code == 200

    # AD-69: listing requires exam_id (no DB-wide list); owner-scoped when given.
    assert (await client.get("/api/admin/candidates", headers=auth(t1))).status_code == 400
    assert (await client.get(f"/api/admin/candidates?exam_id={exam.id}",
            headers=auth(t1))).status_code == 200
    assert (await client.get(f"/api/admin/candidates?exam_id={exam.id}",
            headers=auth(t2))).status_code == 404   # non-owner can't list it


async def test_super_can_reset_password(client, factory):
    _, super_tok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)
    target, _ = await factory.admin(role=AdminRole.PROCTOR.value, password="oldpw123")
    r = await client.post(f"/api/admin/admins/{target.id}/set-password",
                          json={"password": "newpw456"}, headers=auth(super_tok))
    assert r.status_code == 200
    # Old password rejected, new one works.
    assert (await client.post("/api/admin/auth/login",
            json={"username": target.username, "password": "oldpw123"})).status_code == 401
    assert (await client.post("/api/admin/auth/login",
            json={"username": target.username, "password": "newpw456"})).status_code == 200
    async with AsyncSessionLocal() as s:
        assert await s.scalar(select(Admin).where(Admin.id == target.id)) is not None


async def test_login_guard_escalating_lockout():
    """Admin login lockout GROWS: 1st = 60s, 2nd = 120s; cleared on success.
    (AD-46 — login_guard. The guard short-circuits when limiter.enabled is False,
    so the test flips it on around the assertions.)"""
    from app.core import login_guard
    from app.core.limiter import limiter
    from app.core.redis import redis_client

    ip = "203.0.113.77"  # documentation/test-only IP
    limiter.enabled = True
    try:
        await login_guard.clear(ip)
        # 9 wrong tries → no lockout yet.
        for _ in range(9):
            assert await login_guard.register_failure(ip) == 0
        # 10th → first lockout = 60s.
        assert await login_guard.register_failure(ip) == 60
        assert 55 <= await login_guard.seconds_locked(ip) <= 60
        # Simulate the lockout expiring, then another batch → escalates to 120s.
        await redis_client.delete(login_guard._k("until", ip))
        for _ in range(9):
            await login_guard.register_failure(ip)
        assert await login_guard.register_failure(ip) == 120
        # A successful login clears all state.
        await login_guard.clear(ip)
        assert await login_guard.seconds_locked(ip) == 0
    finally:
        await login_guard.clear(ip)
        limiter.enabled = False
