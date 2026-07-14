"""Room (phòng thi) management + seating + giám thị self-view (AD-47).

The chủ tịch (proctor) manages rooms of their own exams, assigns a giám thị
(room_proctor) to each, and arranges candidates into rooms + seats. A giám thị
uses ``GET /my-rooms`` to find which room(s) they watch.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin._http import XLSX_MEDIA, attach as _attach
from app.api.deps import exam_for_admin, require_roles
from app.core.identifier import classify_identifier
from app.core.limiter import client_ip
from app.database import get_db
from app.models import Admin, Candidate, Exam, ExamEvent, ExamSession, Room
from app.models.enums import AdminRole, EventType, ExamStatus, SessionStatus
from app.schemas.candidate import CandidateCreate
from app.schemas.room import (
    ArrangeSeatingRequest,
    MyRoomOut,
    RoomCreate,
    RoomOut,
    RoomSeat,
    RoomUpdate,
)
from app.services import seating_service, session_service

router = APIRouter()

_require_proctor = require_roles(AdminRole.PROCTOR.value)
_require_proctor_or_room = require_roles(AdminRole.PROCTOR.value, AdminRole.ROOM_PROCTOR.value)


async def _room_for_admin(db: AsyncSession, room_id: uuid.UUID, admin: Admin) -> Room:
    room = await db.get(Room, room_id)
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phòng thi")
    await exam_for_admin(db, room.exam_id, admin)  # ownership gate
    return room


async def _room_for_seating(db: AsyncSession, room_id: uuid.UUID, admin: Admin) -> Room:
    """A room the admin may seat (AD-48): a giám thị only their assigned room; a
    chủ tịch only rooms of an exam they own. Else 404 (hide existence)."""
    room = await db.get(Room, room_id)
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phòng thi")
    if admin.role == AdminRole.ROOM_PROCTOR.value:
        if room.proctor_id != admin.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phòng thi")
        return room
    await exam_for_admin(db, room.exam_id, admin)  # chủ tịch ownership gate
    return room


async def _room_out(db: AsyncSession, room: Room) -> RoomOut:
    out = RoomOut.model_validate(room)
    if room.proctor_id:
        p = await db.get(Admin, room.proctor_id)
        out.proctor_name = (p.full_name or p.username) if p else None
    out.candidate_count = int(await db.scalar(
        select(func.count(Candidate.id)).where(Candidate.room_id == room.id)
    ) or 0)
    return out


async def _assert_room_proctor(db: AsyncSession, proctor_id: uuid.UUID | None) -> None:
    if proctor_id is None:
        return
    p = await db.get(Admin, proctor_id)
    if p is None or p.role != AdminRole.ROOM_PROCTOR.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Chỉ gán được tài khoản giám thị cho phòng.")


# --- Room CRUD --------------------------------------------------------------

@router.get("/exams/{exam_id}/rooms", response_model=list[RoomOut])
async def list_rooms(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> list[RoomOut]:
    await exam_for_admin(db, exam_id, admin)
    rooms = list(await db.scalars(
        select(Room).where(Room.exam_id == exam_id).order_by(Room.created_at)
    ))
    return [await _room_out(db, r) for r in rooms]


@router.post("/exams/{exam_id}/rooms", response_model=RoomOut,
             status_code=status.HTTP_201_CREATED)
async def create_room(
    exam_id: uuid.UUID,
    body: RoomCreate,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> RoomOut:
    await exam_for_admin(db, exam_id, admin)
    await _assert_room_proctor(db, body.proctor_id)
    room = Room(exam_id=exam_id, name=body.name, proctor_id=body.proctor_id,
                capacity=body.capacity,
                proctor_real_name=(body.proctor_real_name or None))
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return await _room_out(db, room)


@router.patch("/rooms/{room_id}", response_model=RoomOut)
async def update_room(
    room_id: uuid.UUID,
    body: RoomUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> RoomOut:
    room = await _room_for_admin(db, room_id, admin)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        room.name = data["name"]
    if "capacity" in data and data["capacity"] is not None:
        room.capacity = data["capacity"]
    if "proctor_id" in data:
        await _assert_room_proctor(db, data["proctor_id"])
        room.proctor_id = data["proctor_id"]
    if "proctor_real_name" in data:
        name = (data["proctor_real_name"] or "").strip()
        room.proctor_real_name = name or None
    await db.commit()
    await db.refresh(room)
    return await _room_out(db, room)


@router.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> None:
    room = await _room_for_admin(db, room_id, admin)
    await db.delete(room)  # candidates.room_id → SET NULL
    await db.commit()


# --- Seating: chủ tịch chia PHÒNG · giám thị xếp MÁY (AD-48) ----------------

@router.post("/exams/{exam_id}/assign-rooms")
async def assign_rooms(
    exam_id: uuid.UUID,
    body: ArrangeSeatingRequest,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> dict:
    """Chủ tịch chia thí sinh vào PHÒNG (không gán ghế — ghế do giám thị xếp lúc
    thi, AD-48). Cân bằng nếu phòng chưa khai báo số máy; nếu có khai báo thì lấp
    theo capacity và 400 nếu thiếu chỗ. ``seat_number`` được xoá. Deterministic."""
    await exam_for_admin(db, exam_id, admin)
    rooms = list(await db.scalars(
        select(Room).where(Room.exam_id == exam_id).order_by(Room.created_at)
    ))
    if not rooms:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chưa có phòng thi nào để chia.")
    candidates = list(await db.scalars(
        select(Candidate).where(Candidate.exam_id == exam_id).order_by(Candidate.id)
    ))
    shuffled = session_service.deterministic_shuffle(body.seed or str(exam_id), candidates)

    placement: list[tuple[Candidate, uuid.UUID]] = []
    count: dict[uuid.UUID, int] = {r.id: 0 for r in rooms}
    room_by_id = {r.id: r for r in rooms}

    if body.counts is not None:
        # Chủ tịch tự nhập số thí sinh mỗi phòng (AD-49). Validate từng phòng ≤ sức
        # chứa (nếu khai báo) và tổng ≤ số thí sinh; phần dư để chưa xếp phòng.
        wanted: dict[uuid.UUID, int] = {}
        for rc in body.counts:
            r = room_by_id.get(rc.room_id)
            if r is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    "Phòng không thuộc kỳ thi này.")
            if r.capacity > 0 and rc.count > r.capacity:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Phòng {r.name}: {rc.count} thí sinh vượt sức chứa {r.capacity} máy.")
            wanted[rc.room_id] = rc.count
        if sum(wanted.values()) > len(shuffled):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Tổng {sum(wanted.values())} vượt số thí sinh hiện có ({len(shuffled)}).")
        idx = 0
        for r in rooms:
            n = wanted.get(r.id, 0)
            for _ in range(n):
                if idx >= len(shuffled):
                    break
                placement.append((shuffled[idx], r.id))
                idx += 1
            count[r.id] = n
    elif all(r.capacity == 0 for r in rooms):
        for i, c in enumerate(shuffled):
            r = rooms[i % len(rooms)]
            count[r.id] += 1
            placement.append((c, r.id))
    else:
        idx = 0
        for r in rooms:
            n = 0
            while idx < len(shuffled) and n < r.capacity:
                n += 1
                placement.append((shuffled[idx], r.id))
                idx += 1
            count[r.id] = n
        if idx < len(shuffled):
            total_cap = sum(r.capacity for r in rooms)
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Không đủ chỗ: {len(shuffled)} thí sinh nhưng chỉ có {total_cap} máy. "
                "Tăng 'số máy' của phòng hoặc thêm phòng.",
            )
    # Chỉ gán PHÒNG (AD-53: bỏ vị trí ngồi/ghế — không còn seat_number).
    for c in candidates:
        c.room_id = None
    for c, room_id in placement:
        c.room_id = room_id
    await db.commit()
    return {
        "total": len(shuffled),
        "rooms": [{"room_id": str(r.id), "name": r.name, "count": count[r.id]} for r in rooms],
    }


@router.get("/rooms/{room_id}/seating", response_model=list[RoomSeat])
async def room_seating(
    room_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor_or_room),
) -> list[RoomSeat]:
    """Danh sách thí sinh của 1 phòng (giám thị phòng mình hoặc chủ tịch)."""
    room = await _room_for_seating(db, room_id, admin)
    cands = list(await db.scalars(
        select(Candidate).where(Candidate.room_id == room.id)
        .order_by(Candidate.full_name)
    ))
    return [
        RoomSeat(candidate_id=c.id, full_name=c.full_name, cccd=c.cccd,
                 id_type=c.id_type, unit=c.unit, birth_date=c.birth_date)
        for c in cands
    ]


@router.post("/rooms/{room_id}/candidates", response_model=RoomSeat,
             status_code=status.HTTP_201_CREATED)
async def add_room_candidate(
    room_id: uuid.UUID,
    body: CandidateCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor_or_room),
) -> RoomSeat:
    """Giám thị (phòng mình) hoặc chủ tịch thêm 1 thí sinh lẻ THẲNG vào phòng — kể
    cả khi kỳ thi đang chạy (walk-in). Khác import hàng loạt của chủ tịch (AD-54)."""
    room = await _room_for_seating(db, room_id, admin)
    if await db.scalar(select(Candidate.id).where(Candidate.cccd == body.cccd)):
        raise HTTPException(status.HTTP_409_CONFLICT, "CCCD đã tồn tại")
    cand = Candidate(
        cccd=body.cccd, id_type=classify_identifier(body.cccd)[1],
        full_name=body.full_name, birth_date=body.birth_date,
        unit=body.unit, graduation_year=body.graduation_year, major=body.major,
        category=body.category, attempt_number=body.attempt_number,
        exam_id=room.exam_id, room_id=room.id,
    )
    db.add(cand)
    await db.flush()
    db.add(ExamEvent(
        session_id=None, cccd_attempted=body.cccd, client_ip=client_ip(request),
        event_type=EventType.EMERGENCY_ADD.value,
        event_metadata={"by": admin.username, "room": room.name,
                        "candidate_id": str(cand.id), "exam_id": str(room.exam_id)},
    ))
    await db.commit()
    await db.refresh(cand)
    return RoomSeat(candidate_id=cand.id, full_name=cand.full_name, cccd=cand.cccd,
                    id_type=cand.id_type, unit=cand.unit, birth_date=cand.birth_date)


async def _seating_payload(db: AsyncSession, exam: Exam) -> list[dict]:
    rooms = list(await db.scalars(
        select(Room).where(Room.exam_id == exam.id).order_by(Room.created_at)
    ))
    out = []
    for r in rooms:
        proctor = await db.get(Admin, r.proctor_id) if r.proctor_id else None
        cands = list(await db.scalars(
            select(Candidate).where(Candidate.room_id == r.id)
            .order_by(Candidate.full_name)
        ))
        # Prefer the real assigned name (audit); fall back to the account label.
        proctor_label = r.proctor_real_name or (
            (proctor.full_name or proctor.username) if proctor else None)
        out.append({
            "room_name": r.name,
            "proctor_name": proctor_label,
            "candidates": [
                {"full_name": c.full_name, "cccd": c.cccd, "unit": c.unit}
                for c in cands
            ],
        })
    return out


@router.get("/exams/{exam_id}/seating.xlsx")
async def seating_xlsx(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> Response:
    exam = await exam_for_admin(db, exam_id, admin)
    data = await _seating_payload(db, exam)
    content = seating_service.export_excel(exam.name, data)
    base = f"DanhSachPhong - {exam.name}".strip()
    return Response(content=content, media_type=XLSX_MEDIA,
                    headers={"Content-Disposition": _attach(f"{base}.xlsx")})


@router.get("/exams/{exam_id}/seating.pdf")
async def seating_pdf(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> Response:
    exam = await exam_for_admin(db, exam_id, admin)
    data = await _seating_payload(db, exam)
    content = seating_service.export_pdf(exam.name, data)
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="seating_{exam_id}.pdf"'})


# --- Giám thị self-view -----------------------------------------------------

@router.get("/my-rooms", response_model=list[MyRoomOut])
async def my_rooms(
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor_or_room),
) -> list[MyRoomOut]:
    """Rooms the current admin watches. For a giám thị (room_proctor) these are
    the rooms assigned to them; for a chủ tịch, the rooms of their own exams.
    Rooms of CLOSED (archived) exams are hidden — they would pile up forever
    since the giám thị pool accounts are reused across kỳ thi."""
    if admin.role == AdminRole.ROOM_PROCTOR.value:
        rooms = list(await db.scalars(
            select(Room).join(Exam, Exam.id == Room.exam_id)
            .where(Room.proctor_id == admin.id,
                   Exam.status != ExamStatus.CLOSED.value)
            .order_by(Room.created_at)
        ))
    else:
        rooms = list(await db.scalars(
            select(Room).join(Exam, Exam.id == Room.exam_id)
            .where((Exam.created_by == admin.id) | (Exam.created_by.is_(None)),
                   Exam.status != ExamStatus.CLOSED.value)
            .order_by(Room.created_at)
        ))
    now = datetime.now(timezone.utc)
    out: list[MyRoomOut] = []
    for r in rooms:
        exam = await db.get(Exam, r.exam_id)
        if exam is None:
            continue
        active = await session_service.get_active_sitting(db, exam.id)
        count = int(await db.scalar(
            select(func.count(Candidate.id)).where(Candidate.room_id == r.id)) or 0)
        # Đồng hồ thi CHUNG (AD-78): deadline sớm nhất của các phiên đang làm trong
        # buổi active — giống hệt roster của chủ tịch nên 2 màn hiện cùng 1 giờ.
        cohort_end_time = None
        if active is not None:
            cohort_end_time = await db.scalar(
                select(func.min(ExamSession.end_time)).where(
                    ExamSession.sitting_id == active.id,
                    ExamSession.status == SessionStatus.IN_PROGRESS.value,
                    ExamSession.end_time.is_not(None),
                )
            )
        out.append(MyRoomOut(
            room_id=r.id, room_name=r.name, exam_id=exam.id, exam_name=exam.name,
            exam_status=exam.status,
            active_sitting_id=active.id if active else None,
            candidate_count=count,
            cohort_end_time=cohort_end_time,
            server_time=now,
        ))
    return out
