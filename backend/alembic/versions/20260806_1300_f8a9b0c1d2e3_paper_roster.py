"""exam_sittings: danh sách thí sinh đã in phiếu trả lời giấy

Phiếu in mã thí sinh bằng bóng tròn nhị phân (14 bit) chứ không phải số báo danh —
đọc bóng tròn thì dùng đúng bộ đọc đã có, đọc chữ thì phải thêm cả một tầng nhận
dạng ký tự. Cột này giữ ánh xạ mã ↔ thí sinh ĐÚNG NHƯ LÚC IN.

Vì sao phải lưu chứ không tính lại lúc quét: nếu suy ra mã từ thứ tự danh sách hiện
tại thì chỉ cần thêm/bớt một thí sinh giữa lúc in và lúc quét là toàn bộ bài bị gán
nhầm người — sai âm thầm, không có dấu hiệu nào.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-08-06 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exam_sittings",
                  sa.Column("paper_roster", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("exam_sittings", "paper_roster")
