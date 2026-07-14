"""Giải mã đề QTI đã mã hoá (.qenc) + kiểm mã kích hoạt TOTP.

File .qenc do tool Windows ``qti-crypter/`` sinh ra (spec 2026-07-13):

    bytes 0-4   magic  b"QENC1"
    bytes 5-20  salt   16 byte ngẫu nhiên
    bytes 21-32 nonce  12 byte ngẫu nhiên
    bytes 33-   ciphertext || GCM tag 16 byte

key = PBKDF2-HMAC-SHA256(secret, salt, 600k, 32) — chuẩn mật mã AD-11.
Mã kích hoạt = TOTP RFC 6238 (HMAC-SHA1, 8 số, bước 1800s = 30 phút), server
chấp nhận lệch ±1 bước để bù drift đồng hồ máy người ra đề.

Secret 32 byte NHÚNG SẴN trong cả tool lẫn server (quyết định user: mặc định,
không cần cài đặt); lưu dạng 2 dãy XOR để không grep ra trực tiếp. Có thể
override qua env ``QTI_SECRET`` (base64) nếu sau này cần rotate không rebuild.
Fixture ``tests/fixtures/sample.qenc`` sinh từ code Node đảm bảo 2 bên khớp.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
from datetime import datetime, timezone

from app.config import settings

MAGIC = b"QENC1"
PBKDF2_ITERS = 600_000
TOTP_STEP = 1800  # giây — mã đổi mỗi 30 phút (đổi từ 600s theo yêu cầu 13-07; PHẢI khớp tool)
TOTP_DIGITS = 8

class QencError(Exception):
    """File .qenc hỏng / sai định dạng / không giải mã được / thiếu khoá."""


def get_secret() -> bytes:
    """Secret 32 byte cho mã hoá/giải mã đề .qenc — LẤY TỪ env ``QTI_SECRET`` (base64).

    AD-86: KHÔNG nhúng secret trong mã nguồn (repo công khai sẽ lộ → ai cũng giải mã
    được đề). Secret là khoá triển khai: nhà cung cấp đặt cùng giá trị vào ``.env`` của
    máy chủ và vào phần mềm mã hoá đề (qti-crypter). Thiếu → báo lỗi rõ, không giải mã.
    """
    if not settings.qti_secret:
        raise QencError(
            "Máy chủ chưa cấu hình QTI_SECRET (.env) — không giải mã được đề .qenc. "
            "Liên hệ nhà cung cấp để lấy khoá."
        )
    return base64.b64decode(settings.qti_secret)


def _totp_at(counter: int, secret: bytes) -> str:
    msg = struct.pack(">Q", counter)
    h = hmac.new(secret, msg, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITS)
    return str(code).zfill(TOTP_DIGITS)


def verify_code(code: str, now: datetime | None = None) -> bool:
    """Mã kích hoạt hợp lệ? Chấp nhận cửa sổ hiện tại ±1 bước (±30 phút)."""
    code = (code or "").strip()
    if len(code) != TOTP_DIGITS or not code.isdigit():
        return False
    ts = int((now or datetime.now(timezone.utc)).timestamp())
    counter = ts // TOTP_STEP
    secret = get_secret()
    return any(
        hmac.compare_digest(_totp_at(counter + d, secret), code) for d in (-1, 0, 1)
    )


def is_qenc(data: bytes) -> bool:
    return data[:5] == MAGIC


def decrypt_qenc(data: bytes) -> bytes:
    """Giải mã .qenc → bytes ZIP QTI gốc. Raise QencError nếu hỏng/sai."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if len(data) < 5 + 16 + 12 + 16 or not is_qenc(data):
        raise QencError("File không phải định dạng .qenc")
    salt, nonce, ct_tag = data[5:21], data[21:33], data[33:]
    key = hashlib.pbkdf2_hmac("sha256", get_secret(), salt, PBKDF2_ITERS, dklen=32)
    try:
        return AESGCM(key).decrypt(nonce, ct_tag, None)
    except InvalidTag:
        raise QencError("File đề hỏng hoặc không đúng phần mềm mã hoá")


def encrypt_qenc(zip_bytes: bytes) -> bytes:
    """Đóng gói bytes → .qenc (chỉ dùng cho test/fixture — production dùng tool)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt, nonce = os.urandom(16), os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", get_secret(), salt, PBKDF2_ITERS, dklen=32)
    return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, zip_bytes, None)
