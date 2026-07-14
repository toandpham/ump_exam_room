"""Import hàng loạt: template Excel, preview/commit, upload ảnh ZIP (AD-75)."""

import io
import json
import os
import uuid
import zipfile
from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin._http import XLSX_MEDIA
from app.api.deps import exam_for_admin, get_current_admin
from app.core.image_processor import ImageValidationError, save_candidate_photo
from app.core.identifier import classify_identifier
from app.core.redis import redis_client
from app.database import get_db
from app.models import Admin, Candidate, Room
from app.models.enums import SessionStatus
from app.schemas.candidate import (
    ImportCommitRequest,
    ImportCommitResult,
    ImportPreviewResponse,
    ImportPreviewRow,
    ZipUploadReport,
)
from app.services import excel_service

from ._common import _exam_is_active

router = APIRouter()

IMPORT_TTL = 1800  # seconds a parsed-import preview stays valid in Redis


# --- template / import ------------------------------------------------------

@router.get("/template.xlsx")
async def download_template(_: Admin = Depends(get_current_admin)) -> Response:
    return Response(
        content=excel_service.build_template(),
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="candidate_template.xlsx"'},
    )


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def import_preview(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> ImportPreviewResponse:
    content = await file.read()
    try:
        raw_rows = excel_service.parse_rows(content)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không đọc được file Excel (.xlsx)")

    parsed = [(rn, *excel_service.validate_row(vals)) for rn, vals in raw_rows]

    # File-internal duplicate CCCDs.
    cccd_rows: dict[str, list[int]] = {}
    for rn, data, _errs in parsed:
        if data["cccd"]:
            cccd_rows.setdefault(data["cccd"], []).append(rn)
    dup_cccds = {c for c, rs in cccd_rows.items() if len(rs) > 1}

    # CCCDs already in the database — only the ones currently tied to an
    # active section are real conflicts. Existing records in draft / closed
    # sections (or unassigned) can be re-bound to the new section at commit.
    all_cccds = [d["cccd"] for _, d, _ in parsed if d["cccd"]]
    existing_active_cccds: set[str] = set()
    existing_movable_cccds: set[str] = set()
    if all_cccds:
        from app.models.session import ExamSession  # local — avoid cycles
        in_progress_exam_ids = set(await db.scalars(
            select(ExamSession.exam_id).where(
                ExamSession.status == SessionStatus.IN_PROGRESS.value,
            ).distinct()
        ))
        rows = await db.execute(
            select(Candidate.cccd, Candidate.exam_id)
            .where(Candidate.cccd.in_(all_cccds))
        )
        for cccd, exam_id in rows.all():
            if exam_id is not None and exam_id in in_progress_exam_ids:
                existing_active_cccds.add(cccd)
            else:
                existing_movable_cccds.add(cccd)

    preview_rows: list[ImportPreviewRow] = []
    valid_data: list[dict] = []
    for rn, data, errors in parsed:
        errs = list(errors)
        if data["cccd"] in dup_cccds:
            errs.append("CCCD bị trùng trong file")
        if data["cccd"] in existing_active_cccds:
            errs.append("CCCD đang dự một kỳ thi khác — không thể chuyển khi đang làm bài")
        # CCCDs in existing_movable_cccds are OK — commit will rebind to the new section.
        is_valid = not errs
        preview_rows.append(
            ImportPreviewRow(row_number=rn, data=data, errors=errs, valid=is_valid)
        )
        if is_valid:
            valid_data.append(data)

    token = uuid.uuid4().hex
    await redis_client.setex(f"import:{token}", IMPORT_TTL, json.dumps(valid_data))
    return ImportPreviewResponse(
        token=token,
        total_rows=len(parsed),
        valid_count=len(valid_data),
        error_count=len(parsed) - len(valid_data),
        rows=preview_rows,
        expires_in=IMPORT_TTL,
    )


@router.post("/import/commit", response_model=ImportCommitResult)
async def import_commit(
    body: ImportCommitRequest,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> ImportCommitResult:
    raw = await redis_client.get(f"import:{body.token}")
    if raw is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Phiên import đã hết hạn hoặc không tồn tại. Vui lòng preview lại.",
        )
    rows: list[dict] = json.loads(raw)

    if body.exam_id is not None:
        await exam_for_admin(db, body.exam_id, admin)  # ownership gate (AD-30)
        if await _exam_is_active(db, body.exam_id):
            raise HTTPException(status.HTTP_423_LOCKED, "Thí sinh đang làm bài — không thể import thêm.")

    created = updated = skipped = 0
    errors: list[str] = []
    cccds = [r["cccd"] for r in rows]
    existing_map: dict[str, Candidate] = {}
    if cccds:
        for cand in await db.scalars(select(Candidate).where(Candidate.cccd.in_(cccds))):
            existing_map[cand.cccd] = cand

    # Auto room assignment from the "Phòng" column (AD-54): match existing rooms by
    # name (case-insensitive) within the exam; auto-create any new names so the file
    # fully drives the room split — the chủ tịch no longer divides manually.
    room_by_name: dict[str, uuid.UUID] = {}
    if body.exam_id is not None:
        for rm in await db.scalars(select(Room).where(Room.exam_id == body.exam_id)):
            room_by_name[rm.name.strip().lower()] = rm.id
        wanted_names = {r["room_name"].strip() for r in rows
                        if r.get("room_name") and r["room_name"].strip()}
        new_names = [n for n in wanted_names if n.lower() not in room_by_name]
        if new_names:
            for n in new_names:
                db.add(Room(exam_id=body.exam_id, name=n))
            await db.flush()
            for rm in await db.scalars(select(Room).where(Room.exam_id == body.exam_id)):
                room_by_name[rm.name.strip().lower()] = rm.id

    def _room_id_for(row: dict) -> uuid.UUID | None:
        name = (row.get("room_name") or "").strip()
        return room_by_name.get(name.lower()) if name else None

    # Same protection as preview: refuse to move a candidate currently sitting
    # an in_progress exam.
    from app.models.session import ExamSession
    locked_exam_ids = set(await db.scalars(
        select(ExamSession.exam_id).where(
            ExamSession.status == SessionStatus.IN_PROGRESS.value,
        ).distinct()
    ))

    for r in rows:
        cccd = r["cccd"]
        existing = existing_map.get(cccd)
        if existing is not None:
            if existing.exam_id in locked_exam_ids:
                skipped += 1
                errors.append(f"{cccd}: đang làm bài kỳ thi khác, bỏ qua")
                continue
            # Rebind to the new section + refresh info from the Excel row.
            existing.exam_id = body.exam_id
            existing.id_type = r.get("id_type", "cccd")
            existing.full_name = r["full_name"]
            existing.birth_date = date.fromisoformat(r["birth_date"])
            existing.unit = r["unit"]
            existing.graduation_year = r["graduation_year"]
            existing.major = r["major"]
            existing.category = r["category"]
            existing.attempt_number = r["attempt_number"]
            room_id = _room_id_for(r)
            if room_id is not None:
                existing.room_id = room_id
            updated += 1
        else:
            db.add(Candidate(
                cccd=cccd,
                id_type=r.get("id_type", "cccd"),
                full_name=r["full_name"],
                birth_date=date.fromisoformat(r["birth_date"]),
                unit=r["unit"],
                graduation_year=r["graduation_year"],
                major=r["major"],
                category=r["category"],
                attempt_number=r["attempt_number"],
                exam_id=body.exam_id,
                room_id=_room_id_for(r),
            ))
            created += 1

    await db.commit()
    await redis_client.delete(f"import:{body.token}")
    return ImportCommitResult(created=created, updated=updated, skipped=skipped, errors=errors)


# --- photos -----------------------------------------------------------------

@router.post("/photos/zip", response_model=ZipUploadReport)
async def upload_photos_zip(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> ZipUploadReport:
    content = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File ZIP không hợp lệ")

    report = ZipUploadReport(updated=0)
    names = [n for n in zf.namelist() if not n.endswith("/")]

    # Photo filenames are the candidate's login id (CCCD or passport). Normalize
    # each via classify so passport-named photos match too (AD-58).
    def _norm(stem: str) -> str | None:
        try:
            return classify_identifier(stem)[0]
        except ValueError:
            return None

    name_cccd = {n: _norm(os.path.splitext(os.path.basename(n))[0]) for n in names}
    cccds = [c for c in name_cccd.values() if c]
    cands = list(await db.scalars(select(Candidate).where(Candidate.cccd.in_(cccds)))) if cccds else []
    candmap = {c.cccd: c for c in cands}

    for n in names:
        base = os.path.basename(n)
        cccd = name_cccd[n]
        if not cccd:
            report.invalid_files.append(base)
            continue
        candidate = candmap.get(cccd)
        if candidate is None:
            report.unmatched_files.append(base)
            continue
        if await _exam_is_active(db, candidate.exam_id):
            report.invalid_files.append(f"{base} (kỳ thi đang khoá)")
            continue
        try:
            candidate.photo_path = save_candidate_photo(zf.read(n), cccd)
        except (ImageValidationError, KeyError):
            report.invalid_files.append(base)
            continue
        report.matched.append(cccd)
        report.updated += 1

    await db.commit()
    return report
