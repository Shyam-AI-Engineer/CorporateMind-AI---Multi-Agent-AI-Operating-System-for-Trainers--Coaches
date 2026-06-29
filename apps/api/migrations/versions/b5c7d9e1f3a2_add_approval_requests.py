"""Sprint 31 — add approval workflow tables (expand-only).

Revision ID: b5c7d9e1f3a2
Revises: f2b8d4e6c9a1
Create Date: 2026-06-28

EXPAND-ONLY migration (no destructive changes to existing tables).

Creates:
  approval_requests
    Human-driven approval workflow for tasks, recommendations, campaigns and
    proposals.  A request moves through: pending → in_review → approved |
    rejected | cancelled.  decision (approve | reject | none) is set at
    resolution time.  assigned_reviewer is a string user_id so we avoid a
    hard FK to the users table (same pattern as requested_by in operations).

  approval_timeline
    Ordered sequence of state-change events for a single approval request.
    Append-only; never updated.  Provides the audit trail shown in the
    Approval Detail page.

RLS: same tenant_isolation pattern as all business tables.
Reversible: downgrade drops policies, indexes, and both tables.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "b5c7d9e1f3a2"
down_revision = "f2b8d4e6c9a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── approval_requests ──────────────────────────────────────────────────────
    op.create_table(
        "approval_requests",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by", sa.String(256), nullable=False),
        sa.Column("assigned_reviewer", sa.String(256), nullable=True),
        sa.Column(
            "priority",
            sa.String(32),
            nullable=False,
            server_default="medium",
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "decision",
            sa.String(32),
            nullable=False,
            server_default="none",
        ),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Composite index for the main inbox query (workspace + status filter)
    op.create_index(
        "ix_approval_requests_workspace_status",
        "approval_requests",
        ["tenant_id", "workspace_id", "status"],
    )
    # Index for "my reviews" query
    op.create_index(
        "ix_approval_requests_reviewer",
        "approval_requests",
        ["tenant_id", "assigned_reviewer"],
    )
    # Index for due-date ordering / overdue filter
    op.create_index(
        "ix_approval_requests_due_date",
        "approval_requests",
        ["tenant_id", "workspace_id", "due_date"],
    )
    # Index for cursor pagination (newest-first)
    op.create_index(
        "ix_approval_requests_created_at",
        "approval_requests",
        ["tenant_id", "workspace_id", "created_at"],
    )
    op.execute("ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE approval_requests FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY approval_requests_tenant_isolation
          ON approval_requests
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )

    # ── approval_timeline ──────────────────────────────────────────────────────
    op.create_table(
        "approval_timeline",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_request_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_user_id", sa.String(256), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_timeline_request",
        "approval_timeline",
        ["tenant_id", "approval_request_id", "occurred_at"],
    )
    op.execute("ALTER TABLE approval_timeline ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE approval_timeline FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY approval_timeline_tenant_isolation
          ON approval_timeline
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    # Drop approval_timeline first (logically depends on approval_requests)
    op.execute(
        "DROP POLICY IF EXISTS approval_timeline_tenant_isolation ON approval_timeline"
    )
    op.drop_index("ix_approval_timeline_request", table_name="approval_timeline")
    op.drop_table("approval_timeline")

    # Drop approval_requests
    op.execute(
        "DROP POLICY IF EXISTS approval_requests_tenant_isolation ON approval_requests"
    )
    op.drop_index("ix_approval_requests_created_at", table_name="approval_requests")
    op.drop_index("ix_approval_requests_due_date", table_name="approval_requests")
    op.drop_index("ix_approval_requests_reviewer", table_name="approval_requests")
    op.drop_index(
        "ix_approval_requests_workspace_status", table_name="approval_requests"
    )
    op.drop_table("approval_requests")
