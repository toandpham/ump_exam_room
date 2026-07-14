"""Exam model."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk
from app.models.enums import ExamStatus

if TYPE_CHECKING:
    from app.models.candidate import Candidate
    from app.models.room import Room
    from app.models.session import ExamSession
    from app.models.sitting import Sitting


class Exam(Base, TimestampMixin):
    __tablename__ = "exams"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Default duration prefilled when creating a sitting; the authoritative
    # run-time duration lives on each Sitting (AD-47).
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    exam_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ExamStatus.DRAFT.value,
        server_default=ExamStatus.DRAFT.value, index=True,
    )
    # NOTE (AD-47): the đề lives on sittings now. ``encrypted_payload``,
    # ``shuffle_questions``, ``shuffle_options``, ``question_count`` and
    # ``report_snapshot`` moved to ``exam_sittings``; ``paused_at`` moved to
    # ``exam_sessions`` (per-candidate pause).
    # Owning proctor (AD-30). A proctor sees/operates only their own exams;
    # super_admin sees all. NULL = legacy/unowned (visible to every proctor).
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), index=True
    )
    # Whether candidates may self-register on exam day for this section (AD-33).
    # Chosen at create time; when False the "Đăng ký tại chỗ" button is hidden.
    allow_registration: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # passive_deletes=True: don't have the ORM emit UPDATE … SET exam_id = NULL
    # before the DELETE. The DB-level FKs already handle it correctly
    # (candidates.exam_id → SET NULL; exam_sessions.exam_id → CASCADE), and the
    # ORM's default clearing trips a NOT NULL constraint on exam_sessions.
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="exam", passive_deletes=True,
    )
    sessions: Mapped[list["ExamSession"]] = relationship(
        back_populates="exam", passive_deletes=True,
    )
    rooms: Mapped[list["Room"]] = relationship(
        back_populates="exam", passive_deletes=True, order_by="Room.created_at",
    )
    sittings: Mapped[list["Sitting"]] = relationship(
        back_populates="exam", passive_deletes=True, order_by="Sitting.ordinal",
    )
