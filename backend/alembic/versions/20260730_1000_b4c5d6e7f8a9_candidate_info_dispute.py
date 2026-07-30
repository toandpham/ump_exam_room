"""candidates: cờ "thí sinh báo sai thông tin" để giám sát nhìn thấy (AD-122)

Trước đây bấm "Báo giám thị" chỉ phát qua WebSocket cho trang quản trị, mà bộ nghe
đã bị gỡ cùng box Thông báo (AD-77) → không ai thấy. Ghi vào hồ sơ thí sinh để nhãn
hiện ngay trên dòng của người đó ở bảng giám sát và bảng phòng, qua nhịp poll sẵn có.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-30 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column("info_disputed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidates", "info_disputed_at")
