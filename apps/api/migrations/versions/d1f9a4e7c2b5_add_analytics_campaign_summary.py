"""Sprint 19 — add analytics_campaign_summary table.

Revision ID: d1f9a4e7c2b5
Revises: c9e5a2d7f4b1
Create Date: 2026-06-22

New table: analytics_campaign_summary
  One row per campaign (snapshot, not time-series).
  Refreshed by the compute_campaign_summary Celery beat task (daily).
  Unique constraint (tenant_id, campaign_id) enables ON CONFLICT DO UPDATE
  upserts so re-running the rollup is idempotent.

Columns:
  campaign_id, workspace_id, campaign_name, channel, campaign_status
    — denormalized from campaigns to avoid JOINs on the read path.
  recipients_count   — COUNT(DISTINCT contact_id) in campaign_recipients.
  messages_sent      — outbound_messages with status in (sent|delivered|opened|replied).
  messages_delivered — campaign_recipients with delivered_at IS NOT NULL.
  replies_received   — inbox_messages with reply_intent='interested' matched to campaign.
  leads_created      — leads whose contact_id appears in campaign_recipients.
  proposals_generated, proposals_sent, proposals_accepted — from proposals linked
    via Lead→CampaignRecipient (all-touch attribution).
  closed_revenue_inr — SUM(actual_value_inr) for accepted proposals.
  avg_deal_size_inr  — AVG(actual_value_inr) for accepted proposals; NULL if none.
  win_rate           — proposals_accepted / proposals_sent; 0 if no sent proposals.
  avg_days_to_accept — AVG(client_accepted_at - sent_at) in days (Amendment 1).
  last_refreshed_at  — server timestamp of last upsert.

RLS: enabled + FORCE ROW LEVEL SECURITY with tenant isolation predicate.

Reversible: downgrade drops the table and all dependent objects.
"""

from alembic import op
import sqlalchemy as sa


revision = "d1f9a4e7c2b5"
down_revision = "c9e5a2d7f4b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_campaign_summary",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_name", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("campaign_status", sa.String(30), nullable=False),
        sa.Column("recipients_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_delivered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replies_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("leads_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposals_generated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposals_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposals_accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("closed_revenue_inr", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("avg_deal_size_inr", sa.Numeric(14, 2), nullable=True),
        sa.Column("win_rate", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("avg_days_to_accept", sa.Numeric(8, 2), nullable=True),
        sa.Column(
            "last_refreshed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "campaign_id",
            name="uq_analytics_campaign_summary_tenant_campaign",
        ),
    )

    # Workspace index for workspace-scoped list queries
    op.create_index(
        "ix_analytics_campaign_summary_workspace",
        "analytics_campaign_summary",
        ["tenant_id", "workspace_id"],
    )

    op.execute(
        "ALTER TABLE analytics_campaign_summary ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE analytics_campaign_summary FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        """
        CREATE POLICY analytics_campaign_summary_tenant_isolation
          ON analytics_campaign_summary
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS analytics_campaign_summary_tenant_isolation "
        "ON analytics_campaign_summary"
    )
    op.drop_index("ix_analytics_campaign_summary_workspace", table_name="analytics_campaign_summary")
    op.drop_table("analytics_campaign_summary")
