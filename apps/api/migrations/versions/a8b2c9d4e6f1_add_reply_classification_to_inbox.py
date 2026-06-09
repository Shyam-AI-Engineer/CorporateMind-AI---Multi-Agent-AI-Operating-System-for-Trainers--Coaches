"""Add reply-classification columns to inbox_messages.

Revision ID: a8b2c9d4e6f1
Revises: d2e5f9a3b4c6
Create Date: 2026-06-09

Adds the three columns populated by ReplyClassifierAgent after a reply is
synced from Gmail.  reply_intent already exists from the original
inbox_messages migration (d2e5f9a3b4c6) — only confidence, classified_at,
and classification_model are new.

Expand-only:
  All three columns are nullable, so the migration is safe to run before
  the application starts writing to them.  Existing rows have NULL across
  the board until the next sync triggers classification.

Indexing:
  ix_inbox_messages_reply_intent — used by Sprint 4C onwards for CRM
  segmentation and analytics dashboards filtering on intent class.

No RLS change: inbox_messages already carries the hardened NULLIF predicate
from migration d2e5f9a3b4c6.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a8b2c9d4e6f1"
down_revision = "d2e5f9a3b4c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbox_messages",
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
    )
    op.add_column(
        "inbox_messages",
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "inbox_messages",
        sa.Column("classification_model", sa.String(length=100), nullable=True),
    )
    op.create_index(
        op.f("ix_inbox_messages_reply_intent"),
        "inbox_messages",
        ["reply_intent"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_inbox_messages_reply_intent"),
        table_name="inbox_messages",
    )
    op.drop_column("inbox_messages", "classification_model")
    op.drop_column("inbox_messages", "classified_at")
    op.drop_column("inbox_messages", "confidence")
