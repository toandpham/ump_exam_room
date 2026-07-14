"""add join_code to exams

Revision ID: cec7fe9c0f3f
Revises: fe7d68def6be
Create Date: 2026-05-28 10:05:38.465130
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cec7fe9c0f3f'
down_revision: Union[str, None] = 'fe7d68def6be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable first so we can backfill, then enforce NOT NULL + UNIQUE.
    op.add_column("exams", sa.Column("join_code", sa.String(length=12), nullable=True))
    # Backfill: 6-char codes using md5 of a random number (pgcrypto not required).
    # Per-row md5 → uppercase → strip 0/O/I/1/L look-alikes → take first 6.
    op.execute(r"""
        UPDATE exams SET join_code = substring(
          translate(upper(md5(random()::text || id::text)),
                    '0OI1L', '')
          FROM 1 FOR 6
        );
    """)
    op.alter_column("exams", "join_code", nullable=False)
    op.create_unique_constraint("uq_exams_join_code", "exams", ["join_code"])
    op.create_index("ix_exams_join_code", "exams", ["join_code"])


def downgrade() -> None:
    op.drop_index("ix_exams_join_code", table_name="exams")
    op.drop_constraint("uq_exams_join_code", "exams", type_="unique")
    op.drop_column("exams", "join_code")
