"""Idempotent startup bootstrap (AD-48).

Ensures a fixed pool of 10 giám thị (room_proctor) accounts always exists —
``giamthi1``..``giamthi10`` (display "Giám thị 1".."Giám thị 10"). Exams
auto-assign room i → giamthi{i}; the chủ tịch resets each one's 6-digit PIN and
reads it out to the giám thị. Default passwords are placeholders, meant to be
reset before use.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models import Admin
from app.models.enums import AdminRole

logger = logging.getLogger("exam.bootstrap")

ROOM_PROCTOR_COUNT = 10


def room_proctor_username(n: int) -> str:
    return f"giamthi{n}"


async def ensure_room_proctors() -> int:
    """Create any missing giamthi1..N accounts. Returns how many were created."""
    names = [room_proctor_username(i) for i in range(1, ROOM_PROCTOR_COUNT + 1)]
    async with AsyncSessionLocal() as db:
        existing = set(await db.scalars(
            select(Admin.username).where(Admin.username.in_(names))
        ))
        created = 0
        for i in range(1, ROOM_PROCTOR_COUNT + 1):
            uname = room_proctor_username(i)
            if uname in existing:
                continue
            db.add(Admin(
                username=uname,
                password_hash=hash_password(f"giamthi{i}"),  # placeholder; chủ tịch resets PIN
                full_name=f"Giám thị {i}",
                role=AdminRole.ROOM_PROCTOR.value,
                is_active=True,
            ))
            created += 1
        if created:
            await db.commit()
            logger.info("Bootstrapped %d giám thị account(s)", created)
        return created
