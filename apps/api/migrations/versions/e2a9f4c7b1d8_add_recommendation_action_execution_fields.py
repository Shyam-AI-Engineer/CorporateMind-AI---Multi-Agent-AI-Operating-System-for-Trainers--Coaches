"""Sprint 26A — add execution fields to recommendation_actions.

Revision ID: e2a9f4c7b1d8
Revises: d5f3b8e2a7c9
Create Date: 2026-06-26

Expand-only migration: adds 7 nullable columns to recommendation_actions
to support the Recommendation Work Queue execution workflow.

  execution_status   — current execution state (in_progress/completed/blocked/cancelled)
  started_at         — when the trainer clicked Start
  completed_at       — when the trainer clicked Complete
  blocked_at         — when the trainer clicked Block
  cancelled_at       — when the trainer clicked Cancel
  blocked_reason     — reason for blocking or cancelling (shared column)
  completion_notes   — optional notes on completion

No existing columns are modified. No destructive changes.
All new columns are nullable so existing rows remain valid.
RLS is already enabled from the d5f3b8e2a7c9 migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "e2a9f4c7b1d8"
down_revision: str = "d5f3b8e2a7c9"
branch_labels = None
depends_on = None

_TABLE = "recommendation_actions"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("execution_status", sa.String(20), nullable=True))
    op.add_column(_TABLE, sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(_TABLE, sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(_TABLE, sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(_TABLE, sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(_TABLE, sa.Column("blocked_reason", sa.Text(), nullable=True))
    op.add_column(_TABLE, sa.Column("completion_notes", sa.Text(), nullable=True))

    # Index for queue queries filtered by execution_status
    op.create_index(
        "ix_rec_actions_execution_status",
        _TABLE,
        ["tenant_id", "workspace_id", "execution_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rec_actions_execution_status", table_name=_TABLE)
    op.drop_column(_TABLE, "completion_notes")
    op.drop_column(_TABLE, "blocked_reason")
    op.drop_column(_TABLE, "cancelled_at")
    op.drop_column(_TABLE, "blocked_at")
    op.drop_column(_TABLE, "completed_at")
    op.drop_column(_TABLE, "started_at")
    op.drop_column(_TABLE, "execution_status")
