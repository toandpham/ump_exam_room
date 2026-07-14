"""SEB hard-enforcement on candidate endpoints (AD-56/AD-59). The global suite
runs with seb_enforce=False (conftest); this file flips it on around each test.

Default enforcement is PRESENCE mode (universal .seb, IP-independent): any request
carrying a SEB header passes, a plain browser is blocked. Strict mode (a pasted
SEB_CONFIG_KEY) additionally binds each request to that exact .seb."""
import pytest

from app.config import settings
from app.core import seb_config as sc


@pytest.fixture
def seb_on():
    settings.seb_enforce = True
    try:
        yield
    finally:
        settings.seb_enforce = False


@pytest.fixture
def seb_strict():
    """Enable strict per-.seb binding via a pasted Config Key."""
    settings.seb_enforce = True
    settings.seb_config_key = "deadbeefcafe"
    sc.current_config_key.cache_clear()
    try:
        yield settings.seb_config_key
    finally:
        settings.seb_enforce = False
        settings.seb_config_key = ""
        sc.current_config_key.cache_clear()


def _strict_headers(path: str, ck: str, host="exam-server.local", proto="http"):
    url = f"{proto}://{host}{path}"
    h = sc.request_hash(url, ck)
    return {"X-Forwarded-Proto": proto, "X-Forwarded-Host": host,
            sc.CONFIG_KEY_HEADER: h}


async def test_candidate_login_blocked_without_seb(client, factory, seb_on):
    exam, sitting, _ = await factory.active_exam([{"text": "Câu 1", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                          headers={"X-Forwarded-For": "10.0.0.1"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "seb_required"


async def test_candidate_login_allowed_in_presence_mode(client, factory, seb_on):
    """Presence mode: the mere SEB header (any value) lets the request through —
    this is what makes one universal .seb work on any IP."""
    exam, sitting, _ = await factory.active_exam([{"text": "Câu 1", "correct": "A"}])
    cand = await factory.candidate(exam.id)
    headers = {"X-Forwarded-For": "10.0.0.1", sc.CONFIG_KEY_HEADER: "anything"}
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["token"]


async def test_strict_mode_requires_matching_config_key(client, factory, seb_strict):
    exam, sitting, _ = await factory.active_exam([{"text": "Câu 1", "correct": "A"}])
    cand = await factory.candidate(exam.id)

    # Wrong/garbage hash is rejected even though a SEB header is present.
    bad = {"X-Forwarded-Proto": "http", "X-Forwarded-Host": "exam-server.local",
           sc.CONFIG_KEY_HEADER: "garbage"}
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=bad)
    assert r.status_code == 403

    # Correct hash bound to (URL + Config Key) passes.
    good = _strict_headers("/api/exam/auth/login", seb_strict)
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd}, headers=good)
    assert r.status_code == 200, r.text
    assert r.json()["token"]
