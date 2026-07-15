"""Sitting (buổi thi) CRUD + QTI import + open (AD-47).

A kỳ thi (Exam) is a container; each sitting carries its own đề and runs one at a
time. QTI ZIPs are uploaded into a sitting (``POST /sittings/{id}/import-qti``);
opening a sitting (``POST /sittings/{id}/open``) decrypts its payload into Redis
and flips it active so candidates can log in. Run-control (distribute/start/end/
pause) lives in the monitor router, keyed by sitting id.
"""

import hashlib
import io
import json
import os
import tempfile
import uuid
import zipfile

import pyzipper
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import exam_for_admin, require_roles, sitting_for_admin
from app.core import encryption as _encryption
from app.core import qti_crypt
from app.core.redis import redis_client
from app.database import get_db
from app.models import Admin, Answer, ExamSession, Sitting
from app.models.enums import AdminRole, EventType, SessionStatus, SittingStatus
from app.schemas.sitting import SittingCreate, SittingOut, SittingUpdate
from app.services import exam_assets, exam_package, qti_loader, session_service
from app.services.qti_loader import QtiLoadError

router = APIRouter()

_require_proctor = require_roles(AdminRole.PROCTOR.value)
# Deleting a buổi is reserved for Quản trị (super_admin); the chủ tịch (proctor)
# may set everything up and run it but not delete a sitting.
_require_super = require_roles(AdminRole.SUPER_ADMIN.value)

# AD-75: trần upload + trần tổng-giải-nén cho import-qti (chống lấp RAM/đĩa).
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024
_MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024


# --- QTI 3.0 import helpers (moved from exams.py, AD-47) --------------------

def _build_exam_file_from_qti(parsed: dict, password: str, duration_minutes: int,
                              exam_date_iso: str | None) -> bytes:
    """Encrypt a parsed QTI payload into the on-disk .exam blob format (the
    at-rest representation stored in ``exam_sittings.encrypted_payload``)."""
    payload = parsed["payload"]
    exam_meta = parsed["exam"]
    plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    checksum = hashlib.sha256(plaintext).hexdigest()
    enc = _encryption.encrypt(plaintext, password)
    file_obj = {
        "version": exam_package.FORMAT_VERSION,
        "exam_id": str(uuid.uuid4()),
        "exam_name": exam_meta["name"],
        "description": "Imported from QTI 3.0 package",
        "duration_minutes": duration_minutes,
        "exam_date": exam_date_iso,
        "shuffle_questions": exam_meta["shuffle_questions"],
        "shuffle_options": exam_meta["shuffle_options"],
        "question_count": len(payload["questions"]),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checksum_sha256": checksum,
        "salt": enc["salt"],
        "nonce": enc["nonce"],
        "encrypted_payload": enc["ciphertext"],
    }
    return json.dumps(file_obj, ensure_ascii=False).encode("utf-8")


def _find_package_root(extracted: str) -> str:
    """Return the directory that actually contains ``imsmanifest.xml`` (QTI ZIPs
    often nest content in a single top-level folder)."""
    if os.path.isfile(os.path.join(extracted, "imsmanifest.xml")):
        return extracted
    for name in os.listdir(extracted):
        sub = os.path.join(extracted, name)
        if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "imsmanifest.xml")):
            return sub
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "ZIP không chứa imsmanifest.xml — không phải gói QTI hợp lệ.",
    )


def _safe_extract_zip(zip_bytes: bytes, dest: str) -> None:
    """Extract a ZIP while blocking path-traversal entries.

    Luồng .qenc (spec 2026-07-13): ZIP bên trong PHẢI là ZIP thường — mật khẩu
    ZipCrypto/WinZip của nhà cung cấp đã bị gỡ khỏi luồng nạp đề; người ra đề
    giải nén + nén lại không mật khẩu trước khi mã hoá bằng tool."""
    try:
        # pyzipper đọc ZIP thường như zipfile chuẩn (giữ lib vì report vẫn dùng).
        zf = pyzipper.AESZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File không phải ZIP hợp lệ.")
    dest_abs = os.path.realpath(dest)
    # AD-75: trần TỔNG dung lượng giải nén — chống zip-bomb lấp RAM/đĩa VM
    # (VM từng phình tới trần 10GB trong sự cố 13-07). Đề thật 280 câu + ảnh
    # giải nén ~200MB; 2GB là rất dư.
    total = sum(i.file_size for i in zf.infolist())
    if total > _MAX_EXTRACTED_BYTES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Gói đề giải nén tới {total // (1024 * 1024)}MB — vượt trần "
            f"{_MAX_EXTRACTED_BYTES // (1024 * 1024)}MB, từ chối (nghi zip-bomb).",
        )
    for member in zf.namelist():
        target = os.path.realpath(os.path.join(dest, member))
        if target != dest_abs and not target.startswith(dest_abs + os.sep):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ZIP chứa đường dẫn nguy hiểm.")
    try:
        zf.extractall(dest)
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "password required" in msg or "is encrypted" in msg:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                "ZIP bên trong có đặt mật khẩu — hãy giải nén và nén lại KHÔNG mật khẩu "
                "trước khi mã hoá bằng phần mềm Mã hoá đề thi.")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Không giải nén được: {exc}")


# --- response builder -------------------------------------------------------

async def _sitting_out(db: AsyncSession, sitting: Sitting) -> SittingOut:
    out = SittingOut.model_validate(sitting)
    out.has_payload = await session_service.sitting_has_payload(db, sitting.id)
    out.has_running_sessions = bool(await db.scalar(
        select(ExamSession.id).where(
            ExamSession.sitting_id == sitting.id,
            ExamSession.status == SessionStatus.IN_PROGRESS.value,
        ).limit(1)
    ))
    return out


# --- CRUD -------------------------------------------------------------------

@router.get("/exams/{exam_id}/sittings", response_model=list[SittingOut])
async def list_sittings(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> list[SittingOut]:
    await exam_for_admin(db, exam_id, admin)  # ownership gate
    rows = list(await db.scalars(
        select(Sitting).where(Sitting.exam_id == exam_id).order_by(Sitting.ordinal)
    ))
    return [await _sitting_out(db, s) for s in rows]


@router.post("/exams/{exam_id}/sittings", response_model=SittingOut,
             status_code=status.HTTP_201_CREATED)
async def create_sitting(
    exam_id: uuid.UUID,
    body: SittingCreate,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> SittingOut:
    await exam_for_admin(db, exam_id, admin)
    next_ordinal = (await db.scalar(
        select(func.coalesce(func.max(Sitting.ordinal), 0)).where(Sitting.exam_id == exam_id)
    )) + 1
    sitting = Sitting(
        exam_id=exam_id, ordinal=next_ordinal, status=SittingStatus.DRAFT.value,
        **body.model_dump(),
    )
    db.add(sitting)
    await db.commit()
    await db.refresh(sitting)
    return await _sitting_out(db, sitting)


@router.patch("/sittings/{sitting_id}", response_model=SittingOut)
async def update_sitting(
    sitting_id: uuid.UUID,
    body: SittingUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> SittingOut:
    sitting = await sitting_for_admin(db, sitting_id, admin)
    if sitting.status != SittingStatus.DRAFT.value:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Chỉ sửa được buổi thi khi chưa mở (nháp).")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(sitting, field, value)
    await db.commit()
    await db.refresh(sitting)
    return await _sitting_out(db, sitting)


@router.delete("/sittings/{sitting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sitting(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_super),  # super-only (AD-49): chủ tịch không xoá
) -> None:
    sitting = await sitting_for_admin(db, sitting_id, admin)
    if sitting.status == SittingStatus.ACTIVE.value:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Buổi thi đang mở — hãy đóng trước khi xoá.")
    await redis_client.delete(session_service.payload_key(sitting.id))
    exam_assets.wipe_sitting_assets(sitting.id)
    await db.delete(sitting)
    await db.commit()


# --- QTI import -------------------------------------------------------------

@router.post("/sittings/{sitting_id}/import-qti", response_model=SittingOut)
async def import_qti_into_sitting(
    sitting_id: uuid.UUID,
    file: UploadFile = File(..., description="Gói QTI 3.0 đã mã hoá (.qenc)"),
    password: str = Form(..., description="Mật khẩu mở đề (người ra đề đọc lúc nạp)"),
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> SittingOut:
    """Load QTI content into a sitting. Allowed while draft or active (a mid-run
    re-upload recomputes existing sessions' shuffle). Title/duration come from the
    QTI time-limits if present, else the sitting's existing duration.

    Spec 2026-07-13: CHỈ nhận file .qenc (mã hoá bởi tool qti-crypter) + mã kích
    hoạt TOTP 30 phút. ZIP thường bị từ chối — chống lộ đề khi lưu chuyển file.
    """
    sitting = await sitting_for_admin(db, sitting_id, admin)
    if sitting.status == SittingStatus.CLOSED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Buổi thi đã đóng — không thể nạp lại đề.")

    # AD-75: chặn file khổng lồ TRƯỚC khi decrypt (đọc trọn vào RAM). Đề thật
    # .qenc ~100-150MB; trần 500MB là rất dư.
    raw = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"File quá lớn (> {_MAX_UPLOAD_BYTES // (1024 * 1024)}MB) — không phải gói đề hợp lệ.",
        )
    if not qti_crypt.is_qenc(raw):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Đề phải được mã hoá bằng phần mềm Mã hoá đề thi (file .qenc) — "
            "không nhận ZIP thường.",
        )
    # Hai khoá: khoá hệ thống nhúng sẵn + mật khẩu đề do người ra đề đọc. Sai/thiếu
    # mật khẩu → GCM không mở được → QencError → 400 (không có "cửa kiểm tra" nào để
    # bypass: mật khẩu nằm THẲNG trong khoá giải mã).
    try:
        zip_bytes = qti_crypt.decrypt_qenc(raw, password)
    except qti_crypt.QencError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    with tempfile.TemporaryDirectory(prefix="qti_") as tmp:
        _safe_extract_zip(zip_bytes, tmp)
        qti_dir = _find_package_root(tmp)
        try:
            parsed = qti_loader.load_qti_package(qti_dir)
        except QtiLoadError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    duration = parsed["exam"]["duration_minutes"] or sitting.duration_minutes or 45
    key = session_service.storage_key()
    content = _build_exam_file_from_qti(parsed, key, duration, None)

    sitting.encrypted_payload = content
    sitting.duration_minutes = duration
    # AD-69: LUÔN đảo câu hỏi + đảo đáp án (chống nhìn bài), bất kể file QTI khai gì
    # — quyết định vận hành của hội đồng. Phần tử `fixed` (vd "Tất cả đáp án trên")
    # vẫn được giữ nguyên vị trí nhờ shuffle_keeping_fixed (AD-34).
    sitting.shuffle_questions = True
    sitting.shuffle_options = True
    sitting.question_count = len(parsed["payload"].get("questions", []))
    sitting.report_snapshot = [
        {"id": q["id"], "code": q.get("code", ""), "text": q.get("text", ""),
         "correct_option": q.get("correct_option")}
        for q in sorted(parsed["payload"]["questions"], key=lambda x: x.get("order_index", 0))
    ]

    # Mid-run re-upload (sitting already active): fresh question UUIDs invalidate
    # any frozen session order, so recompute it + drop orphaned answers, and
    # refresh the Redis payload.
    if sitting.status == SittingStatus.ACTIVE.value:
        file_obj = exam_package.parse_exam_file(content)
        decrypted = exam_package.decrypt_exam_file(file_obj, key)
        sessions = list(await db.scalars(
            select(ExamSession).where(
                ExamSession.sitting_id == sitting.id,
                ExamSession.status.in_([
                    SessionStatus.WAITING.value, SessionStatus.READY.value,
                    SessionStatus.IN_PROGRESS.value,
                ]),
            )
        ))
        for sess in sessions:
            q_order, o_order = session_service.build_orders(
                str(sess.id), decrypted, sitting.shuffle_questions, sitting.shuffle_options,
            )
            sess.question_order = q_order
            sess.option_order = o_order
            await db.execute(delete(Answer).where(Answer.session_id == sess.id))
        # SP-1: nạp lại đề giữa buổi → xoá ảnh cũ rồi materialize ảnh mới (UUID
        # câu mới → file mới); cache payload kèm URL.
        exam_assets.wipe_sitting_assets(sitting.id)
        decrypted = exam_assets.materialize_payload_images(sitting.id, decrypted)
        ttl = sitting.duration_minutes * 60 + 1800
        await redis_client.set(
            session_service.payload_key(sitting.id),
            json.dumps(decrypted, ensure_ascii=False), ex=ttl,
        )
    await db.commit()
    await db.refresh(sitting)
    return await _sitting_out(db, sitting)


# --- open (draft → active) --------------------------------------------------

@router.post("/sittings/{sitting_id}/open", response_model=SittingOut)
async def open_sitting(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> SittingOut:
    """Mở buổi thi: decrypt the đề into Redis and flip the sitting active so
    candidates can log in. At most one sitting per exam may be active."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    if sitting.status == SittingStatus.ACTIVE.value:
        return await _sitting_out(db, sitting)  # idempotent
    if sitting.status == SittingStatus.CLOSED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Buổi thi đã đóng — không thể mở lại.")
    blob = await session_service.sitting_payload_blob(db, sitting.id)
    if not blob:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chưa nạp đề — vào nạp QTI trước.")
    other = await session_service.get_active_sitting(db, sitting.exam_id)
    if other is not None and other.id != sitting.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Buổi \"{other.name}\" đang mở. Hãy đóng nó trước khi mở buổi khác.",
        )

    key = session_service.storage_key()
    file_obj = exam_package.parse_exam_file(blob)
    decrypted = exam_package.decrypt_exam_file(file_obj, key)
    # SP-1: giải mã ảnh ra file tĩnh + gắn URL vào payload TRƯỚC khi cache Redis,
    # để /questions trả URL (không base64).
    decrypted = exam_assets.materialize_payload_images(sitting.id, decrypted)
    ttl = sitting.duration_minutes * 60 + 1800
    await redis_client.set(
        session_service.payload_key(sitting.id),
        json.dumps(decrypted, ensure_ascii=False), ex=ttl,
    )
    # SP-4: buổi mới mở → xoá cờ wipe còn sót (nếu có) để đề vừa nạp không bị xoá ngay.
    await redis_client.delete(session_service.kiosk_wipe_key(sitting.exam_id))
    sitting.status = SittingStatus.ACTIVE.value
    db.add(session_service.make_event(
        event_type=EventType.SITTING_OPENED.value,
        metadata={"sitting_id": str(sitting.id), "exam_id": str(sitting.exam_id),
                  "admin": admin.username},
    ))
    await db.commit()
    await db.refresh(sitting)
    return await _sitting_out(db, sitting)


@router.get("/sittings/{sitting_id}", response_model=SittingOut)
async def get_sitting(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> SittingOut:
    sitting = await sitting_for_admin(db, sitting_id, admin)
    return await _sitting_out(db, sitting)
