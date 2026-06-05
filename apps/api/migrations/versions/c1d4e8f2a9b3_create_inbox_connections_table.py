"""Create inbox_connections table.

Revision ID: c1d4e8f2a9b3
Revises: e3f6a0b7c5d8
Create Date: 2026-06-05

Stores connected Gmail inboxes (and future providers) per workspace.
Phase 1: provider="gmail" only.

Encrypted columns (AES-256-GCM, base64url ciphertext — service layer only):
  email_address_enc  — plaintext email is never stored
  refresh_token_enc  — OAuth refresh token
  access_token_enc   — nullable; re-derivable from refresh_token at sync time

Deduplication:
  email_address_hash = HMAC-SHA256(email, tenant_id.bytes).hexdigest() — 64 hex chars
  Unique constraint uq_inbox_connections_tenant_email_hash prevents a workspace
  from connecting the same Gmail account twice within the same tenant.

Indexes:
  ix_inbox_connections_tenant_id        — standard tenant hot-path index
  ix_inbox_connections_workspace_id     — filter by workspace
  ix_inbox_connections_email_address_hash — dedup existence check without decryption
  ix_inbox_connections_status           — filter active / needs_reauth connections

RLS:
  ENABLE ROW LEVEL SECURITY + FORCE ROW LEVEL SECURITY applied so the app
  role (the table owner) is also subject to the policy.
  Policy uses the hardened NULLIF predicate (same as all tables post-b9f4e7d2a1c8).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1d4e8f2a9b3"
down_revision = "e3f6a0b7c5d8"
branch_labels = None
depends_on = None

_PREDICATE = "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "inbox_connections",
        sa.Column(
            "tenant_id",
            sa.UUID(),
            nullable=False,
            comment="Org-level tenant isolation key — must match app.tenant_id in RLS",
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        # Encrypted credentials — AES-256-GCM base64url ciphertext
        sa.Column("email_address_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=True),
        # HMAC-SHA256(email, tenant_id.bytes).hexdigest() — 64 hex chars
        sa.Column("email_address_hash", sa.String(length=64), nullable=False),
        # Space-separated OAuth scopes granted at connection time
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("token_expiry_at", sa.DateTime(timezone=True), nullable=True),
        # active | needs_reauth | revoked | error
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("connected_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "email_address_hash",
            name="uq_inbox_connections_tenant_email_hash",
        ),
    )
    op.create_index(
        op.f("ix_inbox_connections_tenant_id"),
        "inbox_connections",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbox_connections_workspace_id"),
        "inbox_connections",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbox_connections_email_address_hash"),
        "inbox_connections",
        ["email_address_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbox_connections_status"),
        "inbox_connections",
        ["status"],
        unique=False,
    )

    # RLS — same pattern as all tenant tables post-b9f4e7d2a1c8
    op.execute("ALTER TABLE inbox_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inbox_connections FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON inbox_connections"
        f"  USING ({_PREDICATE})"
        f"  WITH CHECK ({_PREDICATE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON inbox_connections")
    op.execute("ALTER TABLE inbox_connections NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inbox_connections DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_inbox_connections_status"), table_name="inbox_connections")
    op.drop_index(
        op.f("ix_inbox_connections_email_address_hash"),
        table_name="inbox_connections",
    )
    op.drop_index(
        op.f("ix_inbox_connections_workspace_id"), table_name="inbox_connections"
    )
    op.drop_index(
        op.f("ix_inbox_connections_tenant_id"), table_name="inbox_connections"
    )
    op.drop_table("inbox_connections")
