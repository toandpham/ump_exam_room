"""Sao lưu ngay trong trang quản trị (đợt 5).

Trước đây sao lưu chỉ chạy ngầm theo hẹn giờ trên máy chủ; người vận hành không có
cách nào biết nó còn chạy không, cũng không tự tạo được một bản trước khi mở buổi
thi. Nay xem/tạo/tải ngay trên web.

CỐ Ý KHÔNG có khôi phục qua web: nút đó bấm nhầm là mất sạch, và khôi phục trong
lúc ứng dụng đang chạy để lại trạng thái hỏng. Khôi phục vẫn đi qua
``scripts/restore.sh`` với người vận hành ngồi trước máy chủ.
"""

import gzip
from pathlib import Path

from app.models.enums import AdminRole
from tests.conftest import auth


def _dir(monkeypatch, tmp_path: Path) -> Path:
    from app.services import backup_service
    monkeypatch.setattr(backup_service, "backup_dir", lambda: tmp_path)
    return tmp_path


async def test_list_shows_backups_newest_first(client, factory, tmp_path, monkeypatch):
    d = _dir(monkeypatch, tmp_path)
    for name in ("exam_db_20260801_100000.sql.gz", "exam_db_20260802_100000.sql.gz"):
        (d / name).write_bytes(gzip.compress(b"-- dump"))
    admin, tok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)

    r = await client.get("/api/admin/admins/backups", headers=auth(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert [b["name"] for b in body["files"]] == [
        "exam_db_20260802_100000.sql.gz", "exam_db_20260801_100000.sql.gz"]
    assert body["files"][0]["size_bytes"] > 0
    assert body["latest_age_seconds"] is not None


async def test_list_reports_when_there_is_no_backup_at_all(client, factory, tmp_path, monkeypatch):
    """Không có bản nào là tình huống nguy hiểm nhất — phải nói thẳng."""
    _dir(monkeypatch, tmp_path)
    admin, tok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)
    body = (await client.get("/api/admin/admins/backups", headers=auth(tok))).json()
    assert body["files"] == []
    assert body["latest_age_seconds"] is None


async def test_download_a_backup(client, factory, tmp_path, monkeypatch):
    d = _dir(monkeypatch, tmp_path)
    (d / "exam_db_20260803_090000.sql.gz").write_bytes(gzip.compress(b"-- dump noi dung"))
    admin, tok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)

    r = await client.get("/api/admin/admins/backups/exam_db_20260803_090000.sql.gz",
                         headers=auth(tok))
    assert r.status_code == 200
    assert gzip.decompress(r.content) == b"-- dump noi dung"


async def test_download_refuses_paths_outside_the_backup_folder(client, factory, tmp_path, monkeypatch):
    """Tên file đến từ URL — không được để ai đi ngang ra ngoài thư mục sao lưu."""
    d = _dir(monkeypatch, tmp_path)
    (d.parent / "secret.txt").write_text("khong duoc doc")
    admin, tok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)

    for bad in ("../secret.txt", "..%2Fsecret.txt", "secret.txt", "exam_db_x.sql.gz"):
        r = await client.get(f"/api/admin/admins/backups/{bad}", headers=auth(tok))
        assert r.status_code in (400, 404), f"{bad} → {r.status_code}"


async def test_create_backup_writes_a_real_dump(client, factory, tmp_path, monkeypatch):
    d = _dir(monkeypatch, tmp_path)
    admin, tok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)

    r = await client.post("/api/admin/admins/backups", headers=auth(tok))
    assert r.status_code == 200, r.text
    name = r.json()["name"]
    f = d / name
    assert f.exists() and f.stat().st_size > 0
    # Phải là dump thật, không phải file rỗng/cụt.
    head = gzip.decompress(f.read_bytes())[:200].decode("utf-8", "replace")
    assert "PostgreSQL database dump" in head


async def test_backup_endpoints_are_super_admin_only(client, factory, tmp_path, monkeypatch):
    _dir(monkeypatch, tmp_path)
    _, chairman = await factory.admin(role=AdminRole.PROCTOR.value)
    _, room = await factory.admin(role=AdminRole.ROOM_PROCTOR.value)

    for tok in (chairman, room):
        assert (await client.get("/api/admin/admins/backups",
                                 headers=auth(tok))).status_code == 403
        assert (await client.post("/api/admin/admins/backups",
                                  headers=auth(tok))).status_code == 403


async def test_no_restore_endpoint_exists(client, factory, tmp_path, monkeypatch):
    """Quyết định có chủ ý: khôi phục KHÔNG làm qua web (xem chú thích đầu file)."""
    _dir(monkeypatch, tmp_path)
    _, tok = await factory.admin(role=AdminRole.SUPER_ADMIN.value)
    r = await client.post("/api/admin/admins/backups/exam_db_x.sql.gz/restore",
                          headers=auth(tok))
    assert r.status_code in (404, 405)
