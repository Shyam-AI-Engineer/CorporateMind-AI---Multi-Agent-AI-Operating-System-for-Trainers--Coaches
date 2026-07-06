"""add customer_success table — Sprint 47.

Revision ID: e8d2f4a6b0c1
Revises: c3e5f7a9b1d4
Create Date: 2026-07-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "e8d2f4a6b0c1"
down_revision = "c3e5f7a9b1d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_success",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("health_status", sa.String(32), nullable=False, server_default="watch"),
        sa.Column("health_score", sa.SmallInteger(), nullable=True),
        sa.Column("risk_level", sa.String(32), nullable=False, server_default="medium"),
        sa.Column("owner_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("renewal_date", sa.Date(), nullable=True),
        sa.Column("last_contact_date", sa.Date(), nullable=True),
        sa.Column("next_followup_date", sa.Date(), nullable=True),
        sa.Column("expansion_opportunity", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("renewal_probability", sa.SmallInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # One success record per customer
    op.create_unique_constraint(
        "uq_customer_success_customer_id",
        "customer_success",
        ["customer_id"],
    )

    # Composite index for the most-common list query (tenant + workspace)
    op.create_index(
        "ix_customer_success_tenant_workspace",
        "customer_success",
        ["tenant_id", "workspace_id"],
    )
    op.create_index("ix_customer_success_owner_user_id", "customer_success", ["owner_user_id"])
    op.create_index("ix_customer_success_renewal_date", "customer_success", ["renewal_date"])
    op.create_index("ix_customer_success_health_status", "customer_success", ["health_status"])
    op.create_index("ix_customer_success_risk_level", "customer_success", ["risk_level"])
    op.create_index("ix_customer_success_next_followup_date", "customer_success", ["next_followup_date"])

    # Row-Level Security — tenant isolation
    op.execute("ALTER TABLE customer_success ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY customer_success_tenant_isolation
        ON customer_success
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS customer_success_tenant_isolation ON customer_success"
    )
    op.drop_table("customer_success")
