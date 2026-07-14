"""SP-1 (thiết kế offline-first): vật chất hoá ảnh đề của một buổi ra FILE TĨNH
dưới ``uploads/sitting_<id>/img/`` để Caddy phục vụ (/uploads/*), nhờ đó
``/questions`` chỉ trả URL ngắn thay vì base64 — diệt cú bùng CPU khi 1000 máy
cùng tải đề lúc bắt đầu thi. Xoá file khi đóng/ xoá buổi.

Tên thư mục suy ra từ ``sitting.id.hex`` (UUID 128-bit, đủ khó đoán theo tinh
thần 'giảm bảo mật vừa phải') nên KHÔNG cần migration/cột mới.
"""

from __future__ import annotations

import base64
import hashlib
import shutil
import uuid
from pathlib import Path

from app.config import settings

# mime → đuôi file (ảnh QTI nội tuyến thường jpg/png/webp/gif).
_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
}


def _sitting_dir(sitting_id: uuid.UUID) -> Path:
    return Path(settings.upload_dir) / f"sitting_{sitting_id.hex}"


def materialize_payload_images(sitting_id: uuid.UUID, payload: dict) -> dict:
    """Ghi bytes của mọi ảnh (câu + đáp án) ra đĩa, dedup theo sha256 nội dung,
    THÊM khoá ``url`` (gốc-tương-đối) và XOÁ ``b64`` khỏi từng image dict —
    bản payload cache Redis chỉ còn URL, không kèm blob ảnh (SP-1b: đề nhiều
    ảnh từng phình payload ~110MB làm lag mỗi cú /questions). ``b64`` gốc vẫn
    an toàn trong ``encrypted_payload`` ở DB (mọi call site đều giải mã lại từ
    đó trước khi gọi hàm này). Ảnh hỏng (không decode được) giữ nguyên dict để
    /questions còn fallback data URL. Mutate + trả về chính ``payload``.
    Idempotent: file đã tồn tại → bỏ qua ghi."""
    img_dir = _sitting_dir(sitting_id) / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"/uploads/sitting_{sitting_id.hex}/img"

    def _do(images: list[dict] | None) -> None:
        for im in images or []:
            b64 = im.get("b64")
            if not b64:
                continue
            try:
                data = base64.b64decode(b64)
            except Exception:
                # Ảnh hỏng → bỏ qua, không chặn cả buổi.
                continue
            sha = hashlib.sha256(data).hexdigest()
            ext = _EXT.get((im.get("mime") or "").lower(), "jpg")
            fname = f"{sha}.{ext}"
            fpath = img_dir / fname
            if not fpath.exists():
                fpath.write_bytes(data)
            im["url"] = f"{prefix}/{fname}"
            im.pop("b64", None)

    for q in payload.get("questions", []):
        _do(q.get("images"))
        for o in q.get("options", []):
            _do(o.get("images"))
    return payload


def wipe_sitting_assets(sitting_id: uuid.UUID) -> bool:
    """Xoá toàn bộ thư mục ảnh tĩnh của buổi (gọi khi đóng/ xoá buổi). Trả True
    nếu có gì để xoá."""
    d = _sitting_dir(sitting_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False
