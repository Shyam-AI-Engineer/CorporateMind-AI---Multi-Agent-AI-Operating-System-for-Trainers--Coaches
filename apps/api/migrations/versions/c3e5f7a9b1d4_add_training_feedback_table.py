"""add training_feedback table — Sprint 46.

Revision ID: c3e5f7a9b1d4
Revises: b2d4e6f8a0c2
Create Date: 2026-07-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "c3e5f7a9b1d4"
down_revision = "b2d4e6f8a0c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("attendance_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("trainer_id", UUID(as_uuid=True), nullable=True),
        sa.Column("overall_rating", sa.SmallInteger(), nullable=True),
        sa.Column("trainer_rating", sa.SmallInteger(), nullable=True),
        sa.Column("content_rating", sa.SmallInteger(), nullable=True),
        sa.Column("materials_rating", sa.SmallInteger(), nullable=True),
        sa.Column("venue_rating", sa.SmallInteger(), nullable=True),
        sa.Column("would_recommend", sa.Boolean(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # One feedback record per attendance
    op.create_unique_constraint(
        "uq_training_feedback_attendance_id",
        "training_feedback",
        ["attendance_id"],
    )

    # Composite index for the most-common list query (tenant + workspace)
    op.create_index(
        "ix_training_feedback_tenant_workspace",
        "training_feedback",
        ["tenant_id", "workspace_id"],
    )
    op.create_index("ix_training_feedback_session_id", "training_feedback", ["session_id"])
    op.create_index("ix_training_feedback_customer_id", "training_feedback", ["customer_id"])
    op.create_index("ix_training_feedback_trainer_id", "training_feedback", ["trainer_id"])
    op.create_index("ix_training_feedback_overall_rating", "training_feedback", ["overall_rating"])

    # Row-Level Security — tenant isolation
    op.execute("ALTER TABLE training_feedback ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY training_feedback_tenant_isolation
        ON training_feedback
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS training_feedback_tenant_isolation ON training_feedback"
    )
    op.drop_table("training_feedback")
