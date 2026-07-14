"""Candidate model — the whitelist of people allowed to log in and sit an exam.

Carries all 9 required fields from the spec.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from app.models.exam import Exam
    from app.models.room import Room
    from app.models.session import ExamSession


class Candidate(Base, TimestampMixin):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = uuid_pk()
    # The login key: a CCCD (12 digits) or a passport number (6–9 alnum). The
    # column name stays `cccd` for compatibility; `id_type` records which kind.
    cccd: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    id_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="cccd", server_default=text("'cccd'")
    )  # 'cccd' | 'passport' (AD-58)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    unit: Mapped[str] = mapped_column(String(255), nullable=False)  # Đơn vị
    photo_path: Mapped[str | None] = mapped_column(String(512))  # Hình thí sinh
    graduation_year: Mapped[int | None] = mapped_column(Integer)  # Năm tốt nghiệp
    major: Mapped[str | None] = mapped_column(String(255))  # Ngành
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # Đối tượng
    attempt_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )  # Lần dự thi
    exam_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exams.id", ondelete="SET NULL"), index=True
    )
    # True = thí sinh tự "Đăng ký tại chỗ" ngày thi; False = import từ Excel (AD-33).
    self_registered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Room assignment within the exam (AD-47). NULL = unassigned. Candidates are
    # only ever assigned to a ROOM — seats/machines were removed in AD-53.
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exam_rooms.id", ondelete="SET NULL"), index=True
    )

    exam: Mapped["Exam | None"] = relationship(back_populates="candidates")
    room: Mapped["Room | None"] = relationship(back_populates="candidates")
    sessions: Mapped[list["ExamSession"]] = relationship(back_populates="candidate")
