"""Add notifications table — Sprint 32.

Revision ID: d7e2a5f8c3b1
Revises: b5c7d9e1f3a2
Create Date: 2026-06-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d7e2a5f8c3b1"
down_revision = "b5c7d9e1f3a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.String(32), nullable=False, server_default="medium"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_notifications_workspace_user_read",
        "notifications",
        ["workspace_id", "user_id", "is_read"],
    )
    op.create_index(
        "ix_notifications_workspace_created",
        "notifications",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_priority",
        "notifications",
        ["priority"],
    )

    op.execute(
        """
        ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
        CREATE POLICY notifications_tenant_isolation ON notifications
            USING (tenant_id = current_setting('app.tenant_id')::uuid);
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS notifications_tenant_isolation ON notifications;"
    )
    op.drop_index("ix_notifications_priority", table_name="notifications")
    op.drop_index("ix_notifications_workspace_created", table_name="notifications")
    op.drop_index("ix_notifications_workspace_user_read", table_name="notifications")
    op.drop_table("notifications")
