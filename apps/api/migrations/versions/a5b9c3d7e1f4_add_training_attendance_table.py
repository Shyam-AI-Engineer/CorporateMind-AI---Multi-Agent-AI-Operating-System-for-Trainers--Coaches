"""add training_attendance table — Sprint 44.

Revision ID: a5b9c3d7e1f4
Revises: e3c7a1f9d2b4
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "a5b9c3d7e1f4"
down_revision = "e3c7a1f9d2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_attendance",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("participant_name", sa.String(255), nullable=False),
        sa.Column("participant_email", sa.String(255), nullable=True),
        sa.Column("participant_phone", sa.String(50), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("designation", sa.String(255), nullable=True),
        sa.Column(
            "attendance_status",
            sa.String(32),
            nullable=False,
            server_default="registered",
        ),
        sa.Column("check_in_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_out_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_percent", sa.Float, nullable=True),
        sa.Column(
            "certificate_eligible",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
        sa.Column("remarks", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # --- Indexes ---
    op.create_index(
        "ix_training_attendance_tenant_workspace",
        "training_attendance",
        ["tenant_id", "workspace_id"],
    )
    op.create_index(
        "ix_training_attendance_session_id",
        "training_attendance",
        ["session_id"],
    )
    op.create_index(
        "ix_training_attendance_status",
        "training_attendance",
        ["attendance_status"],
    )
    op.create_index(
        "ix_training_attendance_participant_email",
        "training_attendance",
        ["participant_email"],
    )
    # Keyset pagination index
    op.create_index(
        "ix_training_attendance_session_created_id",
        "training_attendance",
        ["session_id", "created_at", "id"],
    )

    # --- RLS ---
    op.execute("ALTER TABLE training_attendance ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY training_attendance_tenant_isolation
        ON training_attendance
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
    """)


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS training_attendance_tenant_isolation ON training_attendance"
    )
    op.drop_index(
        "ix_training_attendance_session_created_id",
        table_name="training_attendance",
    )
    op.drop_index(
        "ix_training_attendance_participant_email",
        table_name="training_attendance",
    )
    op.drop_index(
        "ix_training_attendance_status",
        table_name="training_attendance",
    )
    op.drop_index(
        "ix_training_attendance_session_id",
        table_name="training_attendance",
    )
    op.drop_index(
        "ix_training_attendance_tenant_workspace",
        table_name="training_attendance",
    )
    op.drop_table("training_attendance")
