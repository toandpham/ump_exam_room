"""Khiếu nại của thí sinh về MỘT câu hỏi, gắn vào bài thi.

Khác với "Báo giám thị" (AD-122) — cái đó chỉ dùng khi thông tin cá nhân bị sai.
Đây là kênh cho "câu 47 thiếu hình", "câu 12 không có đáp án đúng": nội dung được
lưu cùng bài để hội đồng đọc khi chấm, chứ không chỉ báo cho giám thị lúc đó.

Không có khoá ngoại tới câu hỏi: trên máy phục vụ thi, đề chỉ nằm trong Redis
(payload đã giải mã), không bao giờ có dòng nào trong CSDL (AD-12). ``question_id``
là id câu trong payload; ``question_number`` là số thứ tự câu TRONG ĐỀ CỦA THÍ SINH
ĐÓ (đề trộn nên mỗi người một thứ tự) để giám thị tra nhanh tại chỗ.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk

if TYPE_CHECKING:  # pragma: no cover
    pass


class QuestionReport(Base):
    __tablename__ = "question_reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sitting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_sittings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    question_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Hội đồng đã xử lý: ai, lúc nào, kết luận gì.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL")
    )
    resolution: Mapped[str | None] = mapped_column(String(500))
