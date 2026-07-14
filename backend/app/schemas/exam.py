"""Exam request/response schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SittingDraft(BaseModel):
    """One buổi thi declared up front in the create-exam wizard (AD-47)."""
    name: str = Field(min_length=1, max_length=255)
    scheduled_date: date | None = None
    duration_minutes: int | None = Field(default=None, gt=0, le=600)


class ExamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    # Default duration prefilled when creating a sitting (AD-47); the đề + its
    # authoritative duration live on each sitting.
    duration_minutes: int = Field(gt=0, le=600)
    exam_date: date | None = None
    allow_registration: bool = True
    # Initial structure declared in the wizard. The endpoint generates this many
    # rooms ("Phòng 1..N", each holding up to room_capacity candidates) + these buổi.
    # Empty/omitted → one default of each (keeps API callers + tests working).
    room_count: int = Field(default=1, ge=1, le=50)
    room_capacity: int = Field(default=0, ge=0, le=500)  # max thí sinh/phòng (0 = không giới hạn)
    sittings: list[SittingDraft] = Field(default_factory=list, max_length=50)


class ExamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    duration_minutes: int
    exam_date: date | None
    status: str
    # Total questions across the exam's sittings, and how many sittings exist —
    # đề is per-sitting now (AD-47). Set by the list/get endpoint, not the ORM.
    question_count: int = 0
    sitting_count: int = 0
    # True when at least one candidate session is currently IN_PROGRESS.
    has_running_sessions: bool = False
    allow_registration: bool = True
    # Username (or full name) of the proctor who created/owns this exam (AD-30).
    # None for legacy exams with no owner. Set by the list endpoint, not the ORM.
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime
