"""Mã hoá đề .qenc — mô hình HAI KHOÁ (khoá hệ thống nhúng + mật khẩu đề).

Fixture ``fixtures/sample.qenc`` được sinh bằng CODE NODE của phần mềm Mã hoá đề
(``qti-crypter/``) — test giải mã nó ở đây chính là bảo chứng cross-language: đổi
thuật toán một bên mà quên bên kia là test đỏ ngay.
"""
from pathlib import Path

import pytest

from app.core import qti_crypt

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_PW = "ACDE-FGHJ-KMNP-QRTU"   # mật khẩu dùng khi sinh fixture (scripts scratchpad)
PW = "MHFC-33RF-WMAM-VNQ4"


# ─── khoá hệ thống ────────────────────────────────────────────────────────────

def test_system_key_is_32_bytes():
    assert len(qti_crypt.system_key()) == 32


def test_normalize_password_ignores_case_and_separators():
    # đọc qua điện thoại → người gõ có thể dùng chữ thường / dấu cách thay gạch ngang
    assert qti_crypt.normalize_password("acde-fghj kmnp") == "ACDEFGHJKMNP"
    assert qti_crypt.normalize_password("  a c d e  ") == "ACDE"
    assert qti_crypt.normalize_password("") == ""
    assert qti_crypt.normalize_password(None) == ""


# ─── cross-language: file do Node sinh, Python phải mở được ───────────────────

def test_decrypt_node_fixture_cross_language():
    data = (FIXTURES / "sample.qenc").read_bytes()
    plain = (FIXTURES / "sample_qenc_plain.bin").read_bytes()
    assert qti_crypt.is_qenc(data)
    # fixture mang hạn cố định lúc sinh → chấm mốc thời gian ngay trước hạn
    now = qti_crypt.expires_at(data) - 10
    assert qti_crypt.decrypt_qenc(data, FIXTURE_PW, now=now) == plain


# ─── hai khoá: thiếu mật khẩu là không mở được ────────────────────────────────

def test_roundtrip_with_password():
    data = b"zip bytes \x00\x01 tuy\xe1\xbb\x87t m\xe1\xba\xadt"
    blob = qti_crypt.encrypt_qenc(data, PW)
    assert qti_crypt.is_qenc(blob)
    assert qti_crypt.decrypt_qenc(blob, PW) == data
    # salt/nonce ngẫu nhiên → 2 lần mã hoá cùng nội dung vẫn ra khác nhau
    assert qti_crypt.encrypt_qenc(data, PW) != blob


def test_wrong_password_cannot_open():
    """CHỐT BẢO MẬT: khoá hệ thống là công khai — MỘT MÌNH nó không mở được gì."""
    blob = qti_crypt.encrypt_qenc(b"de thi tuyet mat", PW)
    with pytest.raises(qti_crypt.QencError, match="Mật khẩu"):
        qti_crypt.decrypt_qenc(blob, "ACDE-FGHJ-KMNP-QRTU")


def test_empty_password_rejected():
    blob = qti_crypt.encrypt_qenc(b"x", PW)
    with pytest.raises(qti_crypt.QencError, match="Chưa nhập mật khẩu"):
        qti_crypt.decrypt_qenc(blob, "")


def test_password_normalized_on_both_sides():
    blob = qti_crypt.encrypt_qenc(b"noi dung", PW)
    # gõ thường + dấu cách thay gạch ngang vẫn mở được
    assert qti_crypt.decrypt_qenc(blob, PW.lower().replace("-", " ")) == b"noi dung"


# ─── hạn dùng 1 ngày ──────────────────────────────────────────────────────────

def test_default_ttl_is_one_day():
    assert qti_crypt.DEFAULT_TTL_SECONDS == 24 * 3600


def test_expired_file_rejected():
    blob = qti_crypt.encrypt_qenc(b"de thi", PW)
    exp = qti_crypt.expires_at(blob)
    assert qti_crypt.decrypt_qenc(blob, PW, now=exp - 1) == b"de thi"      # còn hạn
    with pytest.raises(qti_crypt.QencError, match="QUÁ HẠN"):
        qti_crypt.decrypt_qenc(blob, PW, now=exp + 1)                       # quá hạn


def test_tampered_expiry_breaks_file():
    """Hạn nằm trong AAD của GCM → sửa để 'gia hạn' là file hỏng luôn."""
    blob = bytearray(qti_crypt.encrypt_qenc(b"de thi", PW))
    blob[12] ^= 0xFF   # đổi byte cuối của mốc exp
    with pytest.raises(qti_crypt.QencError):
        qti_crypt.decrypt_qenc(bytes(blob), PW, now=0)


# ─── file hỏng / sai định dạng ────────────────────────────────────────────────

def test_rejects_wrong_magic_and_old_format():
    with pytest.raises(qti_crypt.QencError):
        qti_crypt.decrypt_qenc(b"PK\x03\x04 plain zip bytes" + b"x" * 60, PW)
    # định dạng cũ QENC1 (một khoá) không còn được chấp nhận
    with pytest.raises(qti_crypt.QencError):
        qti_crypt.decrypt_qenc(b"QENC1" + b"x" * 80, PW)


def test_rejects_tampered_ciphertext_and_truncated():
    blob = bytearray(qti_crypt.encrypt_qenc(b"de thi tuyet mat", PW))
    blob[-1] ^= 0xFF   # lật 1 bit trong GCM tag
    with pytest.raises(qti_crypt.QencError):
        qti_crypt.decrypt_qenc(bytes(blob), PW)
    with pytest.raises(qti_crypt.QencError):
        qti_crypt.decrypt_qenc(b"QENC2short", PW)
