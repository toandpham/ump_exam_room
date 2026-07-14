"""persist question_count on exams

Revision ID: fe7d68def6be
Revises: 33466d3da300
Create Date: 2026-05-28 09:51:53.210130
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe7d68def6be'
down_revision: Union[str, None] = '33466d3da300'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "exams",
        sa.Column("question_count", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
    )
    # Backfill: for rows whose encrypted_payload still exists, peel the
    # unencrypted question_count out of the JSON header. Closed/purged rows
    # stay at 0 (their content is intentionally gone). For legacy hand-
    # authored drafts, fall back to a COUNT() of the questions table.
    op.execute("""
        UPDATE exams
        SET question_count = COALESCE(
          NULLIF(substring(
            convert_from(encrypted_payload, 'UTF8')
            FROM '"question_count"\\s*:\\s*([0-9]+)'
          ), '')::INTEGER,
          (SELECT count(*) FROM questions WHERE exam_id = exams.id),
          0
        )
        WHERE encrypted_payload IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column("exams", "question_count")
