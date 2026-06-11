"""Sprint 8B follow-up cadence — expand follow_up_tasks (additive, reversible).

Revision ID: b1d7c4e9f2a8
Revises: b9c5d3e2f7a4
Create Date: 2026-06-11

EXPAND step only (ADR-0006 expand-then-contract; ADR-0008 §8).  All changes are
additive and reversible — no column is dropped, no NOT NULL is tightened on an
existing column, no destructive step ships here.

Adds to follow_up_tasks:
  • result_outbound_message_id  UUID NULL  — the draft OutboundMessage the cadence
      produced for this task (set on done / awaiting_approval).  Nullable because a
      task cancelled before generation never has one.
  • attempts  INTEGER NOT NULL DEFAULT 0  — claim counter; a ceiling retires poison
      rows.  server_default 0 backfills existing rows in place.

The `status` column already exists as VARCHAR(30); Sprint 8B widens its *vocabulary*
(adds 'processing' and 'awaiting_approval') with NO schema change — the values are
application-controlled strings, so no enum migration is needed.  This is the reason
status was modelled as a String rather than a PG enum.

RLS: follow_up_tasks already has ENABLE+FORCE ROW LEVEL SECURITY and the
tenant_isolation policy (from b9c5d3e2f7a4).  Adding columns does not affect the
policy, so no RLS DDL is required here.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1d7c4e9f2a8"
down_revision = "b9c5d3e2f7a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "follow_up_tasks",
        sa.Column("result_outbound_message_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "follow_up_tasks",
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    # Partial index for the cadence's hot path: the due-query filters on
    # status='pending' and orders by scheduled_for.  Keeps the sweep cheap as the
    # table grows with terminal (done/cancelled) rows.
    op.create_index(
        "ix_follow_up_tasks_pending_due",
        "follow_up_tasks",
        ["scheduled_for"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_follow_up_tasks_pending_due", table_name="follow_up_tasks")
    op.drop_column("follow_up_tasks", "attempts")
    op.drop_column("follow_up_tasks", "result_outbound_message_id")
