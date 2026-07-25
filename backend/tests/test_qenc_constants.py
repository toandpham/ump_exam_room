"""Khoá cứng 4 hằng số định dạng .qenc (QENC2) — refactor đợt 3, Phase 0 (T0.1).

Các giá trị này được NHÂN ĐÔI trong tool nội bộ `qti-crypter/` (src/crypto.js +
src/secret.js) — tool nằm NGOÀI repo public (gitignored) nên không có test
cross-language chạy chung được. Đổi bất kỳ giá trị nào ở một bên mà quên bên kia
= server không giải mã được file đề của tool (hoặc ngược lại) → SẬP khâu nạp đề
toàn hệ thống đúng ngày thi.

Vì vậy: test này assert CỨNG từng giá trị. Ai đổi chúng phải:
  1. Đổi đồng bộ qti-crypter/src/crypto.js (+ secret.js nếu là SYSTEM_KEY),
  2. Build + PHÁT LẠI MaHoaDeThi.exe cho người ra đề,
  3. Cập nhật test này + fixture tests/fixtures/sample.qenc (sinh bằng tool),
rồi mới được sửa con số ở đây.

Lớp bảo vệ thứ hai (đã có sẵn): tests/test_qti_crypt.py giải mã fixture
sample.qenc sinh bằng CHÍNH code Node của tool — bắt drift về THUẬT TOÁN.
Test này bắt drift về HẰNG SỐ, rẻ và nổ sớm hơn.
"""

from app.core import qti_crypt


def test_qenc_magic_frozen():
    assert qti_crypt.MAGIC == b"QENC2"


def test_qenc_pbkdf2_iters_frozen():
    assert qti_crypt.PBKDF2_ITERS == 600_000


def test_qenc_default_ttl_frozen():
    assert qti_crypt.DEFAULT_TTL_SECONDS == 24 * 3600


def test_qenc_system_key_frozen():
    assert qti_crypt.SYSTEM_KEY_B64 == "Xwk1rUp4E3wemnXg7DiBGa+//I4bCADU5E+/uF70KD0="
    # Khoá phải là 32 byte base64 hợp lệ (AES-256 key material).
    assert len(qti_crypt.system_key()) == 32
