"""Add customer_renewals table — Sprint 48.

Revision ID: f1a3b5c7d9e2
Revises: e8d2f4a6b0c1
Create Date: 2026-07-06 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f1a3b5c7d9e2"
down_revision = "e8d2f4a6b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_renewals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_name", sa.String(255), nullable=True),
        sa.Column("contract_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("renewal_type", sa.String(32), nullable=False, server_default="annual"),
        sa.Column("renewal_status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("renewal_date", sa.Date, nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("probability", sa.SmallInteger, nullable=True),
        sa.Column("expected_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_customer_renewals_tenant_id", "customer_renewals", ["tenant_id"])
    op.create_index(
        "ix_customer_renewals_customer_id", "customer_renewals", ["customer_id"]
    )
    op.create_index(
        "ix_customer_renewals_renewal_date", "customer_renewals", ["renewal_date"]
    )
    op.create_index(
        "ix_customer_renewals_renewal_status", "customer_renewals", ["renewal_status"]
    )
    op.create_index(
        "ix_customer_renewals_owner_user_id", "customer_renewals", ["owner_user_id"]
    )
    op.create_index(
        "ix_customer_renewals_proposal_id", "customer_renewals", ["proposal_id"]
    )
    op.create_index(
        "ix_customer_renewals_workspace_id", "customer_renewals", ["workspace_id"]
    )

    op.execute(
        """
        ALTER TABLE customer_renewals ENABLE ROW LEVEL SECURITY;

        CREATE POLICY customer_renewals_tenant_isolation
            ON customer_renewals
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP POLICY IF EXISTS customer_renewals_tenant_isolation ON customer_renewals;
        ALTER TABLE customer_renewals DISABLE ROW LEVEL SECURITY;
        """
    )
    op.drop_index("ix_customer_renewals_workspace_id", table_name="customer_renewals")
    op.drop_index("ix_customer_renewals_proposal_id", table_name="customer_renewals")
    op.drop_index("ix_customer_renewals_owner_user_id", table_name="customer_renewals")
    op.drop_index("ix_customer_renewals_renewal_status", table_name="customer_renewals")
    op.drop_index("ix_customer_renewals_renewal_date", table_name="customer_renewals")
    op.drop_index("ix_customer_renewals_customer_id", table_name="customer_renewals")
    op.drop_index("ix_customer_renewals_tenant_id", table_name="customer_renewals")
    op.drop_table("customer_renewals")
