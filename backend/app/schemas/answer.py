"""Candidate answer / question-delivery / submit schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnswerIn(BaseModel):
    question_id: uuid.UUID
    selected_option: Literal["A", "B", "C", "D"] | None = None  # null clears the answer


class AnswersBulkIn(BaseModel):
    # AD-69: client gộp đáp án đẩy theo LÔ (giảm số request xuống server cho ~1000 máy).
    answers: list[AnswerIn]


class AnswersBulkOut(BaseModel):
    saved: int


class AnswerOut(BaseModel):
    question_id: uuid.UUID
    selected_option: str | None
    saved: bool = True


class ExamQuestionOption(BaseModel):
    id: str
    text: str
    images: list[str] = Field(default_factory=list)  # list of data URLs


class ExamBlock(BaseModel):
    # Khối nội dung câu hỏi CÓ THỨ TỰ (AD-98): "text" mang ``text``, "image" mang
    # ``src`` (URL). Render tuần tự để ảnh nằm đúng vị trí trong file QTI.
    type: str
    text: str = ""
    src: str = ""


class ExamQuestion(BaseModel):
    id: str
    text: str
    images: list[str] = Field(default_factory=list)  # list of data URLs
    # Nội dung theo thứ tự gốc (chữ ↔ ảnh). Rỗng = đề cũ → FE lùi về text+images.
    blocks: list[ExamBlock] = Field(default_factory=list)
    options: list[ExamQuestionOption]


class ExamQuestionsOut(BaseModel):
    status: str
    time_remaining_seconds: int | None
    total: int
    answers: dict[str, str]  # question_id -> selected_option
    questions: list[ExamQuestion]


class SubmitResult(BaseModel):
    status: str
    submitted_at: datetime | None
    answered: int
    total: int
    total_correct: int | None = None  # candidate sees correct/total only; no scaled score


class ExamResult(BaseModel):
    status: str                 # "submitted" or "timeout"
    submitted_at: datetime | None
    total: int
    answered: int
    total_correct: int
