"""Small HTTP helpers shared across the admin routers (AD-55 M5)."""

from __future__ import annotations

import unicodedata
from urllib.parse import quote

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def ascii_name(name_utf8: str, fallback: str = "download") -> str:
    """ASCII-safe filename for the Content-Disposition fallback.

    Transliterates Vietnamese đ/Đ then strips diacritics via NFKD so e.g.
    "Buổi" → "Buoi" (not "Bui") — AD-62.
    """
    s = name_utf8.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s or fallback


def attach(name_utf8: str, fallback: str = "download") -> str:
    """RFC 5987 Content-Disposition for non-ASCII filenames: UTF-8 ``filename*``
    plus an ASCII ``filename`` fallback so the right name downloads everywhere."""
    return (
        f'attachment; filename="{ascii_name(name_utf8, fallback)}"; '
        f"filename*=UTF-8''{quote(name_utf8)}"
    )
