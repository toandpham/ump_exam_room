"""Schemas for exam control + monitoring + security report."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ExtendRequest(BaseModel):
    minutes: int = Field(ge=1, le=180)


class StartResult(BaseModel):
    started: int
    end_time: datetime | None


class EndResult(BaseModel):
    submitted: int


class SessionSummary(BaseModel):
    session_id: uuid.UUID
    candidate_id: uuid.UUID
    cccd: str
    full_name: str
    unit: str
    category: str
    attempt_number: int
    photo_path: str | None
    status: str
    started_at: datetime | None
    submitted_at: datetime | None
    end_time: datetime | None = None
    score: float | None
    total_correct: int | None
    client_ip: str | None
    device_id: str | None = None
    self_registered: bool = False
    # Per-candidate pause + room assignment (AD-47).
    paused: bool = False
    room_id: uuid.UUID | None = None
    room_name: str | None = None
    # AD-110: máy đã tải xong toàn bộ ảnh đề (cờ Redis do máy thí sinh báo về) —
    # chủ tịch chỉ nên Bắt đầu thi khi mọi máy ready đều True.
    preloaded: bool = False


class RosterCandidate(BaseModel):
    candidate_id: uuid.UUID
    cccd: str
    full_name: str
    unit: str
    category: str
    attempt_number: int
    photo_path: str | None
    self_registered: bool = False
    room_name: str | None = None


class RosterSitting(BaseModel):
    """Header for the monitor — describes the SITTING being watched (AD-47)."""
    sitting_id: uuid.UUID
    exam_id: uuid.UUID
    exam_name: str
    sitting_name: str
    exam_date: str | None
    duration_minutes: int
    status: str
    question_count: int


class RosterResponse(BaseModel):
    sitting: RosterSitting
    assigned_total: int
    logged_in: int
    not_logged_in_total: int
    not_logged_in: list[RosterCandidate]
    # Earliest end_time among running candidates (đồng hồ per-candidate nên không
    # có deadline chung — dùng làm mốc đếm ngược ở màn giám sát, AD-78).
    # server_time để máy admin bù lệch đồng hồ khi đếm ngược.
    earliest_end_time: datetime | None = None
    server_time: datetime | None = None


class SecurityEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    cccd_attempted: str | None
    client_ip: str | None
    created_at: datetime
    metadata: dict | None
