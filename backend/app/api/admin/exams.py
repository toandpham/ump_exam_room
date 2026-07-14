"""Exam (kỳ thi) CRUD. The exam is a container; đề lives on its sittings (AD-47).

QTI import + run-control moved to the sittings / monitor routers. There is no
manual authoring, .exam exchange, or USB scanning (AD-23/AD-27).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import exam_for_admin, get_current_admin, require_roles
from app.bootstrap import room_proctor_username
from app.database import get_db
from app.models import Admin, Exam, ExamSession, Room, Sitting
from app.models.enums import AdminRole, ExamStatus, SessionStatus, SittingStatus
from app.schemas.exam import ExamCreate, ExamOut, SittingDraft

router = APIRouter()

# Role split (AD-25/47): proctor = "Chủ tịch hội đồng thi" orchestrates exams;
# super_admin = "Quản trị" only views + deletes + manages accounts. Reads stay
# open to both so super_admin can see what to delete.
_require_proctor = require_roles(AdminRole.PROCTOR.value)
_require_super = require_roles(AdminRole.SUPER_ADMIN.value)

# Anything except a live (active) exam may be deleted.
_DELETABLE_STATUSES = {ExamStatus.DRAFT.value, ExamStatus.CLOSED.value}


def _exam_out(exam: Exam, question_count: int = 0, sitting_count: int = 0) -> ExamOut:
    out = ExamOut.model_validate(exam)
    out.question_count = question_count
    out.sitting_count = sitting_count
    return out


@router.post("", response_model=ExamOut, status_code=status.HTTP_201_CREATED)
async def create_exam(
    body: ExamCreate,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(_require_proctor),
) -> ExamOut:
    """Create + auto-activate a kỳ thi. Refuses if another exam is already active
    (at-most-one-active invariant — one exam event runs on the machine at a time).
    Auto-creates a first sitting (buổi) + a first room (phòng) so the minimal
    "1 buổi / 1 phòng" flow works out of the box. The creating proctor (chủ tịch)
    becomes the owner (AD-30)."""
    other = await db.scalar(
        select(Exam).where(Exam.status == ExamStatus.ACTIVE.value).limit(1)
    )
    if other is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Kỳ thi \"{other.name}\" đang chạy. Hãy kết thúc nó trước khi tạo kỳ thi mới.",
        )
    exam_fields = body.model_dump(exclude={"room_count", "room_capacity", "sittings"})
    exam = Exam(**exam_fields, status=ExamStatus.ACTIVE.value, created_by=admin.id)
    db.add(exam)
    await db.flush()

    # Generate the declared structure (rooms + buổi). Falls back to one of each
    # so API callers that omit the structure still get a usable exam. Each room i
    # is auto-assigned the fixed giám thị "giamthi{i}" (AD-48).
    n_rooms = max(1, body.room_count)
    gt_names = [room_proctor_username(i) for i in range(1, n_rooms + 1)]
    gt_id = {u: i for u, i in (await db.execute(
        select(Admin.username, Admin.id).where(
            Admin.username.in_(gt_names),
            Admin.role == AdminRole.ROOM_PROCTOR.value))).all()}
    for i in range(1, n_rooms + 1):
        db.add(Room(exam_id=exam.id, name=f"Phòng {i}", capacity=body.room_capacity,
                    proctor_id=gt_id.get(room_proctor_username(i))))
    drafts = body.sittings or [SittingDraft(name="Buổi thi 1")]
    for ordinal, d in enumerate(drafts, start=1):
        db.add(Sitting(
            exam_id=exam.id, name=d.name, ordinal=ordinal,
            scheduled_date=d.scheduled_date,
            duration_minutes=d.duration_minutes or exam.duration_minutes,
            status=SittingStatus.DRAFT.value,
        ))
    await db.commit()
    await db.refresh(exam)
    return _exam_out(exam, 0, len(drafts))


@router.get("", response_model=list[ExamOut])
async def list_exams(
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> list[ExamOut]:
    running_subq = (
        select(ExamSession.exam_id)
        .where(ExamSession.status == SessionStatus.IN_PROGRESS.value)
        .distinct()
        .subquery()
    )
    # Per-exam aggregates over sittings: total questions + sitting count.
    sit_subq = (
        select(
            Sitting.exam_id.label("exam_id"),
            func.coalesce(func.sum(Sitting.question_count), 0).label("q_count"),
            func.count(Sitting.id).label("s_count"),
        )
        .group_by(Sitting.exam_id)
        .subquery()
    )
    stmt = (
        select(
            Exam,
            running_subq.c.exam_id.is_not(None).label("has_running"),
            Admin.full_name, Admin.username,
            sit_subq.c.q_count, sit_subq.c.s_count,
        )
        .outerjoin(running_subq, running_subq.c.exam_id == Exam.id)
        .outerjoin(Admin, Admin.id == Exam.created_by)
        .outerjoin(sit_subq, sit_subq.c.exam_id == Exam.id)
        .order_by(Exam.created_at.desc())
    )
    # AD-30: a proctor sees only their own exams (+ legacy NULL-owner ones).
    if admin.role == AdminRole.PROCTOR.value:
        stmt = stmt.where((Exam.created_by == admin.id) | (Exam.created_by.is_(None)))
    rows = await db.execute(stmt)
    out = []
    for exam, has_running, owner_full, owner_user, q_count, s_count in rows.all():
        eo = _exam_out(exam, int(q_count or 0), int(s_count or 0))
        eo.has_running_sessions = bool(has_running)
        eo.created_by_name = owner_full or owner_user
        out.append(eo)
    return out


@router.get("/{exam_id}", response_model=ExamOut)
async def get_exam(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> ExamOut:
    exam = await exam_for_admin(db, exam_id, admin)  # ownership gate (AD-30)
    q_count = await db.scalar(
        select(func.coalesce(func.sum(Sitting.question_count), 0))
        .where(Sitting.exam_id == exam_id)
    ) or 0
    s_count = await db.scalar(
        select(func.count(Sitting.id)).where(Sitting.exam_id == exam_id)
    ) or 0
    detail = ExamOut.model_validate(exam)
    detail.question_count = int(q_count)
    detail.sitting_count = int(s_count)
    detail.has_running_sessions = bool(await db.scalar(
        select(ExamSession.id).where(
            ExamSession.exam_id == exam.id,
            ExamSession.status == SessionStatus.IN_PROGRESS.value,
        ).limit(1)
    ))
    return detail


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(_require_super),
) -> None:
    exam = await db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề thi")
    if exam.status not in _DELETABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Không thể xoá đề ở trạng thái '{exam.status}'",
        )
    await db.delete(exam)
    await db.commit()
