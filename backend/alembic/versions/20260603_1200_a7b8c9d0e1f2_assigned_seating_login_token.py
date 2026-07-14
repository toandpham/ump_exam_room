"""assigned_seating on exams + login_token on candidates (AD-48 kiosk auto-login)

When an exam uses ``assigned_seating``, each candidate is pre-bound to a machine
and gets a random ``login_token``; opening that machine's link auto-logs the
assigned candidate in (no CCCD typing).

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-03 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exams", sa.Column(
        "assigned_seating", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("candidates", sa.Column("login_token", sa.String(length=64), nullable=True))
    op.create_index("ix_candidates_login_token", "candidates", ["login_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_candidates_login_token", table_name="candidates")
    op.drop_column("candidates", "login_token")
    op.drop_column("exams", "assigned_seating")
