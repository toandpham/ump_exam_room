"""Bảng giấy phép server (AD-74, mở rộng AD-81) — đúng 1 dòng, id luôn = 1."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SystemLicense(Base):
    __tablename__ = "system_license"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    # AD-81: mốc CÀI ĐẶT = bắt đầu dùng thử 90 ngày (đặt 1 lần ở startup, không đổi).
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Key GIA HẠN (nullable — dùng thử không cần key). Có key hợp lệ → ghi đè hạn dùng thử.
    key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Thời điểm nhập key gia hạn (nullable khi chưa nhập).
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Mốc thời gian LỚN NHẤT server từng thấy — chống vặn lùi đồng hồ để "hồi sinh"
    # hạn đã hết (core/license.evaluate).
    max_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
