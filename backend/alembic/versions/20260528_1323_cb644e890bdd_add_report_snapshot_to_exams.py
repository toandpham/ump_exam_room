"""add report_snapshot to exams

Revision ID: cb644e890bdd
Revises: 018b8023adaf
Create Date: 2026-05-28 13:23:03.507759
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'cb644e890bdd'
down_revision: Union[str, None] = '018b8023adaf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exams", sa.Column("report_snapshot", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("exams", "report_snapshot")
