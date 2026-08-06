"""Schemas for exam control + monitoring + security report."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ExtendRequest(BaseModel):
    minutes: int = Field(ge=1, le=180)


class TerminateRequest(BaseModel):
    """Đình chỉ thi một thí sinh. Lý do BẮT BUỘC — đây là quyết định kỷ luật, hội
    đồng phải tra lại được vì sao; ``min_length`` sau khi cắt khoảng trắng."""
    reason: str = Field(min_length=3, max_length=255)

    @field_validator("reason")
    @classmethod
    def _trim(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("Lý do đình chỉ quá ngắn.")
        return v


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
    # Đang tạm dừng VÀ đồng hồ đã trôi qua end_time. Vòng quét tự nộp cố ý bỏ qua
    # phiên tạm dừng (không nộp thay người đang bị dừng), nên nếu không ai bấm Tiếp
    # tục thì phiên nằm đó mãi. Cờ này để bảng giám sát làm nó nổi lên thay vì im
    # lặng treo (lỗ AD-121 #2).
    overdue_paused: bool = False
    # Lý do chủ tịch đình chỉ thi (khi status = "terminated").
    terminated_reason: str | None = None
    room_id: uuid.UUID | None = None
    room_name: str | None = None
    # AD-122: thí sinh đã bấm "Báo giám thị" (sai thông tin) và CHƯA được sửa.
    info_disputed: bool = False
    # AD-122: máy thí sinh im lặng quá OFFLINE_ALERT_SECONDS (90s) — mất kết nối
    # THẬT chứ không phải chớp mạng. Chỉ tính khi phiên còn đang cần online.
    offline: bool = False
    last_seen_seconds: int | None = None
    # AD-110: máy đã tải xong toàn bộ ảnh đề (cờ Redis do máy thí sinh báo về) —
    # chủ tịch chỉ nên Bắt đầu thi khi mọi máy ready đều True.
    preloaded: bool = False
    # Tiến độ làm bài: đã trả lời bao nhiêu / đã xem tới câu thứ mấy / tổng số câu
    # trong đề của thí sinh này. Trước đây bảng giám sát không có con số nào cả,
    # mà đây lại là thứ chủ tịch hỏi nhiều nhất.
    answered_count: int = 0
    viewed_count: int | None = None
    question_total: int = 0
    # Số khiếu nại câu hỏi CHƯA xử lý của thí sinh này. Giám thị không có danh sách
    # (giữ đúng phạm vi quyền AD-124) nhưng phải thấy được em nào vừa báo lỗi.
    open_question_reports: int = 0


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
    info_disputed: bool = False


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
    # Mốc đếm ngược ở màn giám sát (AD-78). Đồng hồ là per-candidate nên không có
    # deadline chung: ``earliest`` = người xong sớm nhất, ``latest`` = người xong
    # muộn nhất (vào trễ / được cộng giờ riêng). Cả hai đều BỎ QUA phiên đang tạm
    # dừng — đồng hồ của họ đóng băng nên end_time không phản ánh thời gian thực
    # của ai cả (lỗ AD-121 #3). server_time để máy admin bù lệch đồng hồ.
    earliest_end_time: datetime | None = None
    latest_end_time: datetime | None = None
    server_time: datetime | None = None


class SecurityEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    cccd_attempted: str | None
    client_ip: str | None
    created_at: datetime
    metadata: dict | None
