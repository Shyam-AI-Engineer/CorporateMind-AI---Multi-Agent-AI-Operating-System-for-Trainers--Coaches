"""Add workflow_templates and workflow_steps tables — Sprint 33.

Revision ID: e8f3a1d6c4b9
Revises: d7e2a5f8c3b1
Create Date: 2026-06-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e8f3a1d6c4b9"
down_revision = "d7e2a5f8c3b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── workflow_templates ────────────────────────────────────────────────────
    op.create_table(
        "workflow_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_workflow_templates_workspace",
        "workflow_templates",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workflow_templates_category",
        "workflow_templates",
        ["category"],
    )
    op.create_index(
        "ix_workflow_templates_workspace_active",
        "workflow_templates",
        ["workspace_id", "is_active"],
    )

    op.execute(
        """
        ALTER TABLE workflow_templates ENABLE ROW LEVEL SECURITY;
        CREATE POLICY workflow_templates_tenant_isolation ON workflow_templates
            USING (tenant_id = current_setting('app.tenant_id')::uuid);
        """
    )

    # ── workflow_steps ────────────────────────────────────────────────────────
    op.create_table(
        "workflow_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "workflow_template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_role", sa.String(32), nullable=False, server_default="member"),
        sa.Column("estimated_hours", sa.Numeric(precision=6, scale=2), nullable=False, server_default="0"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # step_order is DEFERRABLE INITIALLY DEFERRED so bulk-reorder doesn't clash mid-transaction
    op.execute(
        """
        ALTER TABLE workflow_steps
            ADD CONSTRAINT uq_workflow_step_order
            UNIQUE (workflow_template_id, step_order)
            DEFERRABLE INITIALLY DEFERRED;
        """
    )

    op.create_index(
        "ix_workflow_steps_template",
        "workflow_steps",
        ["workflow_template_id"],
    )
    op.create_index(
        "ix_workflow_steps_template_order",
        "workflow_steps",
        ["workflow_template_id", "step_order"],
    )
    op.create_index(
        "ix_workflow_steps_workspace",
        "workflow_steps",
        ["workspace_id"],
    )

    op.execute(
        """
        ALTER TABLE workflow_steps ENABLE ROW LEVEL SECURITY;
        CREATE POLICY workflow_steps_tenant_isolation ON workflow_steps
            USING (tenant_id = current_setting('app.tenant_id')::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS workflow_steps_tenant_isolation ON workflow_steps;")
    op.drop_index("ix_workflow_steps_workspace", table_name="workflow_steps")
    op.drop_index("ix_workflow_steps_template_order", table_name="workflow_steps")
    op.drop_index("ix_workflow_steps_template", table_name="workflow_steps")
    op.execute("ALTER TABLE workflow_steps DROP CONSTRAINT IF EXISTS uq_workflow_step_order;")
    op.drop_table("workflow_steps")

    op.execute("DROP POLICY IF EXISTS workflow_templates_tenant_isolation ON workflow_templates;")
    op.drop_index("ix_workflow_templates_workspace_active", table_name="workflow_templates")
    op.drop_index("ix_workflow_templates_category", table_name="workflow_templates")
    op.drop_index("ix_workflow_templates_workspace", table_name="workflow_templates")
    op.drop_table("workflow_templates")
