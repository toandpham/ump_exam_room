"""Khiếu nại của thí sinh về một câu hỏi."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _require_text(v: str, what: str) -> str:
    v = " ".join(v.split())
    if len(v) < 3:
        raise ValueError(f"{what} quá ngắn.")
    return v


class QuestionReportIn(BaseModel):
    question_id: uuid.UUID
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("content")
    @classmethod
    def _clean(cls, v: str) -> str:
        return _require_text(v, "Nội dung khiếu nại")


class QuestionReportResolveIn(BaseModel):
    resolution: str = Field(min_length=1, max_length=500)

    @field_validator("resolution")
    @classmethod
    def _clean(cls, v: str) -> str:
        return _require_text(v, "Nội dung xử lý")


class QuestionReportOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    cccd: str
    full_name: str
    room_name: str | None = None
    question_id: uuid.UUID
    # Số thứ tự câu TRONG ĐỀ CỦA THÍ SINH ĐÓ — đề trộn nên mỗi người một thứ tự.
    question_number: int
    content: str
    created_at: datetime
    resolved_at: datetime | None = None
    resolution: str | None = None
    resolved_by_name: str | None = None
