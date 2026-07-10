"""Sprint 59 — add bulk_operations table (expand-only).

Revision ID: g1a2b3c4d5e6
Revises: f6d2c4a8e1b7
Create Date: 2026-07-09

EXPAND-ONLY migration (no destructive changes to existing tables).

Creates:
  bulk_operations
    Tracks every user-triggered bulk operation (CSV import, bulk archive,
    bulk assign, bulk status update, dry-run validation).
    Fully tenant-scoped with RLS.
    operation_type: csv_import | csv_validate | bulk_archive |
                    bulk_status_update | bulk_assignment | dry_run
    entity_type: customers | training_engagements | business_tasks |
                 workflow_templates
    status: pending | running | completed | failed | cancelled

Reversible: downgrade drops RLS policy, indexes, and the table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg


revision = "g1a2b3c4d5e6"
down_revision = "f6d2c4a8e1b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bulk_operations",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_type", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("requested_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("total_records", sa.Integer, nullable=False, server_default="0"),
        sa.Column("processed_records", sa.Integer, nullable=False, server_default="0"),
        sa.Column("successful_records", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_records", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_bulk_ops_tenant",
        "bulk_operations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_bulk_ops_workspace",
        "bulk_operations",
        ["tenant_id", "workspace_id"],
    )
    op.create_index(
        "ix_bulk_ops_entity_type",
        "bulk_operations",
        ["tenant_id", "entity_type"],
    )
    op.create_index(
        "ix_bulk_ops_status",
        "bulk_operations",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_bulk_ops_created_at",
        "bulk_operations",
        ["tenant_id", "created_at"],
    )

    op.execute("ALTER TABLE bulk_operations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE bulk_operations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY bulk_operations_tenant_isolation
          ON bulk_operations
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS bulk_operations_tenant_isolation ON bulk_operations")
    op.drop_index("ix_bulk_ops_created_at", "bulk_operations")
    op.drop_index("ix_bulk_ops_status", "bulk_operations")
    op.drop_index("ix_bulk_ops_entity_type", "bulk_operations")
    op.drop_index("ix_bulk_ops_workspace", "bulk_operations")
    op.drop_index("ix_bulk_ops_tenant", "bulk_operations")
    op.drop_table("bulk_operations")
