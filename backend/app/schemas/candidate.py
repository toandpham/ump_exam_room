"""Candidate request/response schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.identifier import classify_identifier


def _validate_cccd(v: str) -> str:
    """Accept a CCCD or passport; return the normalized login value (AD-58)."""
    value, _ = classify_identifier(v)
    return value


class CandidateCreate(BaseModel):
    cccd: str
    full_name: str = Field(min_length=1, max_length=255)
    birth_date: date
    unit: str = Field(min_length=1, max_length=255)
    graduation_year: int | None = Field(default=None, ge=1900, le=2100)
    major: str | None = Field(default=None, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    attempt_number: int = Field(default=1, ge=1)
    exam_id: uuid.UUID | None = None

    _cccd = field_validator("cccd")(_validate_cccd)


class CandidateUpdate(BaseModel):
    cccd: str | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    birth_date: date | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=255)
    graduation_year: int | None = Field(default=None, ge=1900, le=2100)
    major: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    attempt_number: int | None = Field(default=None, ge=1)
    exam_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None

    @field_validator("cccd")
    @classmethod
    def _cccd(cls, v: str | None) -> str | None:
        return _validate_cccd(v) if v is not None else None


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cccd: str
    id_type: str = "cccd"
    full_name: str
    birth_date: date
    unit: str
    photo_path: str | None
    graduation_year: int | None
    major: str | None
    category: str
    attempt_number: int
    exam_id: uuid.UUID | None
    exam_name: str | None = None
    # Room assignment within the exam (AD-47); room_name set by the list endpoint.
    room_id: uuid.UUID | None = None
    room_name: str | None = None
    created_at: datetime
    updated_at: datetime


class CandidateList(BaseModel):
    items: list[CandidateOut]
    total: int
    page: int
    page_size: int


class EmergencyAddRequest(CandidateCreate):
    reason: str = Field(min_length=3, max_length=500)


# --- Bulk import ------------------------------------------------------------

class ImportPreviewRow(BaseModel):
    row_number: int
    data: dict
    errors: list[str] = []
    valid: bool


class ImportPreviewResponse(BaseModel):
    token: str
    total_rows: int
    valid_count: int
    error_count: int
    rows: list[ImportPreviewRow]
    expires_in: int


class ImportCommitRequest(BaseModel):
    token: str
    exam_id: uuid.UUID | None = None  # optionally assign all created candidates


class ImportCommitResult(BaseModel):
    created: int
    updated: int = 0   # rebinding existing record into the target section
    skipped: int
    errors: list[str] = []


class AssignExamRequest(BaseModel):
    exam_id: uuid.UUID
    candidate_ids: list[uuid.UUID] | None = None  # None => assign all candidates


class AssignExamResult(BaseModel):
    assigned: int


class ZipUploadReport(BaseModel):
    updated: int
    matched: list[str] = []
    unmatched_files: list[str] = []
    invalid_files: list[str] = []


class CandidateStats(BaseModel):
    total: int
    with_photo: int
    without_photo: int
    assigned: int
    unassigned: int
    by_unit: dict[str, int]
    by_category: dict[str, int]
