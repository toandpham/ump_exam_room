"""Read/write the encrypted exam-payload blob (the at-rest format stored in
``exams.encrypted_payload``).

File format (v1.0) — top level is UNENCRYPTED JSON. Only the question/answer
content (the "payload") is encrypted; non-secret metadata stays in clear:

    {
      "version": "1.0",
      "exam_name": "...",
      "duration_minutes": 45,
      "shuffle_questions": true,
      "shuffle_options": false,
      "checksum_sha256": "<hex of plaintext payload>",
      "salt": "<base64>", "nonce": "<base64>",
      "encrypted_payload": "<base64 AES-256-GCM ciphertext>"
    }

Decrypted payload JSON:
    {"questions": [
        {"id","text","images":[{"b64","mime"}],"correct_option","order_index",
         "options": [{"id","text","images":[{"b64","mime"}]}]}
    ]}

These blobs are produced from QTI imports (see ``api/admin/exams._build_exam_file_from_qti``)
and stored at rest in ``exams.encrypted_payload``; readers here load them back.
"""

from __future__ import annotations

import hashlib
import json

from app.core import encryption

FORMAT_VERSION = "1.0"


class ExamPackageError(Exception):
    """Malformed .exam file."""


_REQUIRED_KEYS = {
    "version", "exam_name", "duration_minutes", "shuffle_questions",
    "shuffle_options", "checksum_sha256", "salt", "nonce", "encrypted_payload",
}


def parse_exam_file(content: bytes) -> dict:
    """Parse + structurally validate a .exam file. Raises ExamPackageError."""
    try:
        obj = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ExamPackageError("File .exam không phải JSON hợp lệ")
    if not isinstance(obj, dict):
        raise ExamPackageError("File .exam sai cấu trúc")
    missing = _REQUIRED_KEYS - obj.keys()
    if missing:
        raise ExamPackageError(f"File .exam thiếu trường: {', '.join(sorted(missing))}")
    if obj["version"] != FORMAT_VERSION:
        raise ExamPackageError(f"Phiên bản file không được hỗ trợ: {obj['version']}")
    return obj


def decrypt_exam_file(file_obj: dict, password: str) -> dict:
    """Decrypt the payload and verify the SHA-256 checksum. Raises DecryptionError
    (wrong password / tampering) or ExamPackageError (checksum mismatch)."""
    plaintext = encryption.decrypt(
        file_obj["salt"], file_obj["nonce"], file_obj["encrypted_payload"], password
    )
    if hashlib.sha256(plaintext).hexdigest() != file_obj["checksum_sha256"]:
        raise ExamPackageError("Checksum không khớp — nội dung đề có thể đã bị hỏng")
    return json.loads(plaintext.decode("utf-8"))
