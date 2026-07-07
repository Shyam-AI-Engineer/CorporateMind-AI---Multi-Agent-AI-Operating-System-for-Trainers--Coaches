"""Add invoice_payments table.

Revision ID: c4e6f8a2b0d1
Revises: a2b4c6d8e0f2
Create Date: 2026-07-07

Expand-only migration.  Fully reversible downgrade.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "c4e6f8a2b0d1"
down_revision = "a2b4c6d8e0f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_payments",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("reference_number", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", PgUUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_invoice_payments_tenant_id", "invoice_payments", ["tenant_id"])
    op.create_index("ix_invoice_payments_workspace_id", "invoice_payments", ["workspace_id"])
    op.create_index("ix_invoice_payments_invoice_id", "invoice_payments", ["invoice_id"])
    op.create_index("ix_invoice_payments_customer_id", "invoice_payments", ["customer_id"])
    op.create_index("ix_invoice_payments_payment_date", "invoice_payments", ["payment_date"])
    op.create_index("ix_invoice_payments_status", "invoice_payments", ["status"])
    op.create_index(
        "ix_invoice_payments_reference_number", "invoice_payments", ["reference_number"]
    )

    op.execute("ALTER TABLE invoice_payments ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY invoice_payments_tenant_isolation ON invoice_payments
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS invoice_payments_tenant_isolation ON invoice_payments"
    )
    op.execute("ALTER TABLE invoice_payments DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_invoice_payments_reference_number", table_name="invoice_payments")
    op.drop_index("ix_invoice_payments_status", table_name="invoice_payments")
    op.drop_index("ix_invoice_payments_payment_date", table_name="invoice_payments")
    op.drop_index("ix_invoice_payments_customer_id", table_name="invoice_payments")
    op.drop_index("ix_invoice_payments_invoice_id", table_name="invoice_payments")
    op.drop_index("ix_invoice_payments_workspace_id", table_name="invoice_payments")
    op.drop_index("ix_invoice_payments_tenant_id", table_name="invoice_payments")
    op.drop_table("invoice_payments")
