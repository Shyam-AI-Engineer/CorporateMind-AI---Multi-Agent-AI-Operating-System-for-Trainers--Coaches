"""add customers table — Sprint 41.

Revision ID: a3f7b2e9d4c1
Revises: b1e4a8d3f7c2
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "a3f7b2e9d4c1"
down_revision = "b1e4a8d3f7c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(128), nullable=True),
        sa.Column("website", sa.String(512), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(128), nullable=True),
        sa.Column("state", sa.String(128), nullable=True),
        sa.Column("country", sa.String(128), nullable=True),
        sa.Column("postal_code", sa.String(32), nullable=True),
        sa.Column("company_size", sa.String(64), nullable=True),
        sa.Column("annual_revenue_inr", sa.Numeric(precision=18, scale=2), nullable=True),
        # status: active | inactive | prospect | former
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        # health_status: healthy | attention | at_risk | inactive
        sa.Column("health_status", sa.String(32), nullable=False, server_default="healthy"),
        sa.Column("relationship_owner_id", UUID(as_uuid=True), nullable=True),
        sa.Column("primary_contact_name", sa.String(255), nullable=True),
        sa.Column("primary_contact_email", sa.String(255), nullable=True),
        sa.Column("primary_contact_phone", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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

    # ── Indexes ───────────────────────────────────────────────────────────────
    op.create_index("ix_customers_tenant_workspace", "customers", ["tenant_id", "workspace_id"])
    op.create_index("ix_customers_workspace", "customers", ["workspace_id"])
    op.create_index("ix_customers_status", "customers", ["status"])
    op.create_index("ix_customers_health_status", "customers", ["health_status"])
    op.create_index("ix_customers_industry", "customers", ["industry"])
    op.create_index("ix_customers_owner", "customers", ["relationship_owner_id"])
    op.create_index("ix_customers_company_name", "customers", ["company_name"])
    # Keyset pagination cursor index
    op.create_index(
        "ix_customers_workspace_created_id",
        "customers",
        ["workspace_id", "created_at", "id"],
    )

    # ── Row-Level Security ────────────────────────────────────────────────────
    op.execute("ALTER TABLE customers ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY customers_tenant_isolation ON customers
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS customers_tenant_isolation ON customers")
    op.execute("ALTER TABLE customers DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_customers_workspace_created_id", table_name="customers")
    op.drop_index("ix_customers_company_name", table_name="customers")
    op.drop_index("ix_customers_owner", table_name="customers")
    op.drop_index("ix_customers_industry", table_name="customers")
    op.drop_index("ix_customers_health_status", table_name="customers")
    op.drop_index("ix_customers_status", table_name="customers")
    op.drop_index("ix_customers_workspace", table_name="customers")
    op.drop_index("ix_customers_tenant_workspace", table_name="customers")
    op.drop_table("customers")
