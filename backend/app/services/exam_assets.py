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
import io
import logging
import shutil
import uuid
from pathlib import Path

from PIL import Image, ImageFile

from app.config import settings

logger = logging.getLogger("exam.assets")

# Ảnh đề rộng hơn ngưỡng này sẽ được thu nhỏ khi nạp đề (AD-90). Máy thi thật là
# Win7/4GB: ảnh gốc từ máy scan/điện thoại (3000–4000px) tốn cả chục MB RAM mỗi
# tấm khi giải nén. AD-109: hạ 1600→1280 — màn máy thi 1366×768 nên tấm 1600px
# KHÔNG BAO GIỜ hiển thị hết cỡ được; giải nén to hơn màn hình = phí RAM vô ích
# (chính là cú đơ ~2s khi đóng zoom). 1280px vừa khít phóng to full màn.
MAX_IMAGE_WIDTH = 1280
JPEG_QUALITY = 85

# AD-107: bản NHỎ hiển thị trong bài. Khung câu hỏi chỉ rộng ~720px nhưng máy con
# phải GIẢI NÉN nguyên tấm 1600px (~7-8MB RAM/tấm) → máy 4GB nghẹt mỗi lần chuyển
# câu nhiều ảnh (hiện trường: "để yên 20-30s mới nhanh lại"). Sinh thêm bản ≤720px
# cho hiển thị; bản 1600px CHỈ tải khi bấm phóng to (zoom vẫn nét).
THUMB_WIDTH = 720
THUMB_QUALITY = 82

ImageFile.LOAD_TRUNCATED_IMAGES = True

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


def shrink_image(data: bytes, mime: str | None) -> tuple[bytes, str | None]:
    """Thu nhỏ ảnh quá khổ về ``MAX_IMAGE_WIDTH`` (AD-90). Trả (bytes, mime) —
    ảnh đã đủ nhỏ, định dạng lạ hoặc lỗi giải mã thì trả NGUYÊN BẢN (không bao
    giờ làm hỏng đề vì một tấm ảnh)."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width <= MAX_IMAGE_WIDTH:
                return data, mime
            fmt = (im.format or "").upper()
            if fmt not in {"JPEG", "PNG", "WEBP"}:
                return data, mime
            height = max(1, round(im.height * MAX_IMAGE_WIDTH / im.width))
            resized = im.convert("RGB") if fmt == "JPEG" else im.copy()
            resized = resized.resize((MAX_IMAGE_WIDTH, height), Image.LANCZOS)
            buf = io.BytesIO()
            if fmt == "JPEG":
                resized.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
            else:
                resized.save(buf, fmt)
            out = buf.getvalue()
            # Có trường hợp file nén lại còn to hơn (PNG ảnh chụp) → giữ bản gốc.
            return (out, mime) if len(out) < len(data) else (data, mime)
    except Exception as exc:  # noqa: BLE001 — ảnh lạ/hỏng: dùng nguyên bản
        logger.warning("shrink_image bỏ qua một ảnh: %s", exc)
        return data, mime


def _thumb_bytes(data: bytes) -> bytes | None:
    """Bản nhỏ ≤``THUMB_WIDTH`` để hiển thị trong bài (AD-107). Mục tiêu là giảm
    SỐ PIXEL máy con phải giải nén (RAM), không chỉ số byte. Trả None khi ảnh đã
    đủ nhỏ / định dạng lạ / lỗi — caller dùng luôn bản đầy đủ."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width <= THUMB_WIDTH:
                return None
            fmt = (im.format or "").upper()
            if fmt not in {"JPEG", "PNG", "WEBP"}:
                return None
            height = max(1, round(im.height * THUMB_WIDTH / im.width))
            resized = im.convert("RGB") if fmt == "JPEG" else im.copy()
            resized = resized.resize((THUMB_WIDTH, height), Image.LANCZOS)
            buf = io.BytesIO()
            if fmt == "JPEG":
                resized.save(buf, "JPEG", quality=THUMB_QUALITY, optimize=True)
            else:
                resized.save(buf, fmt)
            return buf.getvalue()
    except Exception as exc:  # noqa: BLE001 — ảnh lạ/hỏng: dùng bản đầy đủ
        logger.warning("thumb bỏ qua một ảnh: %s", exc)
        return None


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
            data, _ = shrink_image(data, im.get("mime"))
            sha = hashlib.sha256(data).hexdigest()
            ext = _EXT.get((im.get("mime") or "").lower(), "jpg")
            fname = f"{sha}.{ext}"
            fpath = img_dir / fname
            if not fpath.exists():
                fpath.write_bytes(data)
            im["url"] = f"{prefix}/{fname}"
            # AD-107: bản nhỏ hiển thị trong bài (bản đầy đủ chỉ tải khi phóng to).
            thumb = _thumb_bytes(data)
            if thumb is not None:
                tname = f"{sha}_t.{ext}"
                tpath = img_dir / tname
                if not tpath.exists():
                    tpath.write_bytes(thumb)
                im["thumb_url"] = f"{prefix}/{tname}"
            else:
                im["thumb_url"] = im["url"]
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
