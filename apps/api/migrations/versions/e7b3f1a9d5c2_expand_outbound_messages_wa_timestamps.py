"""Sprint 16B — expand outbound_messages with WhatsApp delivery timestamps.

Revision ID: e7b3f1a9d5c2
Revises: c4f2a8e1d9b6
Create Date: 2026-06-19

EXPAND step only (ADR-0006 / ADR-0010).

Root cause addressed:
  Sprint 16A delivery receipts update outbound_messages.status but the
  analytics rollup reads campaign_recipients.delivered_at / opened_at —
  two disconnected tables.  Adding timestamps to outbound_messages lets the
  rollup derive WA delivery/read counts directly by date.

Adds to outbound_messages:
  delivered_at  — UTC timestamp written on first Meta 'delivered' receipt.
                  Subsequent receipts are ignored (first-write-wins in repo).
  read_at       — UTC timestamp written on first Meta 'read' receipt.
                  Equivalent to email 'opened'; blue-ticks in WhatsApp.
  failed_at     — UTC timestamp written when Meta signals permanent failure.
                  Enables WA failure-rate SLO alerting.

All columns:
  - Nullable (no backfill, no table rewrite, safe for historical rows).
  - Indexed with partial WHERE IS NOT NULL so index size stays small —
    most rows will have NULL for months after launch.
  - Partial indexes on (tenant_id, col) support date-range rollup queries
    that are always tenant-scoped.

Downgrades are clean: drop indexes then drop columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7b3f1a9d5c2"
down_revision = "c4f2a8e1d9b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbound_messages",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outbound_messages",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outbound_messages",
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Partial indexes — WHERE IS NOT NULL keeps the index tiny; the rollup
    # queries always filter on the column being non-null anyway.
    # Note: CONCURRENTLY is omitted because Alembic wraps migrations in a
    # transaction and PostgreSQL forbids CONCURRENTLY inside a transaction block.
    # The table is empty at first migration time so the brief lock is acceptable.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outbound_messages_delivered_at"
        " ON outbound_messages (tenant_id, delivered_at)"
        " WHERE delivered_at IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outbound_messages_read_at"
        " ON outbound_messages (tenant_id, read_at)"
        " WHERE read_at IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outbound_messages_failed_at"
        " ON outbound_messages (tenant_id, failed_at)"
        " WHERE failed_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_outbound_messages_failed_at")
    op.execute("DROP INDEX IF EXISTS ix_outbound_messages_read_at")
    op.execute("DROP INDEX IF EXISTS ix_outbound_messages_delivered_at")

    op.drop_column("outbound_messages", "failed_at")
    op.drop_column("outbound_messages", "read_at")
    op.drop_column("outbound_messages", "delivered_at")
