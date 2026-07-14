"""Exam sitting (buổi thi) — one run of a kỳ thi with its own đề (AD-47).

A kỳ thi (Exam) is now a container: it holds the candidate roster + rooms, while
each sitting carries its OWN encrypted đề, duration, shuffle flags, answer-key
snapshot and run lifecycle. All candidates of the exam sit every sitting, but each
sitting loads a different đề. At most one sitting per exam may be ``active``.

These fields used to live on ``exams``; they moved here when sittings were added.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk
from app.models.enums import SittingStatus

if TYPE_CHECKING:
    from app.models.exam import Exam
    from app.models.session import ExamSession


class Sitting(Base, TimestampMixin):
    __tablename__ = "exam_sittings"

    id: Mapped[uuid.UUID] = uuid_pk()
    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # When this sitting is scheduled (vd "Sáng 3/6"). Coarse; timing is server-side.
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    # Display order among the exam's sittings.
    ordinal: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SittingStatus.DRAFT.value,
        server_default=SittingStatus.DRAFT.value, index=True,
    )
    # Encrypted .exam payload kept at rest; plaintext lives only in Redis when active.
    # deferred: blob đề có thể >100MB — KHÔNG được kéo theo mọi query thường
    # (login/state/list buổi). Chỗ nào cần blob thật thì dùng
    # session_service.sitting_payload_blob / sitting_has_payload (SELECT tường minh).
    encrypted_payload: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    shuffle_questions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    shuffle_options: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Persisted at QTI import so reports & list views show the right count even
    # after end-of-sitting auto-purge wipes encrypted_payload.
    question_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Answer key + original question order, written at QTI import. Reports use this
    # so the per-question summary stays in source order even after payload purge.
    # Shape: [{"id": "<uuid>", "text": "...", "correct_option": "A"}, …]
    report_snapshot: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)

    exam: Mapped["Exam"] = relationship(back_populates="sittings")
    sessions: Mapped[list["ExamSession"]] = relationship(
        back_populates="sitting", passive_deletes=True,
    )
