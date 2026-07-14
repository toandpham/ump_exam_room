"""add paused_at to exams

Revision ID: 018b8023adaf
Revises: 9426860906d8
Create Date: 2026-05-28 12:45:37.590088
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '018b8023adaf'
down_revision: Union[str, None] = '9426860906d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "exams",
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exams", "paused_at")
