"""AES-256-GCM authenticated encryption with PBKDF2-HMAC-SHA256 key derivation.

Used for at-rest encryption of the exam payload (``exams.encrypted_payload``);
the key is derived from a server secret, never exposed to admins (AD-23).
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings

SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32  # AES-256


class DecryptionError(Exception):
    """Wrong password or corrupted/tampered ciphertext."""


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text)


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=salt,
        iterations=settings.pbkdf2_iterations,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt(plaintext: bytes, password: str) -> dict[str, str]:
    """Encrypt with a fresh random salt+nonce. Returns base64 salt/nonce/ciphertext."""
    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    key = derive_key(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return {"salt": _b64e(salt), "nonce": _b64e(nonce), "ciphertext": _b64e(ciphertext)}


def decrypt(salt_b64: str, nonce_b64: str, ciphertext_b64: str, password: str) -> bytes:
    """Decrypt; raises DecryptionError on wrong password or tampering."""
    key = derive_key(password, _b64d(salt_b64))
    try:
        return AESGCM(key).decrypt(_b64d(nonce_b64), _b64d(ciphertext_b64), None)
    except (InvalidTag, ValueError):
        raise DecryptionError("Sai mật khẩu hoặc file đề đã bị hỏng/chỉnh sửa")
