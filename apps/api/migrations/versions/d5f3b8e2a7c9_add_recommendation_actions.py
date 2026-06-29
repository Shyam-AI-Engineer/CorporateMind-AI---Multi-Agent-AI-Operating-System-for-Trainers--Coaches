"""Sprint 25B — add recommendation_actions table.

Revision ID: d5f3b8e2a7c9
Revises: f4a7e1d9c3b6
Create Date: 2026-06-26

New table (expand-only — no destructive changes to existing tables):

  recommendation_actions
    Records trainer-initiated actions against a recommendation snapshot:
    accepted | dismissed | snoozed | completed.

    One row per (tenant_id, workspace_id, recommendation_id) — a trainer can
    only have one active action per recommendation.  ON CONFLICT DO UPDATE
    allows changing from snoozed → accepted, accepted → completed, etc.

    action_type: what the trainer did (accepted / dismissed / snoozed / completed).
    status is NOT stored — derived at service layer so "expired" (snooze past due)
    is computed in Python without needing a background job to flip rows.

    No foreign key to recommendation_snapshots is enforced at DB level to keep
    the schema append-only; the service validates snapshot existence before write.

RLS: tenant isolation policy matches the existing recommendation table pattern.

Reversible: downgrade drops the table and its policy.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "d5f3b8e2a7c9"
down_revision = "f4a7e1d9c3b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_actions",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("snooze_until", sa.Date(), nullable=True),
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
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "recommendation_id",
            name="uq_rec_actions_tenant_ws_rec",
        ),
    )
    op.create_index(
        "ix_rec_actions_workspace",
        "recommendation_actions",
        ["tenant_id", "workspace_id"],
    )
    op.create_index(
        "ix_rec_actions_type",
        "recommendation_actions",
        ["tenant_id", "workspace_id", "action_type"],
    )
    op.execute("ALTER TABLE recommendation_actions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recommendation_actions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rec_actions_tenant_isolation
          ON recommendation_actions
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS rec_actions_tenant_isolation ON recommendation_actions"
    )
    op.drop_index("ix_rec_actions_type", table_name="recommendation_actions")
    op.drop_index("ix_rec_actions_workspace", table_name="recommendation_actions")
    op.drop_table("recommendation_actions")
