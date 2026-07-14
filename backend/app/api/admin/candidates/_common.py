"""Helpers dùng chung cho các submodule candidates (AD-75)."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import exam_for_admin
from app.models import Admin, Candidate, Exam
from app.models.enums import SessionStatus
from app.schemas.candidate import CandidateOut

_LOCKED_MSG = "Danh sách đã khoá: kỳ thi đang diễn ra. Dùng 'Emergency Add' nếu thật sự cần."


async def _exam_is_active(db: AsyncSession, exam_id: uuid.UUID | None) -> bool:
    """A section is considered 'locked for candidate writes' only once a thí
    sinh has actually started the exam — i.e., at least one ExamSession is
    in_progress. Before that, even though the exam content is loaded (status
    'active'), the admin can still freely import / edit / re-assign the
    candidate roster. This matches the section-first workflow where QTI import
    auto-activates the exam well before testing begins."""
    if not exam_id:
        return False
    from app.models.session import ExamSession  # local import to avoid cycle at module load
    started_id = await db.scalar(
        select(ExamSession.id).where(
            ExamSession.exam_id == exam_id,
            ExamSession.status == SessionStatus.IN_PROGRESS.value,
        ).limit(1)
    )
    return started_id is not None


async def _get_candidate_or_404(db: AsyncSession, candidate_id: uuid.UUID) -> Candidate:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy thí sinh")
    return candidate


async def _candidate_for_admin(
    db: AsyncSession, candidate_id: uuid.UUID, admin: Admin
) -> Candidate:
    """Load a candidate, enforcing exam ownership (AD-30/AD-55 I2): a chủ tịch may
    only touch candidates of exams they own (or unassigned ones); super_admin sees
    all. Non-owned → 404 (hide existence, like the other *_for_admin helpers)."""
    candidate = await _get_candidate_or_404(db, candidate_id)
    if candidate.exam_id is not None:
        await exam_for_admin(db, candidate.exam_id, admin)
    return candidate


async def _assert_unlocked(db: AsyncSession, candidate: Candidate) -> None:
    if await _exam_is_active(db, candidate.exam_id):
        raise HTTPException(status.HTTP_423_LOCKED, _LOCKED_MSG)


async def _to_out(db: AsyncSession, candidate: Candidate) -> CandidateOut:
    out = CandidateOut.model_validate(candidate)
    if candidate.exam_id:
        out.exam_name = await db.scalar(select(Exam.name).where(Exam.id == candidate.exam_id))
    return out
