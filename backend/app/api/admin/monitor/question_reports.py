"""Khiếu nại câu hỏi của thí sinh — danh sách + xử lý (chủ tịch).

Giám thị KHÔNG có danh sách (giữ đúng phạm vi Tạm dừng / Tiếp tục của họ, AD-124);
họ chỉ thấy nhãn trên dòng thí sinh trong phòng mình, qua ``open_question_reports``
của ``SessionSummary``.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import exam_for_admin, sitting_for_admin
from app.database import get_db
from app.models import Admin, Candidate, QuestionReport, Room, Sitting
from app.schemas.question_report import QuestionReportOut, QuestionReportResolveIn

from ._common import _require_proctor

router = APIRouter()


@router.get("/sittings/{sitting_id}/question-reports", response_model=list[QuestionReportOut])
async def list_question_reports(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> list[QuestionReportOut]:
    """Khiếu nại của buổi thi, chưa xử lý lên trước.

    Còn đọc được sau khi đóng buổi — hội đồng cần chúng ĐÚNG lúc chấm, mà lúc đó đề
    đã bị xoá."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    rows = (await db.execute(
        select(QuestionReport, Candidate, Room.name, Admin.full_name)
        .join(Candidate, Candidate.id == QuestionReport.candidate_id)
        .outerjoin(Room, Room.id == Candidate.room_id)
        .outerjoin(Admin, Admin.id == QuestionReport.resolved_by)
        .where(QuestionReport.sitting_id == sitting.id)
        .order_by(QuestionReport.resolved_at.is_not(None), QuestionReport.created_at.desc())
    )).all()
    return [
        QuestionReportOut(
            id=r.id, candidate_id=c.id, cccd=c.cccd, full_name=c.full_name,
            room_name=room_name, question_id=r.question_id,
            question_number=r.question_number, content=r.content,
            created_at=r.created_at, resolved_at=r.resolved_at,
            resolution=r.resolution, resolved_by_name=solver_name,
        )
        for r, c, room_name, solver_name in rows
    ]


@router.post("/question-reports/{report_id}/resolve")
async def resolve_question_report(
    report_id: uuid.UUID,
    body: QuestionReportResolveIn,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> dict:
    """Đánh dấu đã xử lý + ghi kết luận của hội đồng."""
    report = await db.get(QuestionReport, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy khiếu nại")
    sitting = await db.get(Sitting, report.sitting_id)
    if sitting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy buổi thi")
    await exam_for_admin(db, sitting.exam_id, admin)  # ownership gate
    report.resolved_at = datetime.now(timezone.utc)
    report.resolved_by = admin.id
    report.resolution = body.resolution
    await db.commit()
    return {"resolved": True}
