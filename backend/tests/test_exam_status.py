"""GET /api/exam/auth/status — is an exam open? (AD-61)

Gated on an ACTIVE kỳ thi (not on a buổi being open): the exam app shows the login
form as soon as an exam is open, otherwise a "no exam in progress" screen."""


async def test_status_open_when_an_exam_is_active(client, factory):
    exam, sitting, _ = await factory.active_exam([{"text": "q1", "correct": "A"}])
    r = await client.get("/api/exam/auth/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["open"] is True
    assert body["exam_name"]
    assert isinstance(body["allow_registration"], bool)


async def test_status_open_even_with_draft_sitting(client, factory):
    # An active exam whose buổi is still draft is enough to show the login screen.
    exam, sitting = await factory.empty_active_exam(owner_id=None)
    r = await client.get("/api/exam/auth/status")
    assert r.status_code == 200, r.text
    assert r.json()["open"] is True
