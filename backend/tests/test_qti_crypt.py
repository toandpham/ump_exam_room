"""Mã hoá đề .qenc + mã kích hoạt TOTP (spec 2026-07-13).

Fixture ``fixtures/sample.qenc`` được sinh bằng CODE NODE của tool
``qti-crypter/`` — test giải mã nó ở đây chính là bảo chứng cross-language
(tool Windows ↔ server Python khớp từng byte).
"""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core import qti_crypt

FIXTURES = Path(__file__).parent / "fixtures"

# Vector TOTP: cùng secret nhúng + timestamp cố định → cùng mã ở cả Node lẫn
# Python (giá trị này cũng được assert trong qti-crypter/test).
VECTOR_TS = 1_770_000_000
VECTOR_CODE = "51727649"       # bước 1800s (30 phút) — đổi từ bộ vector bước 600s cũ
VECTOR_CODE_PREV = "97448987"
VECTOR_CODE_NEXT = "15187590"


def _at(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


# ─── secret + TOTP ────────────────────────────────────────────────────────────

def test_secret_is_32_bytes():
    assert len(qti_crypt.get_secret()) == 32


def test_totp_vector_matches_node():
    assert qti_crypt.verify_code(VECTOR_CODE, now=_at(VECTOR_TS))


def test_totp_accepts_prev_and_next_window():
    # drift ±1 bước (±30 phút): mã của bước trước/sau vẫn được chấp nhận
    assert qti_crypt.verify_code(VECTOR_CODE_PREV, now=_at(VECTOR_TS))
    assert qti_crypt.verify_code(VECTOR_CODE_NEXT, now=_at(VECTOR_TS))


def test_totp_rejects_expired_and_garbage():
    # mã cách 2 bước (60 phút) → hết hạn
    assert not qti_crypt.verify_code(VECTOR_CODE, now=_at(VECTOR_TS + 2 * qti_crypt.TOTP_STEP))
    assert not qti_crypt.verify_code("00000000", now=_at(VECTOR_TS))
    assert not qti_crypt.verify_code("", now=_at(VECTOR_TS))
    assert not qti_crypt.verify_code("abc12345", now=_at(VECTOR_TS))
    assert not qti_crypt.verify_code("1234567", now=_at(VECTOR_TS))  # 7 số


# ─── .qenc ────────────────────────────────────────────────────────────────────

def test_decrypt_node_fixture_cross_language():
    """File .qenc sinh từ Node (tool) phải giải mã được bằng Python (server)."""
    qenc = (FIXTURES / "sample.qenc").read_bytes()
    plain = (FIXTURES / "sample_qenc_plain.bin").read_bytes()
    assert qti_crypt.is_qenc(qenc)
    assert qti_crypt.decrypt_qenc(qenc) == plain


def test_encrypt_decrypt_roundtrip_python():
    data = b"zip bytes \x00\x01 tuy\xe1\xbb\x87t m\xe1\xba\xadt"
    qenc = qti_crypt.encrypt_qenc(data)
    assert qti_crypt.is_qenc(qenc)
    assert qti_crypt.decrypt_qenc(qenc) == data
    # salt/nonce ngẫu nhiên → 2 lần mã hoá ra khác nhau
    assert qti_crypt.encrypt_qenc(data) != qenc


def test_decrypt_rejects_wrong_magic():
    with pytest.raises(qti_crypt.QencError):
        qti_crypt.decrypt_qenc(b"PK\x03\x04 plain zip bytes" + b"x" * 60)


def test_decrypt_rejects_tampered_ciphertext():
    qenc = bytearray(qti_crypt.encrypt_qenc(b"de thi tuyet mat"))
    qenc[-1] ^= 0xFF  # lật 1 bit trong GCM tag
    with pytest.raises(qti_crypt.QencError):
        qti_crypt.decrypt_qenc(bytes(qenc))


def test_decrypt_rejects_truncated():
    with pytest.raises(qti_crypt.QencError):
        qti_crypt.decrypt_qenc(b"QENC1short")
