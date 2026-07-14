"""Drop dormant seat/kiosk columns + the unused questions table (AD-55 cleanup)

AD-53 removed seats/machines + kiosk login but left the DB columns "sleeping";
AD-12/27 moved all question content into per-sitting encrypted payloads, leaving
the questions table permanently empty (verified 0 rows). This migration removes
them for real:
  - exams.assigned_seating   (kiosk flag, never written since AD-53)
  - exam_rooms.access_token  (per-room kiosk link token)
  - candidates.seat_number   (seat within a room — rooms only now)
  - questions                (table; content lives in sitting payloads/Redis)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-10 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("exams", "assigned_seating")
    op.drop_index("ix_exam_rooms_access_token", table_name="exam_rooms")
    op.drop_column("exam_rooms", "access_token")
    op.drop_column("candidates", "seat_number")
    op.drop_index("ix_questions_exam_id", table_name="questions")
    op.drop_table("questions")


def downgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("exam_id", sa.UUID(), sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("image_path", sa.String(length=512), nullable=True),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correct_option", sa.String(length=1), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
    )
    op.create_index("ix_questions_exam_id", "questions", ["exam_id"])
    op.add_column("candidates", sa.Column("seat_number", sa.Integer(), nullable=True))
    op.add_column("exam_rooms", sa.Column("access_token", sa.String(length=64), nullable=True))
    op.create_index("ix_exam_rooms_access_token", "exam_rooms", ["access_token"], unique=True)
    op.add_column("exams", sa.Column(
        "assigned_seating", sa.Boolean(), nullable=False, server_default=sa.text("false")))
