"""add entity fields to workflow_runs — Sprint 35.

Revision ID: a2c6f8d3e9b7
Revises: f6d2c4a8e1b7
Create Date: 2026-06-29

Expand-only migration — adds three nullable columns and two composite
indexes to workflow_runs. No backfill. Fully reversible.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "a2c6f8d3e9b7"
down_revision = "f6d2c4a8e1b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Nullable entity-context columns ──────────────────────────────────────
    op.add_column(
        "workflow_runs",
        sa.Column("entity_type", sa.String(64), nullable=True),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("entity_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("entity_title", sa.String(255), nullable=True),
    )

    # ── Composite indexes for entity queries ─────────────────────────────────
    op.create_index(
        "ix_workflow_runs_workspace_entity_type",
        "workflow_runs",
        ["workspace_id", "entity_type"],
    )
    op.create_index(
        "ix_workflow_runs_workspace_entity_id",
        "workflow_runs",
        ["workspace_id", "entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_workspace_entity_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workspace_entity_type", table_name="workflow_runs")
    op.drop_column("workflow_runs", "entity_title")
    op.drop_column("workflow_runs", "entity_id")
    op.drop_column("workflow_runs", "entity_type")
