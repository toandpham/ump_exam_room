"""Dự phòng giấy: kết quả đọc phiếu + yêu cầu ghi vào CSDL."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class PaperSheetRead(BaseModel):
    """Một tờ đã quét, ĐÃ ĐỌC nhưng CHƯA ghi vào CSDL."""
    page_in_file: int
    candidate_index: int | None = None
    candidate_id: uuid.UUID | None = None
    cccd: str = ""
    full_name: str = ""
    sheet_page: int | None = None
    # {"chỉ số câu (0-based)": "A"} — chuỗi vì JSON không có khoá kiểu số.
    answers: dict[str, str] = Field(default_factory=dict)
    # Câu máy không dám quyết (tô hai ô, tô quá mờ) — người phải xem lại.
    unsure: list[int] = Field(default_factory=list)
    error: str | None = None


class PaperScanResult(BaseModel):
    total_sheets: int
    sheets: list[PaperSheetRead]


class PaperApplyEntry(BaseModel):
    candidate_id: uuid.UUID
    # Chủ tịch xác nhận (có thể đã sửa tay) — khoá là chỉ số câu 0-based.
    answers: dict[int, str]


class PaperApplyIn(BaseModel):
    sheets: list[PaperApplyEntry]
