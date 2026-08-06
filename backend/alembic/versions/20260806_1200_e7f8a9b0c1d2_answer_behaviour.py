"""answers + exam_sessions: dữ liệu hành vi làm bài

Ba cột phục vụ hậu kiểm, không đổi cách chấm điểm:
  - answers.first_answered_at: lần CHỌN ĐẦU TIÊN cho câu đó (answered_at hiện tại
    bị ghi đè mỗi lần đổi nên không biết được lúc quyết định đầu).
  - answers.change_count: số lần đổi đáp án sau lần đầu.
  - exam_sessions.viewed_count: số câu thí sinh đã từng xem tới (máy báo về, ghép
    vào nhịp đẩy đáp án sẵn có nên không thêm request nào).

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-06 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("answers",
                  sa.Column("first_answered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("answers",
                  sa.Column("change_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("exam_sessions",
                  sa.Column("viewed_count", sa.Integer(), nullable=True))
    # Dòng cũ: coi lần ghi hiện có là lần đầu — không có dữ liệu nào tốt hơn, và để
    # NULL thì mọi phép tính sau này phải xử lý riêng.
    op.execute("UPDATE answers SET first_answered_at = answered_at "
               "WHERE first_answered_at IS NULL")


def downgrade() -> None:
    op.drop_column("exam_sessions", "viewed_count")
    op.drop_column("answers", "change_count")
    op.drop_column("answers", "first_answered_at")
