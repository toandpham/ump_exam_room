"""Sitting (buổi thi) results reporting + Excel export (AD-47/AD-68)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin._http import XLSX_MEDIA, attach as _attach
from app.api.deps import require_roles, sitting_for_admin
from app.database import get_db
from app.models import Admin, Exam
from app.models.enums import AdminRole
from app.services import report_service

router = APIRouter()

_require_proctor = require_roles(AdminRole.PROCTOR.value)


async def _report_inputs(db: AsyncSession, sitting_id: uuid.UUID, admin: Admin):
    """Resolve the sitting (ownership-gated) + a human report title."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    exam = await db.get(Exam, sitting.exam_id)
    base = f"{exam.name} - {sitting.name}".strip() if exam else sitting.name
    return sitting, base


@router.get("/sittings/{sitting_id}/report")
async def get_report(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> dict:
    sitting, base = await _report_inputs(db, sitting_id, admin)
    report = await report_service.build_report(db, sitting, exam_name=base)
    # Trả meta + counts cho ReportsPage (tránh serialize ảnh/payload lớn).
    return {
        "meta": report["meta"],
        "rows_count": len(report["rows"]),
        "question_count": report["meta"]["question_count"],
        # Vẫn giữ "rows" để test cũ (test_workflow, test_qti_import) kiểm tra chi tiết.
        "rows": report["rows"],
        "questions": report["questions"],
    }


@router.get("/sittings/{sitting_id}/report.xlsx")
async def get_report_xlsx(
    sitting_id: uuid.UUID,
    password: str = "",   # optional: when provided, return an AES-encrypted ZIP wrapping the .xlsx
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> Response:
    sitting, base = await _report_inputs(db, sitting_id, admin)
    if password and len(password) < 6:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mật khẩu phải ≥6 ký tự (hoặc để trống).")
    report = await report_service.build_report(db, sitting, exam_name=base)
    if password:
        content = report_service.export_excel_encrypted_zip(
            report, password, filename=f"{base}.xlsx",
        )
        return Response(
            content=content, media_type="application/zip",
            headers={"Content-Disposition": _attach(f"{base}.zip")},
        )
    return Response(
        content=report_service.export_excel(report),
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": _attach(f"{base}.xlsx")},
    )
