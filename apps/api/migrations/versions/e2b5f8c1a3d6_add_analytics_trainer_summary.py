"""Sprint 19 — add analytics_trainer_summary table.

Revision ID: e2b5f8c1a3d6
Revises: d1f9a4e7c2b5
Create Date: 2026-06-22

New table: analytics_trainer_summary
  Time-series: one row per (tenant_id, workspace_id, rollup_date).
  Refreshed by the compute_trainer_summary Celery beat task (daily).
  Unique constraint enables ON CONFLICT DO UPDATE upserts.

Per-workspace daily deltas (same philosophy as analytics_daily):
  proposals_generated, proposals_sent, proposals_accepted — counts for rollup_date.
  closed_revenue_inr — SUM(actual_value_inr) accepted on rollup_date.
  avg_deal_size_inr  — AVG(actual_value_inr) accepted on rollup_date; NULL if none.
  pipeline_value_inr — SUM(expected_value_inr) for open proposals (snapshot).
  avg_days_to_accept — AVG(client_accepted_at - sent_at) in days for proposals
    accepted on rollup_date (Amendment 1).
  niche              — denormalized from TrainerProfile for display without JOIN.
    NULL when the profile has not been extracted yet.
  computed_at        — server timestamp of last upsert.

Win rate is NOT stored (computed at service layer from period sums to avoid
misleading per-day rates on sparse data).

RLS: enabled + FORCE ROW LEVEL SECURITY with tenant isolation predicate.

Reversible: downgrade drops the table and all dependent objects.
"""

from alembic import op
import sqlalchemy as sa


revision = "e2b5f8c1a3d6"
down_revision = "d1f9a4e7c2b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_trainer_summary",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rollup_date", sa.Date(), nullable=False),
        sa.Column("niche", sa.String(500), nullable=True),
        sa.Column("proposals_generated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposals_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposals_accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("closed_revenue_inr", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("avg_deal_size_inr", sa.Numeric(14, 2), nullable=True),
        sa.Column("pipeline_value_inr", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("avg_days_to_accept", sa.Numeric(8, 2), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "rollup_date",
            name="uq_analytics_trainer_summary_tenant_ws_date",
        ),
    )

    # Descending date index for "last N days" range queries
    op.create_index(
        "ix_analytics_trainer_summary_date",
        "analytics_trainer_summary",
        ["tenant_id", "workspace_id", sa.text("rollup_date DESC")],
    )

    op.execute(
        "ALTER TABLE analytics_trainer_summary ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE analytics_trainer_summary FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        """
        CREATE POLICY analytics_trainer_summary_tenant_isolation
          ON analytics_trainer_summary
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS analytics_trainer_summary_tenant_isolation "
        "ON analytics_trainer_summary"
    )
    op.drop_index("ix_analytics_trainer_summary_date", table_name="analytics_trainer_summary")
    op.drop_table("analytics_trainer_summary")
