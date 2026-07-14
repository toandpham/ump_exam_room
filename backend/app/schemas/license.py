"""Schemas trang Giấy phép (AD-74)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LicenseInfo(BaseModel):
    status: str  # valid | trial | expired | missing | clock_tampered
    issued_to: str | None = None
    expires_at: datetime | None = None
    days_left: int | None = None
    # true khi còn ≤ WARN_DAYS ngày — dashboard hiện cảnh báo đỏ.
    warn: bool = False


class LicenseSetIn(BaseModel):
    key: str = Field(min_length=10, max_length=2000)
