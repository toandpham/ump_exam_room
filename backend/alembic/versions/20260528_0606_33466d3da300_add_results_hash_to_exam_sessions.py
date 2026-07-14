"""add results_hash to exam_sessions

Revision ID: 33466d3da300
Revises: baaace43524f
Create Date: 2026-05-28 06:06:48.463623
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33466d3da300'
down_revision: Union[str, None] = 'baaace43524f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "exam_sessions",
        sa.Column("results_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exam_sessions", "results_hash")
