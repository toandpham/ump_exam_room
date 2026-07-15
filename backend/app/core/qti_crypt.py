"""Giải mã đề QTI đã mã hoá (.qenc) — mô hình HAI KHOÁ.

File .qenc do phần mềm "Mã hoá đề thi" (chạy tại chỗ người ra đề) sinh ra:

    bytes 0-4    magic  b"QENC2"
    bytes 5-12   exp    hạn dùng (uint64 big-endian, unix giây) — dùng làm AAD
    bytes 13-28  salt   16 byte ngẫu nhiên
    bytes 29-40  nonce  12 byte ngẫu nhiên
    bytes 41-    ciphertext || GCM tag 16 byte

**Hai khoá, thiếu một là không mở được:**

1. *Khoá hệ thống* (``SYSTEM_KEY``) — hằng số NHÚNG SẴN trong cả phần mềm mã hoá
   lẫn server này, dùng vĩnh viễn. **Công khai cũng không sao**: một mình nó KHÔNG
   mở được file nào, nên không cần giấu, không cần cấu hình ``.env``.
2. *Mật khẩu đề* — ngẫu nhiên cho TỪNG file, chỉ người ra đề giữ, đọc cho hội đồng
   lúc nạp đề. Không lưu ở server nơi thi.

    khoá AES = PBKDF2-HMAC-SHA256(SYSTEM_KEY || mật_khẩu, salt, 600k, 32)

Nhờ vậy: nhặt được file đề mà không có mật khẩu → chịu; có mật khẩu nhưng file
chưa tới giờ được đọc → cũng chịu. Người ra đề kiểm soát THỜI ĐIỂM mở đề bằng
việc đọc mật khẩu ra hay chưa.

HẠN DÙNG (1 ngày): file mang sẵn mốc ``exp``; quá hạn thì server TỪ CHỐI nạp. Mốc
này nằm trong AAD của GCM nên sửa là file hỏng. Đây là **chốt chặn phía phần mềm**,
KHÔNG phải khoá tự huỷ: ai cầm cả file lẫn mật khẩu vẫn giải offline được (khoá hệ
thống là công khai). Giá trị của nó là buộc mã hoá đề sát ngày thi — file cũ để lâu
thì không nạp lên được nữa, thu hẹp cửa sổ rủi ro.

LƯU Ý MẬT MÃ: khoá của một file offline không thể "tự hết hạn" thật sự — ai có mật
khẩu thì mở được file ĐÓ mãi mãi. Kiểm soát thật nằm ở chỗ mật khẩu chỉ được đọc ra
sát giờ thi, và mỗi đề một mật khẩu khác nhau (lộ đề này không ảnh hưởng đề khác).

Định dạng cũ ``QENC1`` (một khoá) KHÔNG còn được chấp nhận — file cũ phải mã hoá lại.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import struct
import time

MAGIC = b"QENC2"
PBKDF2_ITERS = 600_000
# Hạn mặc định của file đề kể từ lúc mã hoá — PHẢI khớp qti-crypter/src/crypto.js.
DEFAULT_TTL_SECONDS = 24 * 3600  # 1 ngày
_HDR = 5 + 8 + 16 + 12  # magic + exp + salt + nonce

# Khoá hệ thống — nhúng sẵn, dùng vĩnh viễn, CÔNG KHAI CŨNG KHÔNG SAO (một mình nó
# không mở được gì). PHẢI khớp từng byte với qti-crypter/src/secret.js.
SYSTEM_KEY_B64 = "Xwk1rUp4E3wemnXg7DiBGa+//I4bCADU5E+/uF70KD0="


class QencError(Exception):
    """File .qenc hỏng / sai định dạng / sai mật khẩu."""


def system_key() -> bytes:
    return base64.b64decode(SYSTEM_KEY_B64)


def normalize_password(password: str) -> str:
    """Chuẩn hoá mật khẩu người dùng gõ: HOA hoá, bỏ mọi ký tự không phải chữ/số
    (dấu cách, gạch ngang khi đọc cho nhau). PHẢI khớp hàm cùng tên bên tool."""
    return re.sub(r"[^A-Z0-9]", "", (password or "").upper())


def _derive_key(password: str, salt: bytes) -> bytes:
    """Trộn HAI khoá: khoá hệ thống (nhúng) + mật khẩu đề (người ra đề đọc)."""
    material = system_key() + normalize_password(password).encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", material, salt, PBKDF2_ITERS, dklen=32)


def is_qenc(data: bytes) -> bool:
    return data[:5] == MAGIC


def expires_at(data: bytes) -> int:
    """Mốc hết hạn (unix giây) ghi trong file."""
    return struct.unpack(">Q", data[5:13])[0]


def decrypt_qenc(data: bytes, password: str, now: int | None = None) -> bytes:
    """Giải mã .qenc → bytes ZIP QTI gốc. Raise QencError nếu hỏng/sai mật khẩu/quá hạn."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not normalize_password(password):
        raise QencError("Chưa nhập mật khẩu mở đề (người ra đề cung cấp).")
    if len(data) < _HDR + 16 or not is_qenc(data):
        raise QencError(
            "File không phải định dạng .qenc của phần mềm Mã hoá đề thi "
            "(bản mới). File mã hoá bằng bản cũ phải mã hoá lại."
        )
    exp = expires_at(data)
    now = int(time.time()) if now is None else now
    if now > exp:
        raise QencError(
            "File đề đã QUÁ HẠN (mỗi file chỉ dùng trong 1 ngày kể từ lúc mã hoá). "
            "Đề nghị người ra đề mã hoá lại và gửi file mới."
        )
    aad = data[5:13]   # mốc hạn được xác thực bởi GCM → sửa là hỏng file
    salt, nonce, ct_tag = data[13:29], data[29:41], data[41:]
    key = _derive_key(password, salt)
    try:
        return AESGCM(key).decrypt(nonce, ct_tag, aad)
    except InvalidTag:
        raise QencError("Mật khẩu mở đề không đúng (hoặc file đề đã hỏng).")


def encrypt_qenc(zip_bytes: bytes, password: str, ttl: int = DEFAULT_TTL_SECONDS) -> bytes:
    """Đóng gói bytes → .qenc (dùng cho test/fixture — thực tế dùng phần mềm mã hoá)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    exp = struct.pack(">Q", int(time.time()) + ttl)
    salt, nonce = os.urandom(16), os.urandom(12)
    key = _derive_key(password, salt)
    return MAGIC + exp + salt + nonce + AESGCM(key).encrypt(nonce, zip_bytes, exp)
