"""candidate id_type (CCCD | passport) + widen cccd column (AD-58)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-23 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column(
            "id_type",
            sa.String(length=16),
            nullable=False,
            server_default="cccd",
        ),
    )
    # Passports are ≤ 9 chars (fits 12) but widen for headroom + clarity.
    op.alter_column(
        "candidates", "cccd",
        existing_type=sa.String(length=12),
        type_=sa.String(length=20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "candidates", "cccd",
        existing_type=sa.String(length=20),
        type_=sa.String(length=12),
        existing_nullable=False,
    )
    op.drop_column("candidates", "id_type")
