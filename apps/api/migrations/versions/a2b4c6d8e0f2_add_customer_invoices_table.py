"""Add customer_invoices table — Sprint 51.

Revision ID: a2b4c6d8e0f2
Revises: f1a3b5c7d9e2
Create Date: 2026-07-07 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a2b4c6d8e0f2"
down_revision = "f1a3b5c7d9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(100), nullable=True),
        sa.Column("invoice_date", sa.Date, nullable=True),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True, server_default="INR"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("payment_date", sa.Date, nullable=True),
        sa.Column("renewal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_customer_invoices_tenant_id", "customer_invoices", ["tenant_id"])
    op.create_index("ix_customer_invoices_workspace_id", "customer_invoices", ["workspace_id"])
    op.create_index("ix_customer_invoices_customer_id", "customer_invoices", ["customer_id"])
    op.create_index("ix_customer_invoices_status", "customer_invoices", ["status"])
    op.create_index("ix_customer_invoices_invoice_date", "customer_invoices", ["invoice_date"])
    op.create_index("ix_customer_invoices_due_date", "customer_invoices", ["due_date"])
    op.create_index("ix_customer_invoices_renewal_id", "customer_invoices", ["renewal_id"])

    op.execute(
        """
        ALTER TABLE customer_invoices ENABLE ROW LEVEL SECURITY;

        CREATE POLICY customer_invoices_tenant_isolation
            ON customer_invoices
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP POLICY IF EXISTS customer_invoices_tenant_isolation ON customer_invoices;
        ALTER TABLE customer_invoices DISABLE ROW LEVEL SECURITY;
        """
    )
    op.drop_index("ix_customer_invoices_renewal_id", table_name="customer_invoices")
    op.drop_index("ix_customer_invoices_due_date", table_name="customer_invoices")
    op.drop_index("ix_customer_invoices_invoice_date", table_name="customer_invoices")
    op.drop_index("ix_customer_invoices_status", table_name="customer_invoices")
    op.drop_index("ix_customer_invoices_customer_id", table_name="customer_invoices")
    op.drop_index("ix_customer_invoices_workspace_id", table_name="customer_invoices")
    op.drop_index("ix_customer_invoices_tenant_id", table_name="customer_invoices")
    op.drop_table("customer_invoices")
