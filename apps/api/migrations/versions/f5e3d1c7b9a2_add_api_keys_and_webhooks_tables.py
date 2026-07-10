"""Add api_keys and webhooks tables — Sprint 55: Integration Hub.

Revision ID: f5e3d1c7b9a2
Revises: e9f1a3b5c7d0
Create Date: 2026-07-08 11:00:00.000000

Expand-only migration.  No destructive contract step.  Fully reversible.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID

revision: str = "f5e3d1c7b9a2"
down_revision: str = "e9f1a3b5c7d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── api_keys ──────────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", PgUUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_workspace_id", "api_keys", ["workspace_id"])
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"], unique=True)
    op.create_index("ix_api_keys_is_active", "api_keys", ["is_active"])

    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY api_keys_tenant_isolation
        ON api_keys
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )

    # ── webhooks ──────────────────────────────────────────────────────────────
    op.create_table(
        "webhooks",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(128), nullable=False),
        sa.Column("events", JSONB, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", PgUUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhooks_tenant_id", "webhooks", ["tenant_id"])
    op.create_index("ix_webhooks_workspace_id", "webhooks", ["workspace_id"])
    op.create_index("ix_webhooks_is_active", "webhooks", ["is_active"])

    op.execute("ALTER TABLE webhooks ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY webhooks_tenant_isolation
        ON webhooks
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS webhooks_tenant_isolation ON webhooks")
    op.execute("ALTER TABLE webhooks DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_webhooks_is_active", table_name="webhooks")
    op.drop_index("ix_webhooks_workspace_id", table_name="webhooks")
    op.drop_index("ix_webhooks_tenant_id", table_name="webhooks")
    op.drop_table("webhooks")

    op.execute("DROP POLICY IF EXISTS api_keys_tenant_isolation ON api_keys")
    op.execute("ALTER TABLE api_keys DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_api_keys_is_active", table_name="api_keys")
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_workspace_id", table_name="api_keys")
    op.drop_index("ix_api_keys_tenant_id", table_name="api_keys")
    op.drop_table("api_keys")
