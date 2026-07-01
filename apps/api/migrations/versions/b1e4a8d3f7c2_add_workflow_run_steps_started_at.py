"""add started_at to workflow_run_steps — Sprint 39.

Revision ID: b1e4a8d3f7c2
Revises: a2c6f8d3e9b7
Create Date: 2026-07-01

Expand-only migration — adds a single nullable TIMESTAMPTZ column to
workflow_run_steps. Existing rows get NULL (unknown start time); new rows
will populate it when a step transitions to in_progress. Fully reversible.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1e4a8d3f7c2"
down_revision = "a2c6f8d3e9b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_run_steps",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflow_run_steps", "started_at")
