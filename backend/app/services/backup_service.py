"""Sao lưu cơ sở dữ liệu cho trang quản trị (đợt 5).

Thư mục dùng CHUNG với ``scripts/backup.sh`` (chạy trên máy chủ theo hẹn giờ), nên
bản tạo từ web và bản tự động nằm cùng một chỗ, cùng một cách đặt tên, và cùng được
``scripts/restore.sh`` dùng lại.

**Không có khôi phục ở đây, có chủ ý.** Nút khôi phục trên web bấm nhầm là mất sạch
dữ liệu, và khôi phục trong khi ứng dụng đang chạy sẽ để lại trạng thái hỏng (kết
nối cũ, cache Redis lệch với CSDL vừa thay). Khôi phục vẫn phải là việc có người
ngồi trước máy chủ, qua ``scripts/restore.sh``.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger("exam.backup")

# Đúng cách đặt tên của scripts/backup.sh — dùng để lọc file và để chặn đường dẫn
# lạ khi tải về (tên đến từ URL).
NAME_RE = re.compile(r"^exam_db_\d{8}_\d{6}\.sql\.gz$")

# pg_dump chạy đồng bộ trong luồng riêng; quá mốc này thì coi như hỏng, không để
# treo mãi một luồng của tiến trình phục vụ.
DUMP_TIMEOUT_SECONDS = 600


def backup_dir() -> Path:
    """Thư mục sao lưu (gắn từ máy chủ vào ``/backups``). Hàm chứ không phải hằng
    để test thay được."""
    return Path(getattr(settings, "backup_dir", "/backups"))


def _dsn_parts() -> tuple[str, str, str, str, str]:
    """(host, port, user, password, dbname) lấy từ DATABASE_URL."""
    u = urlparse(str(settings.database_url).replace("+asyncpg", ""))
    return (u.hostname or "postgres", str(u.port or 5432),
            u.username or "exam", u.password or "", (u.path or "/exam_db").lstrip("/"))


def list_backups() -> list[dict]:
    """Các bản sao lưu hiện có, mới nhất trước."""
    d = backup_dir()
    if not d.is_dir():
        return []
    out = []
    for f in d.iterdir():
        if not f.is_file() or not NAME_RE.match(f.name):
            continue
        st = f.stat()
        out.append({
            "name": f.name,
            "size_bytes": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        })
    out.sort(key=lambda b: b["created_at"], reverse=True)
    return out


def resolve_backup(name: str) -> Path | None:
    """Đường dẫn thật của một bản sao lưu, hoặc None nếu tên không hợp lệ / không có.

    Tên đến từ URL nên kiểm hai lớp: khớp đúng mẫu, VÀ đường dẫn sau khi giải hết
    liên kết vẫn nằm trong thư mục sao lưu."""
    if not NAME_RE.match(name):
        return None
    d = backup_dir().resolve()
    p = (d / name).resolve()
    if p.parent != d or not p.is_file():
        return None
    return p


def _run_dump(target: Path) -> None:
    """Chạy pg_dump và ghi ra file .gz. Ném lỗi nếu không thành công.

    Dump hỏng giữa chừng KHÔNG được để lại file cụt — người vận hành sẽ tưởng đó là
    bản dùng được (cùng lý do với scripts/backup.sh). Vì vậy ghi ra file tạm rồi
    mới đổi tên."""
    host, port, user, password, dbname = _dsn_parts()
    env = {**os.environ, "PGPASSWORD": password}
    tmp = target.with_suffix(target.suffix + ".part")
    try:
        proc = subprocess.run(
            ["pg_dump", "-h", host, "-p", port, "-U", user, dbname],
            env=env, capture_output=True, timeout=DUMP_TIMEOUT_SECONDS,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                (proc.stderr or b"").decode("utf-8", "replace").strip()[:400]
                or "pg_dump thất bại")
        tmp.write_bytes(gzip.compress(proc.stdout))
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)


async def create_backup() -> dict:
    """Tạo một bản sao lưu ngay. Trả về thông tin file vừa ghi."""
    d = backup_dir()
    d.mkdir(parents=True, exist_ok=True)
    name = f"exam_db_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql.gz"
    target = d / name
    # pg_dump là tác vụ đồng bộ, chạy vài giây tới vài phút — đẩy sang luồng riêng
    # để không chặn vòng lặp sự kiện đang phục vụ hàng trăm máy thi.
    await asyncio.to_thread(_run_dump, target)
    st = target.stat()
    logger.info("Đã tạo bản sao lưu %s (%d bytes)", name, st.st_size)
    return {"name": name, "size_bytes": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)}
