"""add training_engagements table — Sprint 42.

Revision ID: d7c4b1e8a2f5
Revises: a3f7b2e9d4c1
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "d7c4b1e8a2f5"
down_revision = "a3f7b2e9d4c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_engagements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("program_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("training_type", sa.String(100), nullable=False),
        sa.Column("delivery_mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("priority", sa.String(32), nullable=False, server_default="medium"),
        sa.Column("planned_start_date", sa.Date, nullable=True),
        sa.Column("planned_end_date", sa.Date, nullable=True),
        sa.Column("actual_start_date", sa.Date, nullable=True),
        sa.Column("actual_end_date", sa.Date, nullable=True),
        sa.Column("estimated_participants", sa.Integer, nullable=True),
        sa.Column("actual_participants", sa.Integer, nullable=True),
        sa.Column("assigned_trainer_id", UUID(as_uuid=True), nullable=True),
        sa.Column("coordinator_id", UUID(as_uuid=True), nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("meeting_link", sa.String(1000), nullable=True),
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
        "ix_training_engagements_tenant_workspace",
        "training_engagements",
        ["tenant_id", "workspace_id"],
    )
    op.create_index(
        "ix_training_engagements_customer_id",
        "training_engagements",
        ["customer_id"],
    )
    op.create_index(
        "ix_training_engagements_status",
        "training_engagements",
        ["status"],
    )
    op.create_index(
        "ix_training_engagements_assigned_trainer_id",
        "training_engagements",
        ["assigned_trainer_id"],
    )
    op.create_index(
        "ix_training_engagements_planned_start_date",
        "training_engagements",
        ["planned_start_date"],
    )
    op.create_index(
        "ix_training_engagements_training_type",
        "training_engagements",
        ["training_type"],
    )
    # Keyset pagination index
    op.create_index(
        "ix_training_engagements_workspace_created_id",
        "training_engagements",
        ["workspace_id", "created_at", "id"],
    )

    # --- RLS ---
    op.execute("ALTER TABLE training_engagements ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY training_engagements_tenant_isolation
        ON training_engagements
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS training_engagements_tenant_isolation ON training_engagements")
    op.drop_index("ix_training_engagements_workspace_created_id", table_name="training_engagements")
    op.drop_index("ix_training_engagements_training_type", table_name="training_engagements")
    op.drop_index("ix_training_engagements_planned_start_date", table_name="training_engagements")
    op.drop_index("ix_training_engagements_assigned_trainer_id", table_name="training_engagements")
    op.drop_index("ix_training_engagements_status", table_name="training_engagements")
    op.drop_index("ix_training_engagements_customer_id", table_name="training_engagements")
    op.drop_index("ix_training_engagements_tenant_workspace", table_name="training_engagements")
    op.drop_table("training_engagements")
