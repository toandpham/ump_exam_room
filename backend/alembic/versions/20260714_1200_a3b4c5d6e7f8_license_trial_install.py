"""license: dùng thử theo installed_at, key gia hạn nullable (AD-81)

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-14 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Thêm installed_at (nullable trước để backfill), rồi ép NOT NULL.
    op.add_column("system_license",
                  sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True))
    # Dòng cũ (đã kích hoạt key): coi mốc cài = activated_at; nếu thiếu thì now().
    op.execute("UPDATE system_license SET installed_at = COALESCE(activated_at, now()) "
               "WHERE installed_at IS NULL")
    op.alter_column("system_license", "installed_at", nullable=False)
    # Key + activated_at giờ nullable (dùng thử không cần key).
    op.alter_column("system_license", "key", nullable=True)
    op.alter_column("system_license", "activated_at", nullable=True)


def downgrade() -> None:
    op.alter_column("system_license", "activated_at", nullable=False)
    op.alter_column("system_license", "key", nullable=False)
    op.drop_column("system_license", "installed_at")
