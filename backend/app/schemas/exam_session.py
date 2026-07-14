"""Candidate-facing exam session schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class CCCDLogin(BaseModel):
    cccd: str = Field(min_length=1, max_length=20)
    # Set true to take over an existing live session on another device.
    force: bool = False


class RegisterRequest(BaseModel):
    cccd: str = Field(min_length=6, max_length=20)   # CCCD (12 digits) or passport (AD-58)
    full_name: str = Field(min_length=1, max_length=255)
    birth_date: date
    unit: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    attempt_number: int = Field(default=1, ge=1, le=99)
    graduation_year: int | None = Field(default=None, ge=1900, le=2100)
    major: str | None = Field(default=None, max_length=255)
    exam_id: uuid.UUID | None = None    # admin shortcut; normally inferred from the one active section


class ActiveExamInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    exam_date: date | None
    duration_minutes: int
    allow_registration: bool = True


class ExamRunningStatus(BaseModel):
    """Whether candidates can log in right now: an active exam with an OPEN sitting
    (buổi đang mở). The exam app shows the login form only when ``open`` is true,
    otherwise a "no exam in progress" screen (AD-61)."""
    open: bool = False
    exam_name: str | None = None
    allow_registration: bool = False


class CandidateInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    cccd: str
    id_type: str = "cccd"
    full_name: str
    birth_date: date
    unit: str
    major: str | None
    category: str
    attempt_number: int
    photo_path: str | None


class ExamInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    duration_minutes: int
    exam_date: date | None


class CandidateLoginResponse(BaseModel):
    token: str | None = None
    candidate: CandidateInfo
    exam: ExamInfo | None = None
    session_status: str | None = None  # existing session status, or null if none yet
    # When the CCCD is already live on another device, login returns no token but
    # requires_takeover=true so the client can ask the user to confirm taking over.
    requires_takeover: bool = False
    active_device_ip: str | None = None


class SessionStateOut(BaseModel):
    session_id: uuid.UUID | None
    status: str | None
    started_at: datetime | None
    end_time: datetime | None
    submitted_at: datetime | None
    server_time: datetime
    time_remaining_seconds: int | None
    paused: bool = False    # True when proctor has frozen the exam — candidate UI shows overlay
