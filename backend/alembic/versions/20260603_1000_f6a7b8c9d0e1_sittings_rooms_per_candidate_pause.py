"""sittings + rooms + per-candidate pause (AD-47)

Splits a kỳ thi into sittings (buổi thi, each carrying its own đề) and rooms
(phòng thi). The đề/timing fields move off ``exams`` onto ``exam_sittings``;
``exam_sessions`` reparent onto a sitting and gain a per-candidate ``paused_at``.
Candidates gain a room assignment + seat number.

Backfills one sitting + one room per existing exam so current data degrades to the
"1 buổi / 1 phòng" special case without loss.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-03 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Rooms (phòng thi) -------------------------------------------------
    op.create_table(
        "exam_rooms",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("exam_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("proctor_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proctor_id"], ["admins.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exam_rooms_exam_id", "exam_rooms", ["exam_id"])
    op.create_index("ix_exam_rooms_proctor_id", "exam_rooms", ["proctor_id"])

    # 2) Sittings (buổi thi) — đề/timing move here from exams ---------------
    op.create_table(
        "exam_sittings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("exam_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("ordinal", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=True),
        sa.Column("shuffle_questions", sa.Boolean(),
                  server_default=sa.text("false"), nullable=False),
        sa.Column("shuffle_options", sa.Boolean(),
                  server_default=sa.text("false"), nullable=False),
        sa.Column("question_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("report_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exam_sittings_exam_id", "exam_sittings", ["exam_id"])
    op.create_index("ix_exam_sittings_status", "exam_sittings", ["status"])

    # 3) Candidate room assignment ----------------------------------------
    op.add_column("candidates", sa.Column("room_id", sa.UUID(), nullable=True))
    op.add_column("candidates", sa.Column("seat_number", sa.Integer(), nullable=True))
    op.create_index("ix_candidates_room_id", "candidates", ["room_id"])
    op.create_foreign_key(
        "fk_candidates_room_id_exam_rooms", "candidates", "exam_rooms",
        ["room_id"], ["id"], ondelete="SET NULL",
    )

    # 4) Session reparent + per-candidate pause (nullable first) -----------
    op.add_column("exam_sessions", sa.Column("sitting_id", sa.UUID(), nullable=True))
    op.add_column("exam_sessions",
                  sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_exam_sessions_sitting_id", "exam_sessions", ["sitting_id"])
    op.create_foreign_key(
        "fk_exam_sessions_sitting_id_exam_sittings", "exam_sessions", "exam_sittings",
        ["sitting_id"], ["id"], ondelete="CASCADE",
    )

    # 5) Backfill: one sitting + one room per exam, then repoint sessions ---
    op.execute(
        """
        INSERT INTO exam_sittings
            (id, exam_id, name, ordinal, duration_minutes, status,
             encrypted_payload, shuffle_questions, shuffle_options,
             question_count, report_snapshot, created_at, updated_at)
        SELECT gen_random_uuid(), e.id, 'Buổi thi 1', 1, e.duration_minutes,
               CASE WHEN e.status = 'active' THEN 'active' ELSE 'draft' END,
               e.encrypted_payload, e.shuffle_questions, e.shuffle_options,
               e.question_count, e.report_snapshot, now(), now()
        FROM exams e
        """
    )
    op.execute(
        """
        INSERT INTO exam_rooms (id, exam_id, name, proctor_id, created_at)
        SELECT gen_random_uuid(), e.id, 'Phòng 1', NULL, now() FROM exams e
        """
    )
    op.execute(
        """
        UPDATE exam_sessions s SET sitting_id = st.id
        FROM exam_sittings st WHERE st.exam_id = s.exam_id
        """
    )
    # Inherit any exam-wide pause onto the running candidates' sessions.
    op.execute(
        """
        UPDATE exam_sessions s SET paused_at = e.paused_at
        FROM exams e
        WHERE e.id = s.exam_id AND e.paused_at IS NOT NULL
          AND s.status = 'in_progress'
        """
    )

    # 6) Lock sitting_id NOT NULL + uniqueness ----------------------------
    op.alter_column("exam_sessions", "sitting_id", nullable=False)
    op.create_unique_constraint(
        "uq_session_candidate_sitting", "exam_sessions", ["candidate_id", "sitting_id"]
    )

    # 7) Drop đề/pause columns now owned by sittings/sessions -------------
    op.drop_column("exams", "encrypted_payload")
    op.drop_column("exams", "shuffle_questions")
    op.drop_column("exams", "shuffle_options")
    op.drop_column("exams", "question_count")
    op.drop_column("exams", "report_snapshot")
    op.drop_column("exams", "paused_at")


def downgrade() -> None:
    # Restore the đề/pause columns on exams.
    op.add_column("exams", sa.Column("encrypted_payload", sa.LargeBinary(), nullable=True))
    op.add_column("exams", sa.Column(
        "shuffle_questions", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("exams", sa.Column(
        "shuffle_options", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("exams", sa.Column(
        "question_count", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("exams", sa.Column(
        "report_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("exams", sa.Column(
        "paused_at", sa.DateTime(timezone=True), nullable=True))

    # Copy đề back from the first sitting of each exam.
    op.execute(
        """
        UPDATE exams e SET
            encrypted_payload = st.encrypted_payload,
            shuffle_questions = st.shuffle_questions,
            shuffle_options   = st.shuffle_options,
            question_count    = st.question_count,
            report_snapshot   = st.report_snapshot
        FROM exam_sittings st
        WHERE st.exam_id = e.id AND st.ordinal = 1
        """
    )

    op.drop_constraint("uq_session_candidate_sitting", "exam_sessions", type_="unique")
    op.drop_constraint(
        "fk_exam_sessions_sitting_id_exam_sittings", "exam_sessions", type_="foreignkey")
    op.drop_index("ix_exam_sessions_sitting_id", table_name="exam_sessions")
    op.drop_column("exam_sessions", "paused_at")
    op.drop_column("exam_sessions", "sitting_id")

    op.drop_constraint("fk_candidates_room_id_exam_rooms", "candidates", type_="foreignkey")
    op.drop_index("ix_candidates_room_id", table_name="candidates")
    op.drop_column("candidates", "seat_number")
    op.drop_column("candidates", "room_id")

    op.drop_index("ix_exam_sittings_status", table_name="exam_sittings")
    op.drop_index("ix_exam_sittings_exam_id", table_name="exam_sittings")
    op.drop_table("exam_sittings")
    op.drop_index("ix_exam_rooms_proctor_id", table_name="exam_rooms")
    op.drop_index("ix_exam_rooms_exam_id", table_name="exam_rooms")
    op.drop_table("exam_rooms")
