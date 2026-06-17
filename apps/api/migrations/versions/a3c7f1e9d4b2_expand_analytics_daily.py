"""Sprint 15 — expand analytics_daily with funnel columns + idempotency constraint.

Revision ID: a3c7f1e9d4b2
Revises: d4e2f7a8b3c1
Create Date: 2026-06-17

EXPAND step only (ADR-0006).  All new columns are INTEGER NOT NULL DEFAULT 0
so existing rows (if any) get a safe default and the schema stays consistent
with future upserts.

Adds to analytics_daily:
  proposals_generated  — count of proposals created that rollup day
  proposals_approved   — count of proposals that reached approval_status='approved'
  proposals_sent       — count of proposals where status='sent'
  leads_created        — count of new CRM leads created that day
  leads_booked         — count of leads that reached stage='booked' that day

Also adds:
  UNIQUE (tenant_id, rollup_date, channel)
    — Required for the ON CONFLICT DO UPDATE upsert in compute_daily_rollup.
      Without this, re-running the rollup creates duplicate rows instead of
      correcting them.  NULL channel = cross-channel aggregate row; Postgres
      treats (tenant_id, rollup_date, NULL) as unique per-tenant per-day.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3c7f1e9d4b2"
down_revision = "d4e2f7a8b3c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analytics_daily",
        sa.Column("proposals_generated", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analytics_daily",
        sa.Column("proposals_approved", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analytics_daily",
        sa.Column("proposals_sent", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analytics_daily",
        sa.Column("leads_created", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analytics_daily",
        sa.Column("leads_booked", sa.Integer(), nullable=False, server_default="0"),
    )
    # NULLS NOT DISTINCT: two rows with channel=NULL are treated as duplicates
    # (standard Postgres UNIQUE treats NULL as distinct — ON CONFLICT would not
    # fire for null-channel rows without this modifier, creating duplicates).
    # Requires Postgres 15+; testcontainers uses postgres:16-alpine.
    op.execute(
        "ALTER TABLE analytics_daily ADD CONSTRAINT uq_analytics_daily_tenant_date_channel"
        " UNIQUE NULLS NOT DISTINCT (tenant_id, rollup_date, channel)"
    )


def downgrade() -> None:
    op.drop_constraint("uq_analytics_daily_tenant_date_channel", "analytics_daily", type_="unique")
    op.drop_column("analytics_daily", "leads_booked")
    op.drop_column("analytics_daily", "leads_created")
    op.drop_column("analytics_daily", "proposals_sent")
    op.drop_column("analytics_daily", "proposals_approved")
    op.drop_column("analytics_daily", "proposals_generated")
