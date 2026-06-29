"""Sprint 18A — add revenue columns to analytics_daily.

Revision ID: c9e5a2d7f4b1
Revises: b4d8e3f1a9c7
Create Date: 2026-06-21

EXPAND step only. Both columns are NOT NULL DEFAULT 0 / 0.0 so existing
rows remain valid without a backfill — the ON CONFLICT DO UPDATE upsert
in AnalyticsDailyRepo will write correct values on the next rollup run.

Adds to analytics_daily:
  • proposals_accepted    INTEGER NOT NULL DEFAULT 0
      Count of proposals where client_accepted_at::date = rollup_date.
      Denominator for win_rate = proposals_accepted / proposals_sent.

  • closed_revenue_inr    NUMERIC(14,2) NOT NULL DEFAULT 0
      Sum of actual_value_inr for proposals accepted on rollup_date.
      Drives the daily closed-revenue trend chart.

Design note: NUMERIC(14,2) vs Float — ai_spend_inr uses Float for LLM
cost estimates.  Revenue amounts require exact decimal arithmetic; NUMERIC
prevents float rounding errors on large values.  Consistent with the
actual_value_inr column in proposals (Numeric(12,2)).

Reversible: downgrade drops both columns.
"""

from alembic import op
import sqlalchemy as sa


revision = "c9e5a2d7f4b1"
down_revision = "b4d8e3f1a9c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analytics_daily",
        sa.Column(
            "proposals_accepted",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "analytics_daily",
        sa.Column(
            "closed_revenue_inr",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("analytics_daily", "closed_revenue_inr")
    op.drop_column("analytics_daily", "proposals_accepted")
