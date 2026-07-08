"""Add organization_settings table — Sprint 54: Organization Administration Center.

Revision ID: e9f1a3b5c7d0
Revises: d6e8f0a2b4c3
Create Date: 2026-07-08 10:00:00.000000

Expand-only migration.  No destructive contract step.  Fully reversible.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PgUUID

# revision identifiers, used by Alembic.
revision: str = "e9f1a3b5c7d0"
down_revision: str = "d6e8f0a2b4c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create organization_settings table — one row per tenant (UNIQUE constraint)
    op.create_table(
        "organization_settings",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("organization_name", sa.String(255), nullable=False, server_default="My Organization"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column("date_format", sa.String(32), nullable=False, server_default="DD/MM/YYYY"),
        sa.Column("language", sa.String(16), nullable=False, server_default="en"),
        sa.Column("default_workflow_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("default_training_duration_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("default_invoice_due_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.PrimaryKeyConstraint("id"),
    )

    # One settings row per organization (tenant)
    op.create_index(
        "ix_organization_settings_tenant_id",
        "organization_settings",
        ["tenant_id"],
        unique=True,
    )
    op.create_index(
        "ix_organization_settings_is_active",
        "organization_settings",
        ["is_active"],
    )

    # Enable RLS
    op.execute("ALTER TABLE organization_settings ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY organization_settings_tenant_isolation
        ON organization_settings
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS organization_settings_tenant_isolation ON organization_settings")
    op.execute("ALTER TABLE organization_settings DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_organization_settings_is_active", table_name="organization_settings")
    op.drop_index("ix_organization_settings_tenant_id", table_name="organization_settings")
    op.drop_table("organization_settings")
