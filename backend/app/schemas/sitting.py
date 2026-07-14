"""Sitting (buổi thi) request/response schemas (AD-47)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SittingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    scheduled_date: date | None = None
    duration_minutes: int = Field(gt=0, le=600)


class SittingUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    scheduled_date: date | None = None
    duration_minutes: int | None = Field(default=None, gt=0, le=600)


class SittingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exam_id: uuid.UUID
    name: str
    description: str | None
    scheduled_date: date | None
    ordinal: int
    duration_minutes: int
    status: str
    shuffle_questions: bool
    shuffle_options: bool
    question_count: int = 0
    # Derived (set by the endpoint, not the ORM): đề loaded? any running session?
    has_payload: bool = False
    has_running_sessions: bool = False
    created_at: datetime
    updated_at: datetime
