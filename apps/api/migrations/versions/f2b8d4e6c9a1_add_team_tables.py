"""Sprint 30 — add team collaboration tables (expand-only).

Revision ID: f2b8d4e6c9a1
Revises: a4c9e2f7b1d5
Create Date: 2026-06-28

EXPAND-ONLY migration (no destructive changes to existing tables).

Creates:
  workspace_members
    Tracks workspace-level membership and roles (owner/admin/member/viewer).
    Separate from User.role (org-scoped); this is workspace-scoped.
    Invitation lifecycle: invited_at → accepted_at → removed_at (soft-delete).

  activity_feed
    Append-only audit trail of team and task actions per workspace.
    feed_metadata JSONB stores action-specific context (e.g. old/new status).
    Ordered newest-first; cursor-paginated.

  task_comments
    Thread of human comments on a business task.
    Oldest-first ordering (chronological conversation).
    author_user_id stores UUID-as-string of the authenticated commenter.

Modifies:
  business_tasks — adds assigned_user_id (nullable UUID, no FK enforced).
    Separate from legacy `assignee` (free-text). assigned_user_id links to a
    workspace_members row; assignee remains for display convenience.

RLS: same tenant_isolation pattern as all business tables.
Reversible: downgrade drops policy, indexes, new tables, and the added column.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "f2b8d4e6c9a1"
down_revision = "a4c9e2f7b1d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── workspace_members ──────────────────────────────────────────────────────
    op.create_table(
        "workspace_members",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="member"),
        sa.Column("invited_by", sa.String(256), nullable=False),
        sa.Column(
            "invited_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_members_workspace",
        "workspace_members",
        ["tenant_id", "workspace_id"],
    )
    op.create_index(
        "ix_workspace_members_user",
        "workspace_members",
        ["tenant_id", "workspace_id", "user_id"],
        unique=True,
    )
    op.execute("ALTER TABLE workspace_members ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_members FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY workspace_members_tenant_isolation
          ON workspace_members
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )

    # ── activity_feed ──────────────────────────────────────────────────────────
    op.create_table(
        "activity_feed",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", sa.String(256), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("feed_metadata", pg.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_activity_feed_workspace",
        "activity_feed",
        ["tenant_id", "workspace_id"],
    )
    op.create_index(
        "ix_activity_feed_created_at",
        "activity_feed",
        ["tenant_id", "workspace_id", "created_at"],
    )
    op.execute("ALTER TABLE activity_feed ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE activity_feed FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY activity_feed_tenant_isolation
          ON activity_feed
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )

    # ── task_comments ──────────────────────────────────────────────────────────
    op.create_table(
        "task_comments",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", sa.String(256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_comments_task",
        "task_comments",
        ["tenant_id", "workspace_id", "task_id"],
    )
    op.create_index(
        "ix_task_comments_created_at",
        "task_comments",
        ["tenant_id", "task_id", "created_at"],
    )
    op.execute("ALTER TABLE task_comments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE task_comments FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY task_comments_tenant_isolation
          ON task_comments
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )

    # ── business_tasks: add assigned_user_id ───────────────────────────────────
    op.add_column(
        "business_tasks",
        sa.Column("assigned_user_id", pg.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    # Remove added column first
    op.drop_column("business_tasks", "assigned_user_id")

    # Drop task_comments
    op.execute(
        "DROP POLICY IF EXISTS task_comments_tenant_isolation ON task_comments"
    )
    op.drop_index("ix_task_comments_created_at", table_name="task_comments")
    op.drop_index("ix_task_comments_task", table_name="task_comments")
    op.drop_table("task_comments")

    # Drop activity_feed
    op.execute(
        "DROP POLICY IF EXISTS activity_feed_tenant_isolation ON activity_feed"
    )
    op.drop_index("ix_activity_feed_created_at", table_name="activity_feed")
    op.drop_index("ix_activity_feed_workspace", table_name="activity_feed")
    op.drop_table("activity_feed")

    # Drop workspace_members
    op.execute(
        "DROP POLICY IF EXISTS workspace_members_tenant_isolation ON workspace_members"
    )
    op.drop_index("ix_workspace_members_user", table_name="workspace_members")
    op.drop_index("ix_workspace_members_workspace", table_name="workspace_members")
    op.drop_table("workspace_members")
