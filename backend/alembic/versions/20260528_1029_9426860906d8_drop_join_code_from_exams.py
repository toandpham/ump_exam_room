"""drop join_code from exams

Revision ID: 9426860906d8
Revises: cec7fe9c0f3f
Create Date: 2026-05-28 10:29:35.675193
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9426860906d8'
down_revision: Union[str, None] = 'cec7fe9c0f3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_exams_join_code", table_name="exams")
    op.drop_constraint("uq_exams_join_code", "exams", type_="unique")
    op.drop_column("exams", "join_code")


def downgrade() -> None:
    op.add_column("exams", sa.Column("join_code", sa.String(length=12), nullable=True))
    op.create_unique_constraint("uq_exams_join_code", "exams", ["join_code"])
    op.create_index("ix_exams_join_code", "exams", ["join_code"])
