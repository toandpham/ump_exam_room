"""room capacity + per-room access token; drop candidate login_token (AD-48 v2)

Kiosk links are now per-MACHINE (room + seat position), not per-candidate. Each
room declares a capacity (number of machines) and carries a stable access_token;
the machine link = /exam/?room=<access_token>&seat=<n>. The old per-candidate
login_token is removed.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-03 13:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exam_rooms", sa.Column(
        "capacity", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("exam_rooms", sa.Column("access_token", sa.String(length=64), nullable=True))
    op.create_index("ix_exam_rooms_access_token", "exam_rooms", ["access_token"], unique=True)

    op.drop_index("ix_candidates_login_token", table_name="candidates")
    op.drop_column("candidates", "login_token")


def downgrade() -> None:
    op.add_column("candidates", sa.Column("login_token", sa.String(length=64), nullable=True))
    op.create_index("ix_candidates_login_token", "candidates", ["login_token"], unique=True)

    op.drop_index("ix_exam_rooms_access_token", table_name="exam_rooms")
    op.drop_column("exam_rooms", "access_token")
    op.drop_column("exam_rooms", "capacity")
