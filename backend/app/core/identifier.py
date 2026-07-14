"""Candidate identifier (giấy tờ tuỳ thân) classification.

A candidate logs in with either a Vietnamese CCCD (12 digits) or a passport
(6–9 alphanumeric chars, e.g. foreign candidates). One small helper validates
and normalizes both so every entry point (login, register, Excel import, admin
create) agrees on the rules. The normalized value is what we store in
``candidates.cccd`` (the unique login key) and ``id_type`` records which kind.
"""
from __future__ import annotations

import re

CCCD = "cccd"
PASSPORT = "passport"

_CCCD_RE = re.compile(r"^\d{12}$")
_PASSPORT_RE = re.compile(r"^[A-Z0-9]{6,9}$")

INVALID_MESSAGE = (
    "Số giấy tờ không hợp lệ: CCCD gồm đúng 12 chữ số, "
    "hoặc hộ chiếu gồm 6–9 ký tự chữ và số."
)


def classify_identifier(raw: str) -> tuple[str, str]:
    """Return ``(normalized_value, id_type)`` or raise ``ValueError``.

    Normalization: trim + uppercase (a no-op for all-digit CCCDs). A 12-digit
    string is a CCCD; otherwise a 6–9 alphanumeric string is a passport.
    """
    v = (raw or "").strip().upper()
    if _CCCD_RE.match(v):
        return v, CCCD
    if _PASSPORT_RE.match(v):
        return v, PASSPORT
    raise ValueError(INVALID_MESSAGE)
