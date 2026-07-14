"""add totp 2fa columns to admins

Revision ID: a1b2c3d4e5f6
Revises: cb644e890bdd
Create Date: 2026-05-29 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'cb644e890bdd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("admins", sa.Column("totp_secret", sa.String(length=64), nullable=True))
    op.add_column(
        "admins",
        sa.Column(
            "totp_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("admins", "totp_enabled")
    op.drop_column("admins", "totp_secret")
