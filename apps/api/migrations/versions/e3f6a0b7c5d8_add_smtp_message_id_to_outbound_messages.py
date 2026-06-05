"""Add smtp_message_id to outbound_messages.

Revision ID: e3f6a0b7c5d8
Revises: b9f4e7d2a1c8
Create Date: 2026-06-05

Adds the pre-generated SMTP Message-ID column that supports two capabilities:

  1. Write-before-send idempotency: the value is generated and persisted to DB
     before the aiosmtplib network call.  On Celery retry after a worker crash
     the existing value is reused so the same Message-ID header is sent, which
     prevents duplicate-message delivery warnings at the receiving MTA.

  2. Inbox reply matching: inbox_messages.smtp_message_id (the value extracted
     from In-Reply-To / References headers of an inbound reply) is joined against
     this column to identify which outbound triggered the reply.

Indexes:
  ix_outbound_messages_smtp_message_id              — point lookup by Message-ID
  ix_outbound_messages_tenant_smtp_message_id (composite) — tenant-scoped lookup
    used by the inbox reply matcher (SELECT ... WHERE tenant_id = ? AND
    smtp_message_id = ?); pushes the tenant filter into the index scan so the
    planner doesn't need a second filter step on un-isolated rows.

No RLS change: outbound_messages already carries the hardened NULLIF predicate
from migration b9f4e7d2a1c8.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e3f6a0b7c5d8"
down_revision = "b9f4e7d2a1c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbound_messages",
        sa.Column("smtp_message_id", sa.String(length=512), nullable=True),
    )
    op.create_index(
        op.f("ix_outbound_messages_smtp_message_id"),
        "outbound_messages",
        ["smtp_message_id"],
        unique=False,
    )
    op.create_index(
        "ix_outbound_messages_tenant_smtp_message_id",
        "outbound_messages",
        ["tenant_id", "smtp_message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbound_messages_tenant_smtp_message_id",
        table_name="outbound_messages",
    )
    op.drop_index(
        op.f("ix_outbound_messages_smtp_message_id"),
        table_name="outbound_messages",
    )
    op.drop_column("outbound_messages", "smtp_message_id")
