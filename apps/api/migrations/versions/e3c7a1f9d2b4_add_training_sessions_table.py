"""add training_sessions table — Sprint 43.

Revision ID: e3c7a1f9d2b4
Revises: d7c4b1e8a2f5
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "e3c7a1f9d2b4"
down_revision = "d7c4b1e8a2f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("engagement_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_name", sa.String(255), nullable=False),
        sa.Column("session_number", sa.Integer, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trainer_id", UUID(as_uuid=True), nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("meeting_link", sa.String(1000), nullable=True),
        sa.Column("capacity", sa.Integer, nullable=True),
        sa.Column("expected_attendees", sa.Integer, nullable=True),
        sa.Column("actual_attendees", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
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
        "ix_training_sessions_tenant_workspace",
        "training_sessions",
        ["tenant_id", "workspace_id"],
    )
    op.create_index(
        "ix_training_sessions_engagement_id",
        "training_sessions",
        ["engagement_id"],
    )
    op.create_index(
        "ix_training_sessions_trainer_id",
        "training_sessions",
        ["trainer_id"],
    )
    op.create_index(
        "ix_training_sessions_scheduled_start",
        "training_sessions",
        ["scheduled_start"],
    )
    op.create_index(
        "ix_training_sessions_status",
        "training_sessions",
        ["status"],
    )
    # Keyset pagination index
    op.create_index(
        "ix_training_sessions_engagement_created_id",
        "training_sessions",
        ["engagement_id", "created_at", "id"],
    )

    # --- RLS ---
    op.execute("ALTER TABLE training_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY training_sessions_tenant_isolation
        ON training_sessions
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS training_sessions_tenant_isolation ON training_sessions")
    op.drop_index("ix_training_sessions_engagement_created_id", table_name="training_sessions")
    op.drop_index("ix_training_sessions_status", table_name="training_sessions")
    op.drop_index("ix_training_sessions_scheduled_start", table_name="training_sessions")
    op.drop_index("ix_training_sessions_trainer_id", table_name="training_sessions")
    op.drop_index("ix_training_sessions_engagement_id", table_name="training_sessions")
    op.drop_index("ix_training_sessions_tenant_workspace", table_name="training_sessions")
    op.drop_table("training_sessions")
