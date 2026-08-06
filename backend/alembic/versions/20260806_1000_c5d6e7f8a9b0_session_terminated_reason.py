"""exam_sessions: lý do đình chỉ thi

Chủ tịch dừng hẳn bài của một thí sinh (bắt gian lận, vi phạm quy chế). Bài vẫn được
chấm với những gì đã làm; cột này giữ lý do để hội đồng tra lại. Trạng thái phiên
chuyển sang ``terminated`` (giá trị chuỗi, không phải kiểu enum của CSDL nên không
cần đổi lược đồ cho riêng nó).

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-06 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exam_sessions",
        sa.Column("terminated_reason", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exam_sessions", "terminated_reason")
