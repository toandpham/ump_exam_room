"""Dự phòng giấy: in đề, phát phiếu trả lời, nhận bản quét (đợt 6).

Dùng khi máy hỏng hàng loạt giữa buổi. Ba việc:

  GET  /sittings/{id}/paper/exam.pdf     — đề bản giấy (kèm đáp án nếu hội đồng cần)
  GET  /sittings/{id}/paper/sheets.pdf   — phiếu trả lời cho từng thí sinh
  POST /sittings/{id}/paper/scan         — đọc bản quét, TRẢ VỀ ĐỂ ĐỐI CHIẾU
  POST /sittings/{id}/paper/apply        — ghi các bài đã được xác nhận vào CSDL

Bước quét và bước ghi TÁCH RỜI có chủ ý: máy đọc phiếu không bao giờ chắc chắn
100% (giấy nhàu, tô mờ, tẩy chưa sạch), nên phải để chủ tịch nhìn kết quả rồi mới
quyết định ghi. Ghi thẳng là biến một tờ đọc lệch thành điểm sai không ai biết.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import sitting_for_admin
from app.core.redis import redis_client
from app.database import get_db
from app.models import Admin, Answer, Candidate, Exam, ExamSession, Room, Sitting
from app.models.enums import EventType, SessionStatus
from app.schemas.paper import PaperApplyIn, PaperScanResult, PaperSheetRead
from app.services import paper_exam, session_service
from app.services.omr import geometry as omr_geometry
from app.services.omr import reader as omr_reader
from app.services.omr import sheet as omr_sheet
from app.services.seating_service import _FONT

from ._http import attach
from .monitor._common import _require_proctor

logger = logging.getLogger("exam.paper")

router = APIRouter()

# Trần kích thước file quét: 400 tờ ở 200 DPI vào khoảng 200MB, cho biên rộng gấp
# đôi. Không có trần thì một file hỏng cũng đủ làm cạn bộ nhớ máy chủ.
MAX_SCAN_BYTES = 400 * 1024 * 1024


async def _payload_questions(db: AsyncSession, sitting: Sitting) -> list[dict]:
    payload = await session_service.ensure_sitting_payload(db, redis_client, sitting)
    if not payload:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Buổi thi chưa có đề (hoặc đề đã bị xoá khi đóng buổi).")
    return sorted(payload.get("questions", []), key=lambda q: q.get("order_index", 0))


@router.get("/sittings/{sitting_id}/paper/exam.pdf")
async def paper_exam_pdf(
    sitting_id: uuid.UUID,
    with_answers: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> Response:
    """Đề bản giấy, theo THỨ TỰ GỐC của đề (không trộn theo từng thí sinh)."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    exam_row = await db.get(Exam, sitting.exam_id)
    questions = await _payload_questions(db, sitting)
    pdf = paper_exam.build_exam_paper(
        exam_name=exam_row.name if exam_row else "", sitting_name=sitting.name,
        questions=questions, with_answers=with_answers,
    )
    name = f"{sitting.name}{' - CO DAP AN' if with_answers else ''}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": attach(name)})


@router.get("/sittings/{sitting_id}/paper/sheets.pdf")
async def paper_sheets_pdf(
    sitting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> Response:
    """Phiếu trả lời cho từng thí sinh + GHI LẠI ánh xạ mã ↔ thí sinh.

    Ánh xạ phải được lưu ngay lúc in: suy ra lúc quét thì chỉ cần thêm/bớt một thí
    sinh ở giữa là gán nhầm bài cho người khác mà không có dấu hiệu nào."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    if not sitting.question_count:
        raise HTTPException(status.HTTP_409_CONFLICT, "Buổi thi chưa có đề.")
    rows = (await db.execute(
        select(Candidate, Room.name)
        .outerjoin(Room, Room.id == Candidate.room_id)
        .where(Candidate.exam_id == sitting.exam_id)
        .order_by(Room.name.nulls_last(), Candidate.full_name, Candidate.cccd)
    )).all()
    if not rows:
        raise HTTPException(status.HTTP_409_CONFLICT, "Kỳ thi chưa có thí sinh nào.")
    if len(rows) >= 2 ** omr_geometry.ID_BITS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Quá nhiều thí sinh cho mã trên phiếu.")

    exam_row = await db.get(Exam, sitting.exam_id)
    # Mã bắt đầu từ 1: mã 0 (không tô ô nào) trùng với tờ trắng/đọc hỏng.
    cands = [{"index": i + 1, "cccd": c.cccd, "full_name": c.full_name,
              "room_name": room_name} for i, (c, room_name) in enumerate(rows)]
    pdf = omr_sheet.build_answer_sheets(
        font=_FONT, exam_name=exam_row.name if exam_row else "",
        sitting_name=sitting.name, candidates=cands,
        total_questions=sitting.question_count,
    )
    sitting.paper_roster = [str(c.id) for c, _ in rows]
    await db.commit()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             attach(f"Phieu tra loi - {sitting.name}.pdf")})


def _roster_lookup(sitting: Sitting) -> dict[int, str]:
    return {i + 1: cid for i, cid in enumerate(sitting.paper_roster or [])}


@router.post("/sittings/{sitting_id}/paper/scan", response_model=PaperScanResult)
async def paper_scan(
    sitting_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> PaperScanResult:
    """Đọc bản quét và TRẢ VỀ để đối chiếu — chưa ghi gì vào CSDL."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    roster = _roster_lookup(sitting)
    if not roster:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Chưa in phiếu trả lời cho buổi này — không biết mã trên phiếu là của ai.")

    data = await file.read()
    if len(data) > MAX_SCAN_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File quét quá lớn.")
    try:
        images = omr_reader.images_from_upload(data, file.filename or "")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Không đọc được file quét: {exc}") from exc

    names = {}
    for c in await db.scalars(select(Candidate).where(Candidate.exam_id == sitting.exam_id)):
        names[str(c.id)] = (c.cccd, c.full_name)

    sheets: list[PaperSheetRead] = []
    for i, img in enumerate(images):
        try:
            res = omr_reader.read_sheet(img, sitting.question_count or 0)
        except omr_reader.OmrError as exc:
            sheets.append(PaperSheetRead(page_in_file=i + 1, error=str(exc)))
            continue
        cid = roster.get(res.candidate_index)
        cccd, full_name = names.get(cid or "", ("", ""))
        sheets.append(PaperSheetRead(
            page_in_file=i + 1, candidate_index=res.candidate_index,
            candidate_id=cid, cccd=cccd, full_name=full_name,
            sheet_page=res.page,
            answers={str(q): a for q, a in sorted(res.answers.items())},
            unsure=sorted(res.unsure),
            error=None if cid else "Mã trên phiếu không khớp thí sinh nào của buổi này.",
        ))
    return PaperScanResult(total_sheets=len(sheets), sheets=sheets)


@router.post("/sittings/{sitting_id}/paper/apply")
async def paper_apply(
    sitting_id: uuid.UUID,
    body: PaperApplyIn,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> dict:
    """Ghi bài giấy đã được chủ tịch xác nhận vào CSDL, rồi chấm.

    Chỉ ghi cho thí sinh CHƯA có bài trên máy — bài làm trên máy luôn được ưu tiên
    (nó có mốc thời gian và dấu niêm phong; bài giấy thì không)."""
    sitting = await sitting_for_admin(db, sitting_id, admin)
    snapshot = sitting.report_snapshot or []
    if not snapshot:
        raise HTTPException(status.HTTP_409_CONFLICT, "Buổi thi không có dữ liệu đề.")
    qids = [q["id"] for q in snapshot]
    correct_map = await session_service.correct_map_for_sitting(db, redis_client, sitting)

    applied, skipped = 0, []
    for entry in body.sheets:
        cand = await db.get(Candidate, entry.candidate_id)
        if cand is None or cand.exam_id != sitting.exam_id:
            skipped.append({"candidate_id": str(entry.candidate_id), "reason": "không thuộc kỳ thi"})
            continue
        session = await db.scalar(select(ExamSession).where(
            ExamSession.candidate_id == cand.id, ExamSession.sitting_id == sitting.id))
        if session is not None and session.status != SessionStatus.WAITING.value:
            skipped.append({"candidate_id": str(cand.id),
                            "reason": "đã có bài trên máy — không ghi đè"})
            continue
        if session is None:
            session = ExamSession(
                candidate_id=cand.id, sitting_id=sitting.id, exam_id=sitting.exam_id,
                question_order=qids, option_order={},
            )
            db.add(session)
            await db.flush()
        session.question_order = qids
        for q_index, letter in entry.answers.items():
            if not (0 <= q_index < len(qids)):
                continue
            db.add(Answer(session_id=session.id, question_id=uuid.UUID(qids[q_index]),
                          selected_option=letter))
        session.status = SessionStatus.SUBMITTED.value
        session.submitted_at = datetime.now(timezone.utc)
        # Phiên CSDL của ứng dụng đặt autoflush=False, nên phải tự đẩy các dòng đáp
        # án vừa thêm xuống TRƯỚC khi chấm — nếu không, score_session truy vấn ra
        # bảng rỗng và niêm phong 0 điểm cho một bài làm đúng.
        await db.flush()
        await session_service.score_session(db, session, correct_map)
        db.add(session_service.make_event(
            event_type=EventType.SUBMIT.value, session_id=session.id, cccd=cand.cccd,
            metadata={"source": "paper", "admin": admin.username}))
        applied += 1

    await db.commit()
    logger.info("Nhập bài giấy buổi %s: ghi %d, bỏ qua %d", sitting_id, applied, len(skipped))
    return {"applied": applied, "skipped": skipped}
