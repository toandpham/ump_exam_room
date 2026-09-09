"""Exam session model — one candidate sitting one exam."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, uuid_pk
from app.models.enums import SessionStatus

if TYPE_CHECKING:
    from app.models.answer import Answer
    from app.models.candidate import Candidate
    from app.models.exam import Exam
    from app.models.sitting import Sitting


class ExamSession(Base):
    __tablename__ = "exam_sessions"
    # One session per candidate per sitting (buổi). A candidate sits every sitting
    # of the exam, each producing its own session/answers/score (AD-47).
    __table_args__ = (
        UniqueConstraint("candidate_id", "sitting_id", name="uq_session_candidate_sitting"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The sitting (buổi) this session belongs to — carries the đề + timing (AD-47).
    sitting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_sittings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalised exam id (= sitting.exam_id), kept for cheap ownership/room
    # filtering on hot paths without a join.
    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Per-candidate deterministic shuffle, seeded by session id.
    question_order: Mapped[list[str] | None] = mapped_column(JSONB)
    option_order: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SessionStatus.WAITING.value,
        server_default=SessionStatus.WAITING.value, index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Per-candidate pause (AD-47). Set when a proctor/giám thị pauses THIS
    # candidate: their timer freezes at this instant, the candidate UI shows a
    # "tạm dừng" overlay, and answer/submit are blocked. Resume shifts this
    # session's end_time forward by (now - paused_at) and clears it to NULL.
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    total_correct: Mapped[int | None] = mapped_column(Integer)
    # SHA-256 over the canonical result fields — see ``session_service.compute_results_hash``.
    # Lets the system detect any tampering with score/total_correct/answers after submit.
    results_hash: Mapped[str | None] = mapped_column(String(64))
    client_ip: Mapped[str | None] = mapped_column(String(45))
    # Random per-browser id from localStorage (X-Device-Id header) — used to
    # detect two candidates sitting at the same browser/machine (AD-29).
    device_id: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    candidate: Mapped["Candidate"] = relationship(back_populates="sessions")
    exam: Mapped["Exam"] = relationship(back_populates="sessions")
    sitting: Mapped["Sitting"] = relationship(back_populates="sessions")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
