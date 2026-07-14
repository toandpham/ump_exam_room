"""add created_by (owning proctor) to exams

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-29 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exams", sa.Column("created_by", sa.UUID(), nullable=True))
    op.create_index("ix_exams_created_by", "exams", ["created_by"])
    op.create_foreign_key(
        "fk_exams_created_by_admins", "exams", "admins",
        ["created_by"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_exams_created_by_admins", "exams", type_="foreignkey")
    op.drop_index("ix_exams_created_by", table_name="exams")
    op.drop_column("exams", "created_by")
