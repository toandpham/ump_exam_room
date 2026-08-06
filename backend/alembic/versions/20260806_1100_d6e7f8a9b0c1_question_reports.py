"""question_reports: thí sinh khiếu nại về một câu hỏi, gắn vào bài thi

Kênh cho "câu 47 thiếu hình" / "câu 12 không có đáp án đúng". Khác với cờ "báo sai
thông tin" (AD-122) vốn chỉ dùng cho thông tin cá nhân. Nội dung lưu cùng bài để hội
đồng đọc khi chấm.

Không có khoá ngoại tới câu hỏi: đề chỉ sống trong Redis, không có dòng nào trong
CSDL (AD-12) — question_id là id câu trong payload.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-08-06 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sitting_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("exam_sittings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolution", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_question_reports_session_id", "question_reports", ["session_id"])
    op.create_index("ix_question_reports_candidate_id", "question_reports", ["candidate_id"])
    op.create_index("ix_question_reports_sitting_id", "question_reports", ["sitting_id"])


def downgrade() -> None:
    op.drop_table("question_reports")
