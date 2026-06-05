"""Create inbox_messages table.

Revision ID: d2e5f9a3b4c6
Revises: c1d4e8f2a9b3
Create Date: 2026-06-05

Stores individual inbound emails synced from connected Gmail inboxes.

Foreign keys:
  connection_id → inbox_connections.id  ON DELETE CASCADE
    Synced messages are deleted when their connection is removed.
  outbound_message_id → outbound_messages.id  ON DELETE SET NULL
    Preserves the inbox record if the matched outbound is later deleted;
    the reply is still visible in the inbox view, just unlinked.

Deduplication:
  uq_inbox_messages_connection_provider_message on (connection_id, provider_message_id)
  Prevents duplicate rows if a sync job runs twice for the same Gmail message ID.

Thread matching:
  smtp_message_id — extracted from In-Reply-To / References headers of the inbound;
  compared against outbound_messages.smtp_message_id to find the outbound we sent.
  ix_inbox_messages_tenant_smtp_message_id (composite) mirrors the matching index on
  outbound_messages so both sides of the join scan with the same predicate shape.

Encrypted columns:
  body_snippet_enc — first ~500 chars of plain-text body, AES-256-GCM base64url.
  Text (unbounded) — ciphertext for 500 chars of input is ~700 base64 chars;
  no String(N) bound to avoid silent truncation of the ciphertext.

RLS:
  ENABLE ROW LEVEL SECURITY + FORCE ROW LEVEL SECURITY applied.
  Policy uses the hardened NULLIF predicate (same as all tables post-b9f4e7d2a1c8).
  Note: connection_id FK reaches inbox_connections which is itself RLS-guarded,
  giving a second layer of isolation at the join level.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d2e5f9a3b4c6"
down_revision = "c1d4e8f2a9b3"
branch_labels = None
depends_on = None

_PREDICATE = "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "inbox_messages",
        sa.Column(
            "tenant_id",
            sa.UUID(),
            nullable=False,
            comment="Org-level tenant isolation key — must match app.tenant_id in RLS",
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("connection_id", sa.UUID(), nullable=False),
        # Gmail message ID (opaque string from Gmail API, e.g. "17a3b4c5d6e7f890")
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        # Gmail thread ID — enables thread-level reply grouping
        sa.Column("provider_thread_id", sa.String(length=255), nullable=True),
        # Extracted from In-Reply-To or References headers; matched against
        # outbound_messages.smtp_message_id to identify the outbound we sent
        sa.Column("smtp_message_id", sa.String(length=512), nullable=True),
        # Raw In-Reply-To header value (single Message-ID, RFC 2822)
        sa.Column("in_reply_to", sa.String(length=512), nullable=True),
        # Raw References header value (space-separated Message-IDs, RFC 2822)
        # Named references_header to avoid the PostgreSQL reserved keyword REFERENCES
        sa.Column("references_header", sa.Text(), nullable=True),
        # Set after matching; SET NULL preserves inbox record if outbound is deleted
        sa.Column("outbound_message_id", sa.UUID(), nullable=True),
        # How the outbound match was established:
        # "message_id" | "in_reply_to" | "thread_id" | "subject" | null (unmatched)
        sa.Column("match_method", sa.String(length=50), nullable=True),
        # from_address stored plaintext — sender is counterparty, not our contacts' PII
        sa.Column("from_address", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        # AES-256-GCM encrypted first ~500 chars of plain-text body
        sa.Column("body_snippet_enc", sa.Text(), nullable=True),
        # True when the full body exceeds the 500-char snippet limit
        sa.Column("body_truncated", sa.Boolean(), nullable=False),
        # interested | not_interested | question | out_of_office | auto_reply | unknown
        sa.Column("reply_intent", sa.String(length=50), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["inbox_connections.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["outbound_message_id"],
            ["outbound_messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "provider_message_id",
            name="uq_inbox_messages_connection_provider_message",
        ),
    )

    # Standard per-column indexes
    op.create_index(
        op.f("ix_inbox_messages_tenant_id"),
        "inbox_messages",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbox_messages_connection_id"),
        "inbox_messages",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbox_messages_received_at"),
        "inbox_messages",
        ["received_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbox_messages_smtp_message_id"),
        "inbox_messages",
        ["smtp_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbox_messages_outbound_message_id"),
        "inbox_messages",
        ["outbound_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbox_messages_provider_thread_id"),
        "inbox_messages",
        ["provider_thread_id"],
        unique=False,
    )

    # Composite index: mirrors ix_outbound_messages_tenant_smtp_message_id so the
    # inbox reply matcher executes a symmetric tenant-scoped lookup on both sides
    op.create_index(
        "ix_inbox_messages_tenant_smtp_message_id",
        "inbox_messages",
        ["tenant_id", "smtp_message_id"],
        unique=False,
    )

    # RLS — same pattern as all tenant tables post-b9f4e7d2a1c8
    op.execute("ALTER TABLE inbox_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inbox_messages FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON inbox_messages"
        f"  USING ({_PREDICATE})"
        f"  WITH CHECK ({_PREDICATE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON inbox_messages")
    op.execute("ALTER TABLE inbox_messages NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inbox_messages DISABLE ROW LEVEL SECURITY")

    op.drop_index(
        "ix_inbox_messages_tenant_smtp_message_id", table_name="inbox_messages"
    )
    op.drop_index(
        op.f("ix_inbox_messages_provider_thread_id"), table_name="inbox_messages"
    )
    op.drop_index(
        op.f("ix_inbox_messages_outbound_message_id"), table_name="inbox_messages"
    )
    op.drop_index(
        op.f("ix_inbox_messages_smtp_message_id"), table_name="inbox_messages"
    )
    op.drop_index(
        op.f("ix_inbox_messages_received_at"), table_name="inbox_messages"
    )
    op.drop_index(
        op.f("ix_inbox_messages_connection_id"), table_name="inbox_messages"
    )
    op.drop_index(
        op.f("ix_inbox_messages_tenant_id"), table_name="inbox_messages"
    )
    op.drop_table("inbox_messages")
