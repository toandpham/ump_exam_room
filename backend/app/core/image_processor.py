"""Image validation, resizing and storage for candidate photos."""

from __future__ import annotations

import io
import os

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

ALLOWED_FORMATS = {"JPEG": ".jpg", "PNG": ".png"}
CANDIDATE_SIZE = (400, 500)  # portrait WxH


class ImageValidationError(Exception):
    """Raised when an uploaded file is not an acceptable image."""


def _abs(rel_path: str) -> str:
    return os.path.join(settings.upload_dir, rel_path)


def save_candidate_photo(content: bytes, cccd: str, *, subdir: str = "candidates") -> str:
    """Validate and store a candidate portrait, cover-cropped to 400x500.

    The file is named after the CCCD so re-uploads (single or via ZIP) overwrite
    cleanly. Returns the path relative to the uploads root.
    """
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise ImageValidationError(f"Ảnh vượt quá {settings.max_upload_mb}MB")
    if not content:
        raise ImageValidationError("File rỗng")
    try:
        Image.open(io.BytesIO(content)).verify()
        img = Image.open(io.BytesIO(content))
    except (UnidentifiedImageError, OSError):
        raise ImageValidationError("File không phải ảnh hợp lệ")
    if img.format not in ALLOWED_FORMATS:
        raise ImageValidationError("Chỉ chấp nhận ảnh JPG hoặc PNG")

    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, CANDIDATE_SIZE, method=Image.Resampling.LANCZOS)

    rel_path = f"{subdir}/{cccd}.jpg"
    dest = _abs(rel_path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    img.save(dest, "JPEG", quality=88, optimize=True)
    return rel_path


def delete_upload(rel_path: str | None) -> None:
    """Best-effort removal of a stored upload. Never raises."""
    if not rel_path:
        return
    try:
        path = _abs(rel_path)
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
