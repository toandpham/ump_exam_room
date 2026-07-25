"""Ghi sự kiện kiểm toán (exam_events) — tách từ session_service, refactor đợt 3.

Dùng bởi cả tầng API, scoring và tác vụ nền nên đứng riêng để tránh vòng import.
Re-export qua ``app.services.session_service``."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExamEvent


def make_event(*, event_type, cccd=None, ip=None, session_id=None, metadata=None) -> ExamEvent:
    # AD-75: cột cccd_attempted là String(12); input SAI ĐỊNH DẠNG 13-20 ký tự
    # (dán thừa số) từng nổ varchar overflow → thí sinh nhận 500 thay vì 400.
    return ExamEvent(
        session_id=session_id,
        cccd_attempted=(cccd or None) and str(cccd)[:12],
        client_ip=ip,
        event_type=event_type,
        event_metadata=metadata,
    )


async def log_event_commit(db: AsyncSession, **kwargs) -> None:
    """Persist a single event immediately (used on failed-login paths)."""
    db.add(make_event(**kwargs))
    await db.commit()

