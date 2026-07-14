"""Seed development data.

Run inside the backend container:
    python -m app.seed

Creates (idempotently):
  - 1 super_admin: admin / admin123
  - 1 sample (draft) exam — đề is per-sitting QTI now, so no question rows
  - 10 candidates with all 9 fields + placeholder photos, assigned to the exam
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

from PIL import Image, ImageDraw
from sqlalchemy import func, select

from app.config import settings
from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models import Admin, Candidate, Exam
from app.models.enums import AdminRole, ExamStatus

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("seed")

SAMPLE_EXAM_NAME = "Đề thi mẫu Phase 1"

CANDIDATES: list[dict] = [
    {"cccd": "079200000001", "name": "Nguyễn Văn An", "birth": date(1995, 3, 12),
     "unit": "Sở Y tế Hà Nội", "grad": 2017, "major": "Y đa khoa",
     "category": "Đối tượng 1", "attempt": 1},
    {"cccd": "079200000002", "name": "Trần Thị Bình", "birth": date(1998, 7, 25),
     "unit": "Bệnh viện Bạch Mai", "grad": 2020, "major": "Điều dưỡng",
     "category": "Đối tượng 2", "attempt": 1},
    {"cccd": "079200000003", "name": "Lê Hoàng Cường", "birth": date(1993, 11, 5),
     "unit": "Sở Y tế TP.HCM", "grad": 2015, "major": "Dược học",
     "category": "Đối tượng 1", "attempt": 2},
    {"cccd": "079200000004", "name": "Phạm Thị Dung", "birth": date(2000, 1, 18),
     "unit": "Trường ĐH Y Hà Nội", "grad": 2022, "major": "Y học cổ truyền",
     "category": "Đối tượng 3", "attempt": 1},
    {"cccd": "079200000005", "name": "Vũ Minh Đức", "birth": date(1996, 9, 30),
     "unit": "Bệnh viện Chợ Rẫy", "grad": 2018, "major": "Răng hàm mặt",
     "category": "Đối tượng 2", "attempt": 1},
    {"cccd": "079200000006", "name": "Đỗ Thị Hoa", "birth": date(1997, 5, 14),
     "unit": "Sở Y tế Đà Nẵng", "grad": 2019, "major": "Xét nghiệm",
     "category": "Đối tượng 1", "attempt": 1},
    {"cccd": "079200000007", "name": "Bùi Quốc Huy", "birth": date(1994, 12, 2),
     "unit": "Bệnh viện Trung ương Huế", "grad": 2016, "major": "Y đa khoa",
     "category": "Đối tượng 2", "attempt": 3},
    {"cccd": "079200000008", "name": "Ngô Thị Lan", "birth": date(1999, 4, 21),
     "unit": "Trường ĐH Dược Hà Nội", "grad": 2021, "major": "Dược học",
     "category": "Đối tượng 3", "attempt": 1},
    {"cccd": "079200000009", "name": "Hoàng Văn Nam", "birth": date(1992, 8, 8),
     "unit": "Bệnh viện Đa khoa Cần Thơ", "grad": 2014, "major": "Phục hồi chức năng",
     "category": "Đối tượng 1", "attempt": 2},
    {"cccd": "079200000010", "name": "Đặng Thị Oanh", "birth": date(2001, 2, 28),
     "unit": "Trường ĐH Y Dược TP.HCM", "grad": 2023, "major": "Điều dưỡng",
     "category": "Đối tượng 2", "attempt": 1},
]


def make_placeholder_photo(path: str, name: str) -> None:
    """Generate a simple 400x500 placeholder portrait with the candidate name."""
    img = Image.new("RGB", (400, 500), (228, 230, 236))
    draw = ImageDraw.Draw(img)
    draw.rectangle([2, 2, 397, 497], outline=(120, 124, 140), width=3)
    draw.ellipse([130, 90, 270, 230], fill=(190, 194, 205))  # head
    draw.ellipse([90, 250, 310, 470], fill=(190, 194, 205))  # shoulders
    draw.text((20, 20), name, fill=(40, 44, 60))
    img.save(path, "JPEG", quality=85)


async def seed_admin(session) -> None:
    existing = await session.scalar(select(Admin).where(Admin.username == "admin"))
    if existing:
        logger.info("Admin 'admin' already exists — skipping.")
        return
    session.add(Admin(
        username="admin",
        password_hash=hash_password("admin123"),
        full_name="Quản trị hệ thống",
        role=AdminRole.SUPER_ADMIN.value,
        is_active=True,
    ))
    logger.info("Created super_admin: admin / admin123")


async def seed_exam_and_candidates(session) -> None:
    existing = await session.scalar(select(Exam).where(Exam.name == SAMPLE_EXAM_NAME))
    if existing:
        logger.info("Sample exam already exists — skipping exam + candidates.")
        return

    exam = Exam(
        name=SAMPLE_EXAM_NAME,
        description="Đề thi mẫu sinh tự động cho môi trường phát triển.",
        duration_minutes=30,
        exam_date=date.today(),
        status=ExamStatus.DRAFT.value,
    )
    session.add(exam)
    await session.flush()  # assign exam.id for the FK below
    logger.info("Created sample exam '%s' (đề nạp qua QTI theo buổi).", exam.name)

    photo_root = os.path.join(settings.upload_dir, "candidates")
    os.makedirs(photo_root, exist_ok=True)

    created = 0
    for c in CANDIDATES:
        rel_path = f"candidates/{c['cccd']}.jpg"
        make_placeholder_photo(os.path.join(settings.upload_dir, rel_path), c["name"])
        session.add(Candidate(
            cccd=c["cccd"],
            full_name=c["name"],
            birth_date=c["birth"],
            unit=c["unit"],
            photo_path=rel_path,
            graduation_year=c["grad"],
            major=c["major"],
            category=c["category"],
            attempt_number=c["attempt"],
            exam_id=exam.id,
        ))
        created += 1
    logger.info("Created %d candidates (with placeholder photos), assigned to exam.", created)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed_admin(session)
        await seed_exam_and_candidates(session)
        await session.commit()

        # Report counts.
        admins = await session.scalar(select(func.count()).select_from(Admin))
        exams = await session.scalar(select(func.count()).select_from(Exam))
        candidates = await session.scalar(select(func.count()).select_from(Candidate))
        logger.info(
            "DB totals -> admins=%s exams=%s candidates=%s",
            admins, exams, candidates,
        )


if __name__ == "__main__":
    asyncio.run(main())
