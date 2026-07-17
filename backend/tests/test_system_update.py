"""Cập nhật từ trang Quản trị (AD-89) — backend chỉ ghi flag + đọc state.

Việc build/migrate thật do watcher trên host làm; ở đây test đúng phần backend:
quyền super-only, ghi flag đúng nội dung, đọc state watcher ghi, chặn khi đang chạy.
"""
import json
from datetime import datetime, timezone, timedelta

import pytest

from app.api.admin import system as sysmod
from app.models.enums import AdminRole
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _tmp_files(tmp_path, monkeypatch):
    """Trỏ 2 file giao tiếp vào thư mục tạm — không đụng file thật trên máy dev."""
    monkeypatch.setattr(sysmod, "REQUEST_FILE", tmp_path / "update_request.flag")
    monkeypatch.setattr(sysmod, "STATE_FILE", tmp_path / "update_state.json")
    yield


async def test_super_only(client, factory):
    _, ptok = await factory.admin(role=AdminRole.PROCTOR.value)
    assert (await client.get("/api/admin/system/update-status", headers=auth(ptok))).status_code == 403
    assert (await client.post("/api/admin/system/update", headers=auth(ptok))).status_code == 403


async def test_request_update_writes_flag(client, factory):
    admin, stok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)
    r = await client.post("/api/admin/system/update", headers=auth(stok))
    assert r.status_code == 202
    flag = json.loads(sysmod.REQUEST_FILE.read_text())
    assert flag["requested_by"] == admin.username

    # Gửi lần 2 khi flag còn chờ → không ghi đè, báo "đã có yêu cầu".
    r2 = await client.post("/api/admin/system/update", headers=auth(stok))
    assert r2.status_code == 202
    assert "đang chờ" in r2.json()["detail"]


async def test_blocked_while_running(client, factory):
    _, stok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)
    sysmod.STATE_FILE.write_text(json.dumps({"state": "running"}))
    r = await client.post("/api/admin/system/update", headers=auth(stok))
    assert r.status_code == 409


async def test_status_passthrough_and_watcher_alive(client, factory):
    _, stok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)

    # Chưa có state file → unknown, watcher chết.
    r = await client.get("/api/admin/system/update-status", headers=auth(stok))
    body = r.json()
    assert body["state"] == "unknown" and body["watcher_alive"] is False

    # Watcher vừa ghi state (written_at mới) → alive + truyền nguyên các field.
    sysmod.STATE_FILE.write_text(json.dumps({
        "state": "done", "update_available": True,
        "local": "aaaaaaa", "remote": "bbbbbbb",
        "message": "Cập nhật xong.", "log_tail": ["dòng 1", "dòng 2"],
        "written_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False))
    body = (await client.get("/api/admin/system/update-status", headers=auth(stok))).json()
    assert body["state"] == "done"
    assert body["update_available"] is True
    assert body["local"] == "aaaaaaa" and body["remote"] == "bbbbbbb"
    assert body["watcher_alive"] is True
    assert body["log_tail"] == ["dòng 1", "dòng 2"]

    # written_at cũ quá 5 phút → watcher coi như không chạy.
    sysmod.STATE_FILE.write_text(json.dumps({
        "state": "idle",
        "written_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
    }))
    body = (await client.get("/api/admin/system/update-status", headers=auth(stok))).json()
    assert body["watcher_alive"] is False

    # Flag đang chờ → queued=true.
    sysmod.REQUEST_FILE.write_text("{}")
    body = (await client.get("/api/admin/system/update-status", headers=auth(stok))).json()
    assert body["queued"] is True
