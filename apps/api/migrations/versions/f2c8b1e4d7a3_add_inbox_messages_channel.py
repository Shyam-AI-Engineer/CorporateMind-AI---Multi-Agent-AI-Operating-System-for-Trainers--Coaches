"""Sprint 17A — add channel column to inbox_messages.

Revision ID: f2c8b1e4d7a3
Revises: e7b3f1a9d5c2
Create Date: 2026-06-20

EXPAND step only (no contract, no table rewrite, no data loss).

Adds to inbox_messages:
  channel  VARCHAR(30) nullable — "email" | "whatsapp" | future channels.

Backfill:
  All rows created before this migration are email-sourced (Gmail sync);
  UPDATE sets channel = 'email' for the existing population.

New index:
  uq_inbox_messages_wa_provider_message — partial unique index on
  (tenant_id, provider_message_id) WHERE channel = 'whatsapp'.

  This index serves two purposes:
    1. Lookup: find a WA inbox_message by its Meta wamid without knowing
       connection_id (e.g., from analytics or admin tooling).
    2. Safety net: the DB-level uniqueness backstop when Redis fails open
       during inbound replay protection.

  The existing uq_inbox_messages_connection_provider_message constraint on
  (connection_id, provider_message_id) continues to handle email dedup
  AND WhatsApp dedup (each workspace gets a stable WA InboxConnection, so
  connection_id + wamid is unique for WA too).

Downgrade:
  Drop the partial index, drop the channel column.
  All rows become connection-only identified again — safe because the
  older constraint was never altered.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2c8b1e4d7a3"
down_revision = "e7b3f1a9d5c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbox_messages",
        sa.Column("channel", sa.String(length=30), nullable=True),
    )

    # Backfill: every existing row was synced from Gmail.
    op.execute("UPDATE inbox_messages SET channel = 'email' WHERE channel IS NULL")

    # Partial unique index — WHERE channel = 'whatsapp' keeps it tiny; email rows
    # are covered by the existing (connection_id, provider_message_id) constraint.
    # Note: CONCURRENTLY omitted — Alembic transaction block forbids it.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_inbox_messages_wa_provider_message"
        " ON inbox_messages (tenant_id, provider_message_id)"
        " WHERE channel = 'whatsapp'"
    )

    # Composite index to support channel + received_at dashboard queries.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inbox_messages_channel_received_at"
        " ON inbox_messages (tenant_id, channel, received_at DESC)"
        " WHERE channel IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_inbox_messages_channel_received_at")
    op.execute("DROP INDEX IF EXISTS uq_inbox_messages_wa_provider_message")
    op.drop_column("inbox_messages", "channel")
