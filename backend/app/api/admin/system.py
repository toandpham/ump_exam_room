"""Cập nhật hệ thống từ trang Quản trị (AD-89).

Backend chạy TRONG container nên không thể tự git-pull/build lại chính mình. Cơ chế:

  trang Quản trị bấm "Cập nhật"
    → POST ở đây GHI FILE YÊU CẦU (update_request.flag, nằm trong bind-mount /app
      nên host nhìn thấy ở backend/update_request.flag)
    → watcher trên HOST (scripts/update-watcher.sh, systemd) thấy file → chạy
      ./update.sh (vẫn giữ chốt chặn "đang có thí sinh thi") → ghi tiến trình vào
      update_state.json
    → trang Quản trị poll GET ở đây đọc trạng thái ra màn hình.

Backend chỉ đọc/ghi 2 file — mọi quyền build/migrate nằm ở host, container không
cầm docker socket hay quyền gì thêm.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import require_roles
from app.models import Admin
from app.models.enums import AdminRole

router = APIRouter()

_super_only = require_roles(AdminRole.SUPER_ADMIN.value)

# /app = bind-mount của thư mục backend/ trên host (docker-compose) — watcher trên
# host đọc/ghi cùng 2 file này tại backend/update_request.flag + update_state.json.
REQUEST_FILE = Path("/app/update_request.flag")
STATE_FILE = Path("/app/update_state.json")


class UpdateStatus(BaseModel):
    # Trạng thái do watcher ghi; backend truyền qua + thêm cờ "queued".
    state: str = "unknown"          # unknown | idle | running | done | failed
    update_available: bool = False
    local: str | None = None        # commit đang chạy (7 ký tự)
    remote: str | None = None       # commit mới nhất trên git
    checked_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None
    log_tail: list[str] = []
    queued: bool = False            # đã có yêu cầu chờ watcher nhặt
    watcher_alive: bool = False     # watcher có đang chạy không (theo mốc ghi state)


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@router.get("/update-status", response_model=UpdateStatus,
            dependencies=[Depends(_super_only)])
async def update_status() -> UpdateStatus:
    raw = _read_state()
    status = UpdateStatus(**{k: v for k, v in raw.items() if k in UpdateStatus.model_fields})
    status.queued = REQUEST_FILE.exists()
    # Watcher ghi state mỗi vòng (≤60s); im quá 5 phút = không chạy (chưa cài / chết).
    ts = raw.get("written_at")
    if ts:
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(ts)).total_seconds()
            status.watcher_alive = age < 300
        except ValueError:
            pass
    return status


@router.post("/update", status_code=202, dependencies=[Depends(_super_only)])
async def request_update(admin: Admin = Depends(_super_only)) -> dict:
    state = _read_state()
    if state.get("state") == "running":
        raise HTTPException(409, "Đang cập nhật dở — chờ xong đã.")
    if REQUEST_FILE.exists():
        return {"detail": "Đã có yêu cầu đang chờ — hệ thống sẽ cập nhật trong ~1 phút."}
    REQUEST_FILE.write_text(json.dumps({
        "requested_by": admin.username,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }), encoding="utf-8")
    return {"detail": "Đã gửi yêu cầu — hệ thống sẽ cập nhật trong ~1 phút."}
