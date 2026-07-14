"""Giấy phép server AD-74 — key Ed25519, hết hạn, chống vặn đồng hồ, middleware.

Key test ký bằng cặp khoá SINH TRONG TEST (khoá bí mật thật nằm ngoài repo);
PUBLIC_KEY_HEX được monkeypatch tương ứng. Các test API ghi dòng license id=1
trong DB đều save/restore để không đè giấy phép thật trên máy dev.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import license as lic
from app.database import AsyncSessionLocal
from app.models import SystemLicense
from app.models.enums import AdminRole
from app.services import license_service
from tests.conftest import auth, real_current_state

_PRIV = Ed25519PrivateKey.generate()
_PUB_HEX = _PRIV.public_key().public_bytes_raw().hex()


def make_key(days: float = 90, issued_to: str = "TST Đơn vị", iat: int | None = None) -> str:
    now = int(time.time()) if iat is None else iat
    payload = {"id": "tst00001", "to": issued_to, "iat": now, "exp": now + int(days * 86400)}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = _PRIV.sign(raw)

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    return f"EXAM-{b64(raw)}.{b64(sig)}"


@pytest.fixture(autouse=True)
def _test_pubkey(monkeypatch):
    monkeypatch.setattr(lic, "PUBLIC_KEY_HEX", _PUB_HEX)
    license_service.invalidate_cache()
    yield
    license_service.invalidate_cache()


@pytest_asyncio.fixture
async def preserve_license_row():
    """Test ghi dòng license id=1 phải trả lại nguyên trạng (DB dev dùng chung)."""
    async with AsyncSessionLocal() as db:
        row = await db.get(SystemLicense, 1)
        saved = (row.installed_at, row.key, row.activated_at, row.max_seen_at) if row else None
    yield
    async with AsyncSessionLocal() as db:
        row = await db.get(SystemLicense, 1)
        if saved is None:
            if row is not None:
                await db.delete(row)
        elif row is None:
            db.add(SystemLicense(id=1, installed_at=saved[0], key=saved[1],
                                 activated_at=saved[2], max_seen_at=saved[3]))
        else:
            row.installed_at, row.key, row.activated_at, row.max_seen_at = saved
        await db.commit()
    license_service.invalidate_cache()


# --- unit: parse / evaluate --------------------------------------------------

def test_parse_key_roundtrip():
    payload = lic.parse_key(make_key(days=90, issued_to="Trường X"))
    assert payload.issued_to == "Trường X"
    assert payload.expires_at > datetime.now(timezone.utc) + timedelta(days=89)


def test_parse_key_rejects_tampered_payload():
    key = make_key()
    body, _, sig = key[len("EXAM-"):].partition(".")
    # Sửa 1 ký tự payload (đổi hạn) — chữ ký phải vỡ.
    tampered = "EXAM-" + body[:-2] + ("AA" if body[-2:] != "AA" else "BB") + "." + sig
    with pytest.raises(lic.LicenseError):
        lic.parse_key(tampered)


def test_parse_key_rejects_garbage():
    for bad in ("", "EXAM-", "EXAM-abc", "hello", "EXAM-aGk.aGk"):
        with pytest.raises(lic.LicenseError):
            lic.parse_key(bad)


def test_evaluate_states():
    now = datetime.now(timezone.utc)
    # evaluate(key, installed_at, max_seen_at, ...) — AD-81.
    assert lic.evaluate(None, None, None).status == "missing"
    assert lic.evaluate("EXAM-rác.rác", None, None).status == "missing"
    assert lic.evaluate(make_key(days=90), None, None).status == "valid"
    expired = make_key(days=1, iat=int(time.time()) - 2 * 86400)
    assert lic.evaluate(expired, None, None).status == "expired"
    # Đồng hồ lùi quá 24h so với mốc lớn nhất từng thấy → khoá.
    st = lic.evaluate(make_key(days=90), None, now + timedelta(days=3))
    assert st.status == "clock_tampered"
    # Lùi trong dung sai (chỉnh NTP) thì không oan.
    assert lic.evaluate(make_key(days=90), None, now + timedelta(hours=1)).status == "valid"


def test_evaluate_trial_from_install():
    now = datetime.now(timezone.utc)
    # Vừa cài (không key) → dùng thử, còn ~90 ngày.
    st = lic.evaluate(None, now, None, now=now)
    assert st.status == "trial" and st.ok is True
    assert 88 <= (st.days_left or 0) <= 90
    # Cài đã quá 90 ngày, không key → hết hạn dùng thử.
    old = now - timedelta(days=91)
    assert lic.evaluate(None, old, None, now=now).status == "expired"
    # Có key gia hạn còn hạn → 'valid' ghi đè dùng thử (kể cả khi trial đã hết).
    st2 = lic.evaluate(make_key(days=90), old, None, now=now)
    assert st2.status == "valid" and st2.issued_to == "TST Đơn vị"


# --- API set/get -------------------------------------------------------------

@pytest.mark.asyncio
async def test_license_api_set_and_get(client, factory, preserve_license_row):
    _, super_token = await factory.admin(role=AdminRole.SUPER_ADMIN.value)
    _, proctor_token = await factory.admin(role=AdminRole.PROCTOR.value)

    # proctor không được POST
    r = await client.post("/api/admin/license", json={"key": make_key()},
                          headers=auth(proctor_token))
    assert r.status_code == 403

    # super nhập key sai → 400
    r = await client.post("/api/admin/license", json={"key": "EXAM-xxxx.yyyy"},
                          headers=auth(super_token))
    assert r.status_code == 400

    # super nhập key hết hạn → 400
    r = await client.post("/api/admin/license",
                          json={"key": make_key(days=1, iat=int(time.time()) - 2 * 86400)},
                          headers=auth(super_token))
    assert r.status_code == 400

    # key đúng → valid; mọi admin GET thấy trạng thái
    r = await client.post("/api/admin/license", json={"key": make_key(days=90)},
                          headers=auth(super_token))
    assert r.status_code == 200 and r.json()["status"] == "valid"
    r = await client.get("/api/admin/license", headers=auth(proctor_token))
    body = r.json()
    assert body["status"] == "valid" and body["issued_to"] == "TST Đơn vị"
    assert body["days_left"] >= 89 and body["warn"] is False

    # key sắp hết hạn (≤14 ngày) → warn=true
    r = await client.post("/api/admin/license", json={"key": make_key(days=5)},
                          headers=auth(super_token))
    assert r.status_code == 200 and r.json()["warn"] is True


# --- middleware --------------------------------------------------------------

@pytest.mark.asyncio
async def test_middleware_blocks_api_when_expired(client, factory, monkeypatch):
    async def _expired():
        return lic.LicenseState("expired", None)

    monkeypatch.setattr(license_service, "current_state", _expired)

    # API thường (kể cả thí sinh /status) → 403 license_expired
    r = await client.get("/api/exam/auth/status")
    assert r.status_code == 403 and r.json()["code"] == "license_expired"
    r = await client.get("/api/admin/exams")
    assert r.status_code == 403 and r.json()["code"] == "license_expired"

    # Skip-list: login + /me + license endpoints vẫn hoạt động
    _, super_token = await factory.admin(role=AdminRole.SUPER_ADMIN.value)
    r = await client.get("/api/admin/auth/me", headers=auth(super_token))
    assert r.status_code == 200
    r = await client.get("/api/admin/license", headers=auth(super_token))
    assert r.status_code == 200
    r = await client.get("/api/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_middleware_missing_vs_valid(client, monkeypatch, preserve_license_row):
    # Dùng bản current_state THẬT (đọc DB): xoá dòng license → missing → 403.
    monkeypatch.setattr(license_service, "current_state", real_current_state)
    async with AsyncSessionLocal() as db:
        row = await db.get(SystemLicense, 1)
        if row is not None:
            await db.delete(row)
            await db.commit()
    license_service.invalidate_cache()
    r = await client.get("/api/exam/auth/status")
    assert r.status_code == 403 and r.json()["code"] == "license_missing"

    # Nạp key qua CLI-path (set_key) → hợp lệ ngay (cache đã invalidate).
    async with AsyncSessionLocal() as db:
        await license_service.set_key(db, make_key(days=90))
    r = await client.get("/api/exam/auth/status")
    assert r.status_code != 403
