"""Candidate flow: single-device lock + full answer/submit/scoring (AD-47).

Control endpoints are keyed by SITTING (buổi thi); pause/resume are per-candidate.
"""

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Exam, ExamEvent, ExamSession, Sitting
from app.models.enums import SessionStatus
from tests.conftest import auth, fast_forward_start


def xff(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


async def test_single_device_lock(client, factory):
    exam, sitting, _ = await factory.active_exam([{"text": "1+1?", "correct": "B"}])
    cand = await factory.candidate(exam.id)

    # Device 1 logs in and is live.
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=xff("10.0.0.1"))
    assert r.status_code == 200, r.text
    tok1 = r.json()["token"]
    assert tok1
    assert (await client.get("/api/exam/state", headers={**auth(tok1), **xff("10.0.0.1")})).status_code == 200

    # Device 2 (different IP) without force → must confirm takeover, no token issued.
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=xff("10.0.0.2"))
    assert r.status_code == 200
    assert r.json()["requires_takeover"] is True
    assert r.json()["token"] is None

    # Device 2 forces takeover → gets a token.
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd, "force": True},
                          headers=xff("10.0.0.2"))
    tok2 = r.json()["token"]
    assert tok2

    # Device 1 is now superseded; device 2 works.
    r = await client.get("/api/exam/state", headers={**auth(tok1), **xff("10.0.0.1")})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "device_superseded"
    assert (await client.get("/api/exam/state", headers={**auth(tok2), **xff("10.0.0.2")})).status_code == 200


async def test_finished_candidate_not_kicked_when_superseded(client, factory):
    """A candidate who already finished (submitted/timeout) keeps their result
    screen even if another device claims the lock — they're not bounced to login.
    Anti-multi-device only matters while a session could still be in progress."""
    from app.core import device_lock
    exam, sitting, _ = await factory.active_exam([{"text": "q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    ip = xff("10.9.0.1")
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)

    # Mark the session finished, then let a DIFFERENT device claim the lock.
    async with AsyncSessionLocal() as s:
        sess = await s.scalar(select(ExamSession).where(ExamSession.candidate_id == cand.id))
        sess.status = SessionStatus.SUBMITTED.value
        await s.commit()
    await device_lock.claim(cand.id, "other-device-jti", "10.9.0.2", "devB")

    # Old device still reads its result — NOT 409.
    r = await client.get("/api/exam/state", headers=ch)
    assert r.status_code == 200, r.text
    assert r.json()["status"] in ("submitted", "timeout")


async def test_in_progress_candidate_still_kicked_when_superseded(client, factory):
    """Counterpart: while a session is in progress, supersede DOES kick (anti-cheat)."""
    from app.core import device_lock
    exam, sitting, _ = await factory.active_exam([{"text": "q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    ip = xff("10.9.1.1")
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)
    async with AsyncSessionLocal() as s:
        sess = await s.scalar(select(ExamSession).where(ExamSession.candidate_id == cand.id))
        sess.status = SessionStatus.IN_PROGRESS.value
        await s.commit()
    await device_lock.claim(cand.id, "other-device-jti", "10.9.1.2", "devB")
    r = await client.get("/api/exam/state", headers=ch)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "device_superseded"


async def test_registration_can_be_disabled(client, factory):
    """allow_registration=False on the exam → on-the-spot register is rejected;
    active-exams advertises the flag so the client can hide the button."""
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}])
    # Flip the flag off directly (factory.active_exam defaults true).
    async with AsyncSessionLocal() as s:
        e = await s.get(Exam, exam.id)
        e.allow_registration = False
        await s.commit()

    actives = (await client.get("/api/exam/auth/active-exams")).json()
    mine = [a for a in actives if a["id"] == str(exam.id)]
    assert mine and mine[0]["allow_registration"] is False

    r = await client.post("/api/exam/auth/register", json={
        "cccd": "079900000123", "full_name": "Tự Đăng Ký", "birth_date": "2000-01-01",
        "unit": "X", "category": "Đối tượng 1", "attempt_number": 1, "exam_id": str(exam.id),
    }, headers={"X-Forwarded-For": "10.6.0.1", "X-Device-Id": "DEV-R"})
    assert r.status_code == 403, r.text


async def test_self_registered_counted_in_roster(client, factory):
    """A self-registered candidate is flagged + counted separately from the
    imported roster."""
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}])
    _, proc = await factory.admin()

    r = await client.post("/api/exam/auth/register", json={
        "cccd": "079900000456", "full_name": "Tự Đăng Ký", "birth_date": "2000-01-01",
        "unit": "X", "category": "Đối tượng 1", "attempt_number": 1, "exam_id": str(exam.id),
    }, headers={"X-Forwarded-For": "10.6.1.1", "X-Device-Id": "DEV-S"})
    assert r.status_code == 201, r.text

    roster = (await client.get(f"/api/admin/sittings/{sitting.id}/roster", headers=auth(proc))).json()
    assert roster["self_registered_total"] >= 1
    assert any(c["self_registered"] for c in roster["not_logged_in"])

    # Clean up the self-registered candidate (factory teardown only knows its own).
    async with AsyncSessionLocal() as s:
        from app.models import Candidate
        from sqlalchemy import delete as _del
        await s.execute(_del(Candidate).where(Candidate.cccd == "079900000456"))
        await s.commit()


async def test_proctor_logout_lets_candidate_switch_machine(client, factory):
    """Proctor 'Đăng xuất' kicks the candidate's current device; the candidate
    re-logs in on another machine and resumes (answers kept)."""
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, proc = await factory.admin()
    ip1 = {**xff("10.5.0.1"), **dev("DEV-OLD")}

    tok1 = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip1)).json()["token"]
    await client.post("/api/exam/auth/confirm", headers={**auth(tok1), **ip1})
    # SP-2b: confirm đã đặt READY — không cần distribute để lấy session_id.
    sid = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions", headers=auth(proc))).json()[0]["session_id"]

    # Proctor logs the candidate out → old device is kicked.
    assert (await client.post(f"/api/admin/sessions/{sid}/logout", headers=auth(proc))).status_code == 200
    r = await client.get("/api/exam/state", headers={**auth(tok1), **ip1})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "device_superseded"

    # Candidate logs in on a NEW machine with no takeover prompt, resumes session.
    ip2 = {**xff("10.5.0.2"), **dev("DEV-NEW")}
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip2)
    assert r.status_code == 200 and r.json()["token"]
    assert r.json().get("requires_takeover") is not True


async def test_answer_submit_scoring(client, factory):
    exam, sitting, payload = await factory.active_exam([
        {"text": "Câu 1", "correct": "A"},
        {"text": "Câu 2", "correct": "B"},
    ])
    cand = await factory.candidate(exam.id)
    _, proctor_tok = await factory.admin()
    q1, q2 = payload["questions"][0]["id"], payload["questions"][1]["id"]
    ip = xff("10.1.0.1")

    # Candidate logs in + confirms info → session created (ready — SP-2b).
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    assert (await client.post("/api/exam/auth/confirm", headers=ch)).status_code == 200

    # Proctor starts (distribute skip — confirm already sets READY).
    assert (await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(proctor_tok))).json()["started"] == 1
    # SP-2c: kéo started_at về quá khứ để test không phải chờ đếm ngược 20s.
    await fast_forward_start(sitting.id)

    # Candidate sees 2 questions (correct option hidden).
    r = await client.get("/api/exam/questions", headers=ch)
    assert r.status_code == 200
    qs = r.json()["questions"]
    assert len(qs) == 2
    assert all("correct_option" not in q for q in qs)

    # Answer q1 correctly (A), q2 wrongly (C).
    assert (await client.post("/api/exam/answer", json={"question_id": q1, "selected_option": "A"}, headers=ch)).status_code == 200
    assert (await client.post("/api/exam/answer", json={"question_id": q2, "selected_option": "C"}, headers=ch)).status_code == 200

    # Submit → 1/2 correct.
    r = await client.post("/api/exam/submit", headers=ch)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["total_correct"] == 1
    assert body["answered"] == 2


async def test_score_survives_redis_payload_expiry(client, factory):
    """Regression (AD-55 C1): scoring must NOT silently produce 0 when the Redis
    đề payload TTL has expired before submit (late open / cộng giờ / admit trễ đẩy
    end_time vượt TTL). ``correct_map_for_sitting`` reads ``report_snapshot`` first,
    so the result stays correct even with the Redis key gone."""
    from app.core.redis import redis_client
    from app.services import session_service

    exam, sitting, payload = await factory.active_exam([
        {"text": "Câu 1", "correct": "A"},
        {"text": "Câu 2", "correct": "B"},
    ])
    cand = await factory.candidate(exam.id)
    _, proctor_tok = await factory.admin()
    q1, q2 = payload["questions"][0]["id"], payload["questions"][1]["id"]
    ip = xff("10.9.0.1")

    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(proctor_tok))
    await fast_forward_start(sitting.id)  # SP-2c: bỏ qua đếm ngược để trả lời ngay
    await client.post("/api/exam/answer", json={"question_id": q1, "selected_option": "A"}, headers=ch)
    await client.post("/api/exam/answer", json={"question_id": q2, "selected_option": "C"}, headers=ch)

    # Simulate the payload TTL elapsing before scoring — the old code path scored 0.
    await redis_client.delete(session_service.payload_key(sitting.id))

    body = (await client.post("/api/exam/submit", headers=ch)).json()
    assert body["total"] == 2
    assert body["total_correct"] == 1   # would be 0 if scoring depended on Redis only


async def test_login_rate_limit_is_per_device_not_shared_ip(client):
    """AD-69: login rate-limit keyed by device-id, not IP. Candidates behind one
    NAT gateway IP (AD-35) must NOT share a bucket — one machine hammering gets
    429 while a different machine on the SAME IP still gets through."""
    from app.core.limiter import limiter
    limiter.enabled = True
    try:
        ip = xff("10.7.7.7")   # same gateway IP for everyone (NAT)
        got429 = False
        for _ in range(13):    # limit is 10/2min → must trip within 13
            r = await client.post("/api/exam/auth/login",
                                  json={"cccd": "079000000000"},
                                  headers={**ip, **dev("DEV-HAMMER")})
            if r.status_code == 429:
                got429 = True
                break
        assert got429, "device DEV-HAMMER should have been rate-limited"
        # Different machine, SAME IP → its own bucket → not throttled.
        r = await client.post("/api/exam/auth/login",
                              json={"cccd": "079000000000"},
                              headers={**ip, **dev("DEV-FRESH")})
        assert r.status_code != 429, "a different device on the same IP must not be throttled"
    finally:
        limiter.enabled = False
        try:
            limiter.reset()
        except Exception:  # noqa: BLE001
            pass


async def test_late_candidate_auto_admitted_on_confirm(client, factory):
    """Thí sinh đi trễ: đăng nhập + xác nhận SAU khi buổi đã 'Bắt đầu thi' → tự
    vào thi NGAY (in_progress) với đồng hồ riêng full thời lượng (AD-47), KHỎI chờ
    giám thị bấm 'Duyệt vào thi'. Xác nhận TRƯỚC khi bắt đầu thì vẫn 'ready'."""
    exam, sitting, payload = await factory.active_exam([{"text": "Q", "correct": "A"}])
    ontime = await factory.candidate(exam.id)
    late = await factory.candidate(exam.id)
    _, proctor_tok = await factory.admin()

    # On-time candidate logs in + confirms BEFORE start → 'ready' (chưa bắt đầu).
    ch0 = {**auth((await client.post("/api/exam/auth/login", json={"cccd": ontime.cccd}, headers=xff("10.4.0.0"))).json()["token"]), **xff("10.4.0.0")}
    await client.post("/api/exam/auth/confirm", headers=ch0)
    assert (await client.get("/api/exam/state", headers=ch0)).json()["status"] == "ready"
    # Chủ tịch bấm "Bắt đầu thi" → cohort vào in_progress.
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(proctor_tok))
    assert (await client.get("/api/exam/state", headers=ch0)).json()["end_time"]

    # Late candidate logs in + confirms AFTER start → auto in_progress, đồng hồ riêng.
    ch = {**auth((await client.post("/api/exam/auth/login", json={"cccd": late.cccd}, headers=xff("10.4.0.1"))).json()["token"]), **xff("10.4.0.1")}
    await client.post("/api/exam/auth/confirm", headers=ch)
    state = (await client.get("/api/exam/state", headers=ch)).json()
    assert state["status"] == "in_progress"            # KHÔNG kẹt ở 'ready'
    assert state["end_time"] is not None               # đồng hồ riêng đã được đặt
    assert state["time_remaining_seconds"] and state["time_remaining_seconds"] > 0

    # Vào đề + trả lời + nộp ngay, không cần thao tác admin.
    q = payload["questions"][0]["id"]
    assert (await client.post("/api/exam/answer", json={"question_id": q, "selected_option": "A"}, headers=ch)).status_code == 200
    assert (await client.post("/api/exam/submit", headers=ch)).json()["total_correct"] == 1


async def test_manual_admit_ready_session(client, factory):
    """Nút 'Duyệt vào thi' (fallback): giám thị duyệt MỘT phiên 'ready' vào thi ngay
    với đồng hồ riêng, không cần bấm 'Bắt đầu thi' cho cả cohort."""
    exam, sitting, payload = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, proctor_tok = await factory.admin()
    ip = xff("10.4.0.3")
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)   # ready (chưa bắt đầu)
    sid = (await client.get("/api/exam/state", headers=ch)).json()["session_id"]

    r = await client.post(f"/api/admin/sessions/{sid}/admit", headers=auth(proctor_tok))
    assert r.status_code == 200 and r.json()["started"] == 1, r.text
    state = (await client.get("/api/exam/state", headers=ch)).json()
    assert state["status"] == "in_progress"
    assert state["time_remaining_seconds"] and state["time_remaining_seconds"] > 0


async def test_admit_rejects_non_waiting(client, factory):
    """Admit only applies to waiting/ready sessions — a submitted one is 409."""
    exam, sitting, payload = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, proctor_tok = await factory.admin()
    ip = xff("10.4.0.2")
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(proctor_tok))
    sid = (await client.get("/api/exam/state", headers=ch)).json()["session_id"]
    await client.post("/api/exam/submit", headers=ch)
    r = await client.post(f"/api/admin/sessions/{sid}/admit", headers=auth(proctor_tok))
    assert r.status_code == 409, r.text


async def test_session_online_presence(client, factory):
    """Thoát trình duyệt (revoke device lock) KHÔNG đổi trạng thái phiên thi —
    session vẫn in_progress để thí sinh có thể đăng nhập lại làm tiếp (AD-38).
    Chỉ báo online/offline đã gỡ ở AD-69; test chỉ còn kiểm tra status bất biến."""
    from app.core import device_lock

    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, proctor_tok = await factory.admin()
    ip = xff("10.5.0.1")
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(proctor_tok))

    sess = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions", headers=auth(proctor_tok))).json()
    assert sess[0]["status"] == "in_progress"

    # Simulate the browser closing: heartbeat goes stale.
    await device_lock.revoke(cand.id)
    sess = (await client.get(f"/api/admin/sittings/{sitting.id}/sessions", headers=auth(proctor_tok))).json()
    assert sess[0]["status"] == "in_progress"  # status unchanged — resumable


async def test_time_up_locks_answers_until_extend(client, factory):
    """When a candidate's OWN clock passes end_time they're LOCKED (answers 409);
    the proctor's Cộng giờ moves end_time forward and reopens answering. (The
    background sweep — not running under the test transport — is what later
    auto-submits; here we verify only the write lock + extend, AD-47.)"""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select as _select
    from app.models import ExamSession

    exam, sitting, payload = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, ptok = await factory.admin()
    ip = xff("10.6.0.1")
    q = payload["questions"][0]["id"]
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)  # SP-2c: bỏ qua đếm ngược để trả lời ngay

    # While time remains → answering works.
    assert (await client.post("/api/exam/answer", json={"question_id": q, "selected_option": "A"}, headers=ch)).status_code == 200

    # Simulate this candidate's clock running out.
    async with AsyncSessionLocal() as s:
        sess = (await s.execute(_select(ExamSession).where(ExamSession.candidate_id == cand.id, ExamSession.sitting_id == sitting.id))).scalars().first()
        sess.end_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        await s.commit()

    # Locked: answering rejected.
    r = await client.post("/api/exam/answer", json={"question_id": q, "selected_option": "B"}, headers=ch)
    assert r.status_code == 409 and "hết giờ" in r.json()["detail"].lower()

    # Proctor Cộng giờ → end_time forward → reopens answering.
    r = await client.post(f"/api/admin/sittings/{sitting.id}/extend", json={"minutes": 10}, headers=auth(ptok))
    assert r.status_code == 200 and r.json()["extended"] == 1, r.text
    assert (await client.post("/api/exam/answer", json={"question_id": q, "selected_option": "A"}, headers=ch)).status_code == 200


async def test_report_chosen_answers_in_original_order(client, factory):
    """AD-68: 'rows[].answers' ghi chữ cái THẬT thí sinh chọn theo thứ tự đề GỐC.
    q1→A (đúng), q2→D (sai), q3→không trả lời."""
    from app.services.report_service import build_report

    exam, sitting, payload = await factory.active_exam([
        {"text": "Câu 1", "correct": "A"},
        {"text": "Câu 2", "correct": "B"},
        {"text": "Câu 3", "correct": "C"},
    ])
    cand = await factory.candidate(exam.id)
    _, proctor_tok = await factory.admin()
    q1, q2 = payload["questions"][0]["id"], payload["questions"][1]["id"]
    ip = xff("10.9.0.1")
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(proctor_tok))
    await fast_forward_start(sitting.id)  # SP-2c: bỏ qua đếm ngược để trả lời ngay
    # q1 đúng (A), q2 sai (D), q3 bỏ trống.
    await client.post("/api/exam/answer", json={"question_id": q1, "selected_option": "A"}, headers=ch)
    await client.post("/api/exam/answer", json={"question_id": q2, "selected_option": "D"}, headers=ch)
    await client.post("/api/exam/submit", headers=ch)

    async with AsyncSessionLocal() as s:
        report = await build_report(s, await s.get(Sitting, sitting.id))

    assert "rows" in report and "questions" in report
    row = report["rows"][0]
    # Cột 'answers' = chữ cái đã chọn theo thứ tự câu GỐC
    assert row["answers"] == ["A", "D", ""], f"answers={row['answers']}"
    # Đáp án đúng nằm ở report["questions"], không lộ trong row
    correct = [q["correct_option"] for q in report["questions"]]
    assert correct == ["A", "B", "C"]
    # Điểm: 1 câu đúng / 3 câu
    assert row["total_correct"] == 1
    # Không có trường "answers_summary" hay "chosen_summary" nữa (đã gỡ AD-68)
    assert "answers_summary" not in row
    assert "chosen_summary" not in row
    assert "overview" not in report


async def test_resume_after_device_change(client, factory):
    """Mid-exam machine crash / switch: candidate logs in on a new device and
    resumes the SAME session — answers preserved, timer intact, scoring correct."""
    exam, sitting, payload = await factory.active_exam([
        {"text": "Câu 1", "correct": "A"},
        {"text": "Câu 2", "correct": "B"},
    ], duration=45)
    cand = await factory.candidate(exam.id)
    _, proctor_tok = await factory.admin()
    q1, q2 = payload["questions"][0]["id"], payload["questions"][1]["id"]

    # Device 1: login + confirm (→ ready, SP-2b) + (proctor) start + answer q1.
    ip1 = xff("10.2.0.1")
    tok1 = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip1)).json()["token"]
    ch1 = {**auth(tok1), **ip1}
    await client.post("/api/exam/auth/confirm", headers=ch1)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(proctor_tok))
    await fast_forward_start(sitting.id)  # SP-2c: bỏ qua đếm ngược để trả lời ngay
    await client.post("/api/exam/answer", json={"question_id": q1, "selected_option": "A"}, headers=ch1)

    # --- machine dies, candidate moves to a new computer (different IP) ---
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=xff("10.2.0.2"))
    # The old device is still "live" (just heartbeat'd) so a takeover confirm is asked.
    assert r.json()["requires_takeover"] is True
    r = await client.post("/api/exam/auth/login",
                          json={"cccd": cand.cccd, "force": True}, headers=xff("10.2.0.2"))
    tok2 = r.json()["token"]
    assert tok2
    # Re-login does NOT bounce them to confirm — session is still in_progress.
    assert r.json()["session_status"] == "in_progress"

    ch2 = {**auth(tok2), **xff("10.2.0.2")}
    # Questions + previously-saved answer come back; timer still counting down.
    r = await client.get("/api/exam/questions", headers=ch2)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "in_progress"
    assert body["answers"].get(q1) == "A"          # q1 preserved across the device change
    assert body["time_remaining_seconds"] is not None and body["time_remaining_seconds"] > 0

    # Finish q2 on the new machine, submit → both counted.
    await client.post("/api/exam/answer", json={"question_id": q2, "selected_option": "B"}, headers=ch2)
    r = await client.post("/api/exam/submit", headers=ch2)
    assert r.status_code == 200, r.text
    assert r.json()["total_correct"] == 2


def dev(device: str) -> dict:
    return {"X-Device-Id": device}


async def _same_machine_event(cccd: str):
    async with AsyncSessionLocal() as s:
        return await s.scalar(
            select(ExamEvent).where(
                ExamEvent.event_type == "same_machine_login",
                ExamEvent.cccd_attempted == cccd,
            )
        )


async def test_same_device_second_account_blocked(client, factory):
    """One browser (device id) already has a live session for candidate A →
    logging in as candidate B from that same device is BLOCKED (409)."""
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}])
    a = await factory.candidate(exam.id)
    b = await factory.candidate(exam.id)
    h = {**xff("10.7.7.7"), **dev("DEVICE-ONE")}

    # A logs in + confirms on this device → A now has a waiting session here.
    tok_a = (await client.post("/api/exam/auth/login", json={"cccd": a.cccd}, headers=h)).json()["token"]
    assert (await client.post("/api/exam/auth/confirm", headers={**auth(tok_a), **h})).status_code == 200

    # B tries to log in on the SAME device → blocked.
    r = await client.post("/api/exam/auth/login", json={"cccd": b.cccd}, headers=h)
    assert r.status_code == 409, r.text
    assert "1 tài khoản" in r.json()["detail"]

    # A re-logging in on the same device is fine (resume, same candidate).
    assert (await client.post("/api/exam/auth/login", json={"cccd": a.cccd}, headers=h)).status_code == 200

    # B on a DIFFERENT device works (different machine = legitimate).
    assert (await client.post("/api/exam/auth/login", json={"cccd": b.cccd},
            headers={**xff("10.7.7.8"), **dev("DEVICE-TWO")})).status_code == 200


async def test_same_ip_different_device_no_warn(client, factory):
    """Same IP but different device ids (shared LAN / NAT) → NO warning."""
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}])
    a = await factory.candidate(exam.id)
    b = await factory.candidate(exam.id)
    ip = xff("10.8.8.8")

    tok_a = (await client.post("/api/exam/auth/login", json={"cccd": a.cccd},
             headers={**ip, **dev("DEVICE-A")})).json()["token"]
    await client.post("/api/exam/auth/confirm", headers={**auth(tok_a), **ip, **dev("DEVICE-A")})

    r = await client.post("/api/exam/auth/login", json={"cccd": b.cccd},
                          headers={**ip, **dev("DEVICE-B")})
    assert r.status_code == 200 and r.json()["token"]

    assert await _same_machine_event(b.cccd) is None


async def test_device_switch_by_device_id_same_ip(client, factory):
    """The bug: behind LAN NAT every client shares the gateway IP, so the old
    IP-based switch detection never fired. A different browser device-id with
    the SAME ip must still be detected as a device switch (takeover prompt)."""
    exam, sitting, _ = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    ip = xff("192.168.147.1")  # the shared OrbStack/Docker gateway

    # Device A logs in + confirms → becomes the live device.
    tok_a = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
             headers={**ip, **dev("DEV-A")})).json()["token"]
    await client.post("/api/exam/auth/confirm", headers={**auth(tok_a), **ip, **dev("DEV-A")})

    # Same candidate, SAME ip, DIFFERENT device → must ask to take over.
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                          headers={**ip, **dev("DEV-B")})
    assert r.json().get("requires_takeover") is True, r.text

    # Forcing through claims the new device + resumes.
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd, "force": True},
                          headers={**ip, **dev("DEV-B")})
    assert r.json()["token"]

    # Reconnect from the SAME (new) device is silent — no takeover nag.
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                          headers={**ip, **dev("DEV-B")})
    assert not r.json().get("requires_takeover")
    assert r.json()["token"]


async def test_pause_blocks_answers_then_resume(client, factory):
    """Per-candidate pause (AD-47): pausing ONE session freezes that candidate —
    /state shows paused and POST /answer is rejected; resume reopens it."""
    exam, sitting, payload = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, ptok = await factory.admin()
    q = payload["questions"][0]["id"]
    ip = xff("10.10.0.1")
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)  # SP-2c: bỏ qua đếm ngược để trả lời ngay
    sid = (await client.get("/api/exam/state", headers=ch)).json()["session_id"]
    assert (await client.post("/api/exam/answer", json={"question_id": q, "selected_option": "A"}, headers=ch)).status_code == 200

    assert (await client.post(f"/api/admin/sessions/{sid}/pause", headers=auth(ptok))).status_code == 200
    assert (await client.get("/api/exam/state", headers=ch)).json()["paused"] is True
    r = await client.post("/api/exam/answer", json={"question_id": q, "selected_option": "B"}, headers=ch)
    assert r.status_code == 409 and "tạm dừng" in r.json()["detail"].lower()

    assert (await client.post(f"/api/admin/sessions/{sid}/resume", headers=auth(ptok))).status_code == 200
    assert (await client.get("/api/exam/state", headers=ch)).json()["paused"] is False
    assert (await client.post("/api/exam/answer", json={"question_id": q, "selected_option": "A"}, headers=ch)).status_code == 200


async def test_auto_submit_sweep_per_candidate(client, factory):
    """The background sweep (AD-47) auto-submits a candidate when THEIR OWN clock
    hits 0, sealing the result; a paused candidate past their frozen clock is
    skipped (their timer isn't really running)."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select as _select
    from app.core.redis import redis_client
    from app.models import ExamSession
    from app.services.session_service import auto_submit_expired

    exam, sitting, payload = await factory.active_exam([{"text": "Q", "correct": "A"}])
    a = await factory.candidate(exam.id)
    b = await factory.candidate(exam.id)
    _, ptok = await factory.admin()
    q = payload["questions"][0]["id"]

    async def join(cand, ip):
        tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=xff(ip))).json()["token"]
        ch = {**auth(tok), **xff(ip)}
        await client.post("/api/exam/auth/confirm", headers=ch)
        return ch

    cha = await join(a, "10.12.0.1")
    chb = await join(b, "10.12.0.2")
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)  # SP-2c: bỏ qua đếm ngược để trả lời ngay
    await client.post("/api/exam/answer", json={"question_id": q, "selected_option": "A"}, headers=cha)

    # Pause candidate B, then push BOTH clocks into the past.
    sid_b = (await client.get("/api/exam/state", headers=chb)).json()["session_id"]
    assert (await client.post(f"/api/admin/sessions/{sid_b}/pause", headers=auth(ptok))).status_code == 200
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with AsyncSessionLocal() as s:
        for sess in (await s.execute(_select(ExamSession).where(ExamSession.sitting_id == sitting.id))).scalars():
            sess.end_time = past
        await s.commit()

    n = await auto_submit_expired(redis_client)
    assert n == 1, n   # only A (B is paused → skipped)

    # A auto-submitted (timeout) + sealed; result shows the one correct answer.
    assert (await client.get("/api/exam/state", headers=cha)).json()["status"] == "timeout"
    assert (await client.get("/api/exam/result", headers=cha)).json()["total_correct"] == 1
    r = (await client.get(f"/api/admin/sittings/{sitting.id}/integrity", headers=auth(ptok))).json()
    assert r["ok"] == 1 and r["mismatched"] == []

    # B is still in_progress (paused — its clock isn't running).
    async with AsyncSessionLocal() as s:
        bsess = await s.get(ExamSession, sid_b)
        assert bsess.status == "in_progress"


async def test_pause_all_resume_all(client, factory):
    """Chủ tịch tạm dừng / tiếp tục CẢ BUỔI cho mọi thí sinh đang làm bài (AD-48)."""
    exam, sitting, payload = await factory.active_exam([{"text": "Q", "correct": "A"}])
    a = await factory.candidate(exam.id)
    b = await factory.candidate(exam.id)
    _, ptok = await factory.admin()

    async def join(cand, ip):
        tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=xff(ip))).json()["token"]
        ch = {**auth(tok), **xff(ip)}
        await client.post("/api/exam/auth/confirm", headers=ch)
        return ch

    cha = await join(a, "10.13.0.1")
    chb = await join(b, "10.13.0.2")
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))

    r = await client.post(f"/api/admin/sittings/{sitting.id}/pause-all", headers=auth(ptok))
    assert r.status_code == 200 and r.json()["paused"] == 2, r.text
    assert (await client.get("/api/exam/state", headers=cha)).json()["paused"] is True
    assert (await client.get("/api/exam/state", headers=chb)).json()["paused"] is True

    r = await client.post(f"/api/admin/sittings/{sitting.id}/resume-all", headers=auth(ptok))
    assert r.status_code == 200 and r.json()["resumed"] == 2, r.text
    assert (await client.get("/api/exam/state", headers=cha)).json()["paused"] is False


async def test_integrity_detects_tampered_score(client, factory):
    """A finalised session is sealed (results_hash); editing its score in the DB
    makes /integrity report a mismatch (tamper-evident — AD-22)."""
    from app.models import ExamSession

    exam, sitting, payload = await factory.active_exam([{"text": "Q", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    _, ptok = await factory.admin()
    q = payload["questions"][0]["id"]
    ip = xff("10.11.0.1")
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)  # SP-2c: bỏ qua đếm ngược để trả lời ngay
    await client.post("/api/exam/answer", json={"question_id": q, "selected_option": "A"}, headers=ch)
    await client.post("/api/exam/submit", headers=ch)

    r = (await client.get(f"/api/admin/sittings/{sitting.id}/integrity", headers=auth(ptok))).json()
    assert r["checked"] == 1 and r["ok"] == 1 and r["mismatched"] == []

    # Tamper with the stored score → the re-hash no longer matches the seal.
    async with AsyncSessionLocal() as s:
        sess = (await s.execute(select(ExamSession).where(ExamSession.sitting_id == sitting.id))).scalars().first()
        sess.score = 10
        sess.total_correct = 999
        await s.commit()
    r = (await client.get(f"/api/admin/sittings/{sitting.id}/integrity", headers=auth(ptok))).json()
    assert r["ok"] == 0 and len(r["mismatched"]) == 1


async def test_create_exam_blocked_when_one_active(client, factory):
    """At-most-one-active invariant: creating an exam while another is active
    is rejected with 409."""
    admin, ptok = await factory.admin()
    await factory.empty_active_exam(admin.id)
    r = await client.post("/api/admin/exams",
                          json={"name": "TST_should_fail", "duration_minutes": 30},
                          headers=auth(ptok))
    assert r.status_code == 409


async def test_result_readable_after_sitting_closed(client, factory):
    """A candidate force-submitted by "Đóng buổi" must still be able to read
    their result: /exam/result falls back to the latest session when no sitting
    is active anymore (found live in the 2026-06-10 E2E audit)."""
    exam, sitting, payload = await factory.active_exam([
        {"text": "Câu 1", "correct": "A"},
    ])
    cand = await factory.candidate(exam.id)
    _, ptok = await factory.admin()
    q1 = payload["questions"][0]["id"]
    ip = xff("10.9.0.1")

    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    assert (await client.post("/api/exam/auth/confirm", headers=ch)).status_code == 200
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)  # SP-2c: bỏ qua đếm ngược để trả lời ngay
    assert (await client.post("/api/exam/answer", json={"question_id": q1, "selected_option": "A"}, headers=ch)).status_code == 200

    # Chairman closes the sitting while the candidate is still in_progress:
    # force-submit + score + purge. No sitting is active afterwards.
    r = await client.post(f"/api/admin/sittings/{sitting.id}/end", headers=auth(ptok))
    assert r.status_code == 200, r.text

    r = await client.get("/api/exam/result", headers=ch)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_correct"] == 1
    assert body["total"] == 1


async def test_assign_exam_locked_only_while_running(client, factory):
    """assign-exam uses the same lock semantics as import (AD-47): blocked only
    while a bài thi is running, not for the exam's whole 'active' life."""
    exam, sitting, payload = await factory.active_exam([
        {"text": "Câu 1", "correct": "A"},
    ])
    cand = await factory.candidate(exam.id)
    _, ptok = await factory.admin()
    ip = xff("10.9.0.2")

    # No running session yet → assignment is allowed (used to 423 forever).
    r = await client.post("/api/admin/candidates/assign-exam",
                          json={"exam_id": str(exam.id), "candidate_ids": [str(cand.id)]},
                          headers=auth(ptok))
    assert r.status_code == 200, r.text

    # Start the bài thi → now it IS locked.
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=ip)).json()["token"]
    ch = {**auth(tok), **ip}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    r = await client.post("/api/admin/candidates/assign-exam",
                          json={"exam_id": str(exam.id), "candidate_ids": [str(cand.id)]},
                          headers=auth(ptok))
    assert r.status_code == 423


async def test_roster_shows_room_for_not_logged_in(client, factory):
    """The monitor roster lists the assigned room even for candidates who have
    not logged in yet (the E2E audit found them showing '—')."""
    exam, sitting, _ = await factory.active_exam([
        {"text": "Câu 1", "correct": "A"},
    ])
    _, ptok = await factory.admin()
    room = await factory.room(exam.id, name="Phòng kiểm thử")
    await factory.candidate(exam.id, room_id=room.id)

    r = await client.get(f"/api/admin/sittings/{sitting.id}/roster", headers=auth(ptok))
    assert r.status_code == 200
    pending = r.json()["not_logged_in"]
    assert any(c.get("room_name") == "Phòng kiểm thử" for c in pending)
