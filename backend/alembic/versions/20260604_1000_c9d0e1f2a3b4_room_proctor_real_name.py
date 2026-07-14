"""room proctor_real_name — real human name of the giám thị per exam/room

The giám thị accounts (giamthi1..10) are a fixed pool reused across exams. For
each exam the chủ tịch types the REAL name of the person sitting that room; it is
stored on the room so you can later look up which named person watched which room
(and thus which buổi, since rooms belong to an exam). A new exam creates new rooms
→ the name starts blank again ("resets") while history is preserved on old rooms.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-04 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exam_rooms", sa.Column(
        "proctor_real_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("exam_rooms", "proctor_real_name")
