"""Exam room (phòng thi) — a physical room within a kỳ thi, watched by one giám thị.

Candidates are assigned to a room (no seats/machines — removed in AD-53); a
room_proctor admin assigned to the room sees only its candidates and may
pause/resume them individually (AD-47).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, uuid_pk

if TYPE_CHECKING:
    from app.models.admin import Admin
    from app.models.candidate import Candidate
    from app.models.exam import Exam


class Room(Base, CreatedAtMixin):
    __tablename__ = "exam_rooms"

    id: Mapped[uuid.UUID] = uuid_pk()
    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # The room_proctor (giám thị) assigned to watch this room. NULL = unassigned.
    proctor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), index=True
    )
    # The REAL name of the person sitting this room for this exam (the giám thị
    # accounts are a shared fixed pool, so the human changes per exam). Stored for
    # audit/lookup; blank on a freshly created exam's rooms. (AD-49)
    proctor_real_name: Mapped[str | None] = mapped_column(String(255))
    # Max candidates the room holds. 0 = unlimited (split evenly on auto-assign).
    capacity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    exam: Mapped["Exam"] = relationship(back_populates="rooms")
    proctor: Mapped["Admin | None"] = relationship()
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="room", passive_deletes=True
    )
