"""Quản lý thí sinh: gán kỳ thi, thống kê, export, emergency-add, CRUD đơn lẻ (AD-75)."""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin._http import XLSX_MEDIA
from app.api.deps import exam_for_admin, get_current_admin, require_roles
from app.core.image_processor import (
    ImageValidationError,
    delete_upload,
    save_candidate_photo,
)
from app.core.identifier import classify_identifier
from app.core.limiter import client_ip
from app.database import get_db
from app.models import Admin, Candidate, Exam, ExamEvent, Room
from app.models.enums import AdminRole, EventType
from app.schemas.candidate import (
    AssignExamRequest,
    AssignExamResult,
    CandidateCreate,
    CandidateList,
    CandidateOut,
    CandidateStats,
    CandidateUpdate,
    EmergencyAddRequest,
)
from app.services import excel_service

from ._common import _assert_unlocked, _candidate_for_admin, _exam_is_active, _to_out

router = APIRouter()


# --- assignment / stats / export -------------------------------------------

@router.post("/assign-exam", response_model=AssignExamResult)
async def assign_exam(
    body: AssignExamRequest,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> AssignExamResult:
    await exam_for_admin(db, body.exam_id, admin)  # ownership gate (AD-30)
    # AD-47: exams stay "active" their whole life — the real lock is whether a
    # bài thi is running (same semantics as import_commit).
    if await _exam_is_active(db, body.exam_id):
        raise HTTPException(status.HTTP_423_LOCKED, "Thí sinh đang làm bài — không thể đổi gán.")
    stmt = update(Candidate).values(exam_id=body.exam_id)
    if body.candidate_ids is not None:
        # Explicit selection (incl. [] => no-op). AD-55 I1: previously `if list:`
        # treated [] like None and reassigned EVERY candidate in the DB.
        stmt = stmt.where(Candidate.id.in_(body.candidate_ids))
    elif admin.role == AdminRole.PROCTOR.value:
        # "Assign all": a chủ tịch must not steal candidates out of OTHER
        # proctors' exams (AD-30) — only unassigned ones or those in exams they own.
        owned = select(Exam.id).where(
            (Exam.created_by == admin.id) | (Exam.created_by.is_(None))
        )
        stmt = stmt.where(
            Candidate.exam_id.is_(None) | Candidate.exam_id.in_(owned)
        )
    result = await db.execute(stmt)
    await db.commit()
    return AssignExamResult(assigned=result.rowcount or 0)


@router.get("/stats", response_model=CandidateStats)
async def candidate_stats(
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> CandidateStats:
    total = await db.scalar(select(func.count()).select_from(Candidate)) or 0
    with_photo = await db.scalar(
        select(func.count()).select_from(Candidate).where(Candidate.photo_path.is_not(None))
    ) or 0
    assigned = await db.scalar(
        select(func.count()).select_from(Candidate).where(Candidate.exam_id.is_not(None))
    ) or 0
    by_unit = dict(
        (await db.execute(select(Candidate.unit, func.count()).group_by(Candidate.unit))).all()
    )
    by_category = dict(
        (await db.execute(select(Candidate.category, func.count()).group_by(Candidate.category))).all()
    )
    return CandidateStats(
        total=total,
        with_photo=with_photo,
        without_photo=total - with_photo,
        assigned=assigned,
        unassigned=total - assigned,
        by_unit=by_unit,
        by_category=by_category,
    )


@router.get("/export.xlsx")
async def export_candidates(
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
    exam_id: uuid.UUID | None = Query(default=None),
    unit: str | None = Query(default=None),
    category: str | None = Query(default=None),
) -> Response:
    filters = []
    if exam_id is not None:
        await exam_for_admin(db, exam_id, admin)  # ownership gate (AD-30)
        filters.append(Candidate.exam_id == exam_id)
    if unit:
        filters.append(Candidate.unit.ilike(f"%{unit}%"))
    if category:
        filters.append(Candidate.category.ilike(f"%{category}%"))
    result = await db.execute(
        select(Candidate, Exam.name, Room.name)
        .outerjoin(Exam, Exam.id == Candidate.exam_id)
        .outerjoin(Room, Room.id == Candidate.room_id)
        .where(*filters)
        .order_by(Candidate.full_name)
    )
    rows = [
        {
            "cccd": c.cccd, "full_name": c.full_name, "birth_date": c.birth_date.isoformat(),
            "unit": c.unit, "graduation_year": c.graduation_year, "major": c.major,
            "category": c.category, "attempt_number": c.attempt_number,
            "room_name": rname, "exam_name": ename, "photo_path": c.photo_path,
        }
        for c, ename, rname in result.all()
    ]
    return Response(
        content=excel_service.export_candidates(rows),
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="candidates.xlsx"'},
    )


# --- emergency add (super_admin) -------------------------------------------

@router.post("/emergency-add", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
async def emergency_add(
    body: EmergencyAddRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(require_roles(AdminRole.SUPER_ADMIN.value)),
) -> CandidateOut:
    if await db.scalar(select(Candidate.id).where(Candidate.cccd == body.cccd)):
        raise HTTPException(status.HTTP_409_CONFLICT, "CCCD đã tồn tại")
    candidate = Candidate(**body.model_dump(exclude={"reason"}))
    candidate.id_type = classify_identifier(body.cccd)[1]
    db.add(candidate)
    await db.flush()
    db.add(ExamEvent(
        session_id=None,
        cccd_attempted=body.cccd,
        client_ip=client_ip(request),
        event_type=EventType.EMERGENCY_ADD.value,
        event_metadata={
            "reason": body.reason,
            "admin": admin.username,
            "candidate_id": str(candidate.id),
            "exam_id": str(body.exam_id) if body.exam_id else None,
        },
    ))
    await db.commit()
    await db.refresh(candidate)
    return await _to_out(db, candidate)


# --- single CRUD ------------------------------------------------------------

@router.post("", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    body: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> CandidateOut:
    if body.exam_id is not None:
        await exam_for_admin(db, body.exam_id, admin)  # ownership gate (AD-30/I2)
    if await db.scalar(select(Candidate.id).where(Candidate.cccd == body.cccd)):
        raise HTTPException(status.HTTP_409_CONFLICT, "CCCD đã tồn tại")
    if await _exam_is_active(db, body.exam_id):
        raise HTTPException(status.HTTP_423_LOCKED, "Kỳ thi đang diễn ra — dùng Emergency Add.")
    candidate = Candidate(**body.model_dump())
    candidate.id_type = classify_identifier(body.cccd)[1]
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return await _to_out(db, candidate)


@router.get("", response_model=CandidateList)
async def list_candidates(
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
    cccd: str | None = Query(default=None),
    full_name: str | None = Query(default=None),
    unit: str | None = Query(default=None),
    category: str | None = Query(default=None),
    attempt_number: int | None = Query(default=None),
    has_photo: bool | None = Query(default=None),
    exam_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> CandidateList:
    filters = []
    if cccd:
        filters.append(Candidate.cccd.ilike(f"%{cccd}%"))
    if full_name:
        filters.append(Candidate.full_name.ilike(f"%{full_name}%"))
    if unit:
        filters.append(Candidate.unit.ilike(f"%{unit}%"))
    if category:
        filters.append(Candidate.category.ilike(f"%{category}%"))
    if attempt_number is not None:
        filters.append(Candidate.attempt_number == attempt_number)
    # AD-69: danh sách thí sinh PHẢI theo kỳ thi — không cho liệt kê toàn DB. Gắn
    # luôn ownership gate (AD-30): proctor chỉ thấy thí sinh kỳ thi mình sở hữu.
    if exam_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Thiếu exam_id — danh sách thí sinh phải theo kỳ thi.",
        )
    await exam_for_admin(db, exam_id, admin)
    filters.append(Candidate.exam_id == exam_id)
    if has_photo is True:
        filters.append(Candidate.photo_path.is_not(None))
    elif has_photo is False:
        filters.append(Candidate.photo_path.is_(None))

    total = await db.scalar(
        select(func.count()).select_from(Candidate).where(*filters)
    ) or 0
    result = await db.execute(
        select(Candidate, Exam.name)
        .outerjoin(Exam, Exam.id == Candidate.exam_id)
        .where(*filters)
        .order_by(Candidate.full_name)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    items: list[CandidateOut] = []
    for candidate, exam_name in result.all():
        out = CandidateOut.model_validate(candidate)
        out.exam_name = exam_name
        items.append(out)
    return CandidateList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> CandidateOut:
    candidate = await _candidate_for_admin(db, candidate_id, admin)
    return await _to_out(db, candidate)


@router.patch("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: uuid.UUID,
    body: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> CandidateOut:
    candidate = await _candidate_for_admin(db, candidate_id, admin)
    # NOTE: personal-info edits (name/birth_date/unit/…) ARE allowed while the
    # exam is active — that's how a proctor fixes a candidate who pressed "Báo
    # giám thị" on exam day. Only re-assigning into a DIFFERENT active exam is
    # blocked (below). The session is keyed by candidate_id, so editing fields
    # (even CCCD) doesn't disturb an in-progress session.
    data = body.model_dump(exclude_unset=True)
    if "cccd" in data and data["cccd"] != candidate.cccd:
        if await db.scalar(select(Candidate.id).where(Candidate.cccd == data["cccd"])):
            raise HTTPException(status.HTTP_409_CONFLICT, "CCCD đã tồn tại")
        candidate.id_type = classify_identifier(data["cccd"])[1]   # keep type in sync
    if "exam_id" in data and data["exam_id"] != candidate.exam_id:
        if data["exam_id"] is not None:
            await exam_for_admin(db, data["exam_id"], admin)  # own the TARGET too (I2)
        if await _exam_is_active(db, data["exam_id"]):
            raise HTTPException(status.HTTP_423_LOCKED, "Không thể gán vào kỳ thi đang diễn ra.")
    # A manually-assigned room must belong to the candidate's exam (AD-47).
    if data.get("room_id") is not None:
        from app.models import Room
        room = await db.get(Room, data["room_id"])
        target_exam = data.get("exam_id", candidate.exam_id)
        if room is None or room.exam_id != target_exam:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Phòng không thuộc kỳ thi của thí sinh.")
    for field, value in data.items():
        setattr(candidate, field, value)
    await db.commit()
    await db.refresh(candidate)
    return await _to_out(db, candidate)


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> None:
    candidate = await _candidate_for_admin(db, candidate_id, admin)
    await _assert_unlocked(db, candidate)
    photo = candidate.photo_path
    await db.delete(candidate)
    await db.commit()
    delete_upload(photo)


@router.post("/{candidate_id}/photo", response_model=CandidateOut)
async def upload_candidate_photo(
    candidate_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> CandidateOut:
    candidate = await _candidate_for_admin(db, candidate_id, admin)
    await _assert_unlocked(db, candidate)
    content = await file.read()
    try:
        candidate.photo_path = save_candidate_photo(content, candidate.cccd)
    except ImageValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await db.commit()
    await db.refresh(candidate)
    return await _to_out(db, candidate)
