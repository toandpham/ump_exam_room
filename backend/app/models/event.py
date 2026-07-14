"""Exam event / audit + security log.

Records both failed-login security events (session_id NULL) and per-session
audit-trail events.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class ExamEvent(Base):
    __tablename__ = "exam_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Nullable: failed logins happen before any session exists.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exam_sessions.id", ondelete="SET NULL"), index=True
    )
    cccd_attempted: Mapped[str | None] = mapped_column(String(12), index=True)
    client_ip: Mapped[str | None] = mapped_column(String(45))
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Mapped to column "metadata"; attribute renamed to avoid clashing with Base.metadata.
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
