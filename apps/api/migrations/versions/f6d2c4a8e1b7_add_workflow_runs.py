"""add workflow runs tables — Sprint 34.

Revision ID: f6d2c4a8e1b7
Revises: e8f3a1d6c4b9
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "f6d2c4a8e1b7"
down_revision = "e8f3a1d6c4b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── workflow_runs ─────────────────────────────────────────────────────────
    op.create_table(
        "workflow_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        # nullable — run survives template deletion (SET NULL on delete)
        sa.Column("workflow_template_id", UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("started_by", UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_to", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workflow_template_id"],
            ["workflow_templates.id"],
            ondelete="SET NULL",
            name="fk_workflow_runs_template",
        ),
    )
    op.create_index("ix_workflow_runs_workspace", "workflow_runs", ["workspace_id"])
    op.create_index("ix_workflow_runs_template", "workflow_runs", ["workflow_template_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index(
        "ix_workflow_runs_workspace_status", "workflow_runs", ["workspace_id", "status"]
    )
    op.create_index(
        "ix_workflow_runs_workspace_started",
        "workflow_runs",
        ["workspace_id", "started_at"],
    )

    # ── workflow_run_steps ────────────────────────────────────────────────────
    op.create_table(
        "workflow_run_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_run_id", UUID(as_uuid=True), nullable=False),
        # nullable — template step can be deleted after run is started
        sa.Column("template_step_id", UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_role", sa.String(32), nullable=False, server_default="member"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("completed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            ondelete="CASCADE",
            name="fk_workflow_run_steps_run",
        ),
        sa.ForeignKeyConstraint(
            ["template_step_id"],
            ["workflow_steps.id"],
            ondelete="SET NULL",
            name="fk_workflow_run_steps_template_step",
        ),
    )
    op.create_index("ix_workflow_run_steps_run", "workflow_run_steps", ["workflow_run_id"])
    op.create_index("ix_workflow_run_steps_workspace", "workflow_run_steps", ["workspace_id"])
    op.create_index("ix_workflow_run_steps_status", "workflow_run_steps", ["status"])
    op.create_index(
        "ix_workflow_run_steps_run_order",
        "workflow_run_steps",
        ["workflow_run_id", "step_order"],
    )

    # ── Row-Level Security ────────────────────────────────────────────────────
    op.execute("ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY workflow_runs_tenant_isolation ON workflow_runs
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )

    op.execute("ALTER TABLE workflow_run_steps ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY workflow_run_steps_tenant_isolation ON workflow_run_steps
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS workflow_run_steps_tenant_isolation ON workflow_run_steps"
    )
    op.execute(
        "DROP POLICY IF EXISTS workflow_runs_tenant_isolation ON workflow_runs"
    )

    op.drop_index("ix_workflow_run_steps_run_order", table_name="workflow_run_steps")
    op.drop_index("ix_workflow_run_steps_status", table_name="workflow_run_steps")
    op.drop_index("ix_workflow_run_steps_workspace", table_name="workflow_run_steps")
    op.drop_index("ix_workflow_run_steps_run", table_name="workflow_run_steps")
    op.drop_table("workflow_run_steps")

    op.drop_index("ix_workflow_runs_workspace_started", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workspace_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_template", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workspace", table_name="workflow_runs")
    op.drop_table("workflow_runs")
