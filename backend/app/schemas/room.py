"""Room (phòng thi) + seating schemas (AD-47)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    proctor_id: uuid.UUID | None = None
    capacity: int = Field(default=0, ge=0, le=500)
    proctor_real_name: str | None = Field(default=None, max_length=255)


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    # Send proctor_id: null explicitly to unassign; omit the key to leave it
    # unchanged (the endpoint uses exclude_unset to tell the two apart).
    proctor_id: uuid.UUID | None = None
    capacity: int | None = Field(default=None, ge=0, le=500)
    # Real name of the giám thị sitting this room (AD-49). "" / null clears it.
    proctor_real_name: str | None = Field(default=None, max_length=255)


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exam_id: uuid.UUID
    name: str
    proctor_id: uuid.UUID | None
    capacity: int = 0
    proctor_real_name: str | None = None
    # Set by the endpoint, not the ORM.
    proctor_name: str | None = None
    candidate_count: int = 0


class RoomProctorCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6, max_length=200)
    full_name: str | None = Field(default=None, max_length=255)


class RoomCount(BaseModel):
    room_id: uuid.UUID
    count: int = Field(ge=0)


class ArrangeSeatingRequest(BaseModel):
    # Optional deterministic seed; defaults to the exam id so re-running is stable.
    seed: str | None = None
    # Explicit per-room counts (chủ tịch tự nhập số thí sinh mỗi phòng, AD-49).
    # Omit → auto even/capacity-fill (legacy). Each ≤ room capacity (if >0),
    # sum ≤ total candidates; leftovers stay unassigned.
    counts: list[RoomCount] | None = None


class RoomSeat(BaseModel):
    """A candidate in a room (giám thị roster view)."""
    candidate_id: uuid.UUID
    full_name: str
    cccd: str
    id_type: str = "cccd"          # 'cccd' | 'passport' (AD-58)
    unit: str = ""                 # Đơn vị — helps the proctor verify papers
    birth_date: date | None = None


class MyRoomOut(BaseModel):
    room_id: uuid.UUID
    room_name: str
    exam_id: uuid.UUID
    exam_name: str
    exam_status: str
    active_sitting_id: uuid.UUID | None = None
    candidate_count: int = 0
    # Đồng hồ thi CHUNG (AD-78): deadline sớm nhất của các phiên đang làm trong buổi
    # active (cả phòng bắt đầu cùng lúc → chung 1 mốc) + giờ server để neo đếm ngược.
    cohort_end_time: datetime | None = None
    server_time: datetime | None = None
