"""Add report_exports table — Sprint 56: Reporting & Export Center.

Revision ID: a1b3c5d7e9f2
Revises: f1a3b5c7d9e2
Create Date: 2026-07-08 14:00:00.000000

Expand-only migration.  No destructive contract step.  Fully reversible.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b3c5d7e9f2"
down_revision: str = "f1a3b5c7d9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_name", sa.String(255), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes for common access patterns
    op.create_index("ix_report_exports_tenant_id", "report_exports", ["tenant_id"])
    op.create_index(
        "ix_report_exports_workspace_id", "report_exports", ["workspace_id"]
    )
    op.create_index(
        "ix_report_exports_report_type", "report_exports", ["report_type"]
    )
    op.create_index(
        "ix_report_exports_generated_at", "report_exports", ["generated_at"]
    )
    # Composite index for the primary list query
    op.create_index(
        "ix_report_exports_tenant_ws_created",
        "report_exports",
        ["tenant_id", "workspace_id", "created_at"],
    )

    # Row-Level Security
    op.execute("ALTER TABLE report_exports ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY report_exports_tenant_isolation ON report_exports
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS report_exports_tenant_isolation ON report_exports")
    op.execute("ALTER TABLE report_exports DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_report_exports_tenant_ws_created", table_name="report_exports")
    op.drop_index("ix_report_exports_generated_at", table_name="report_exports")
    op.drop_index("ix_report_exports_report_type", table_name="report_exports")
    op.drop_index("ix_report_exports_workspace_id", table_name="report_exports")
    op.drop_index("ix_report_exports_tenant_id", table_name="report_exports")
    op.drop_table("report_exports")
