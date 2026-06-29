"""Sprint 18A — add revenue attribution fields to proposals.

Revision ID: b4d8e3f1a9c7
Revises: f2c8b1e4d7a3
Create Date: 2026-06-21

EXPAND step only (ADR-0006 expand-then-contract). All columns nullable;
no existing column altered; no data dropped. Safe for zero-downtime deploy.

Adds to proposals:
  • lead_id               UUID NULL
      Direct FK to leads.  Closes the Proposal → Lead → Campaign attribution
      gap.  NULL for proposals generated before Sprint 18A.

  • expected_value_inr    NUMERIC(12,2) NULL
      Trainer's estimate of the deal value at generation time.  Drives the
      pipeline_value_inr funnel metric.

  • actual_value_inr      NUMERIC(12,2) NULL
      Confirmed deal value set when the client accepts.  Drives
      closed_revenue_inr rollup.

  • client_status         VARCHAR(30) NULL
      The client's response dimension.  Orthogonal to:
        status          (delivery lifecycle: draft → sent)
        approval_status (internal approval: pending → approved | rejected)
      Values: NULL (no response yet) | 'accepted' | 'declined'

  • client_accepted_at    TIMESTAMPTZ NULL
      Set by record_acceptance().  Revenue recognition timestamp.

  • client_declined_at    TIMESTAMPTZ NULL
      Set by record_declination().  Audit and re-engagement boundary.

Indexes:
  ix_proposals_lead_id — enables attribution join Proposal → Lead
  ix_proposals_client_accepted_at — partial; only non-NULL rows indexed for
    the revenue rollup query (client_accepted_at::date = :d)

No FK constraint on lead_id — mirrors outbound_message_id pattern
(e4a9b2c7f1d6).  Cross-module FK constraints couple migrations; the
service layer enforces the link at write time.

Reversible: downgrade is DROP COLUMN on a low-write table (< 1s at
current volume; use lock_timeout=5s in production for safety).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PgUUID


revision = "b4d8e3f1a9c7"
down_revision = "f2c8b1e4d7a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column("lead_id", PgUUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("expected_value_inr", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("actual_value_inr", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("client_status", sa.String(30), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column(
            "client_accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "proposals",
        sa.Column(
            "client_declined_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_proposals_lead_id",
        "proposals",
        ["tenant_id", "lead_id"],
    )
    # Partial index — only rows where client_accepted_at IS NOT NULL
    op.create_index(
        "ix_proposals_client_accepted_at",
        "proposals",
        ["tenant_id", "client_accepted_at"],
        postgresql_where=sa.text("client_accepted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_proposals_client_accepted_at", table_name="proposals")
    op.drop_index("ix_proposals_lead_id", table_name="proposals")
    op.drop_column("proposals", "client_declined_at")
    op.drop_column("proposals", "client_accepted_at")
    op.drop_column("proposals", "client_status")
    op.drop_column("proposals", "actual_value_inr")
    op.drop_column("proposals", "expected_value_inr")
    op.drop_column("proposals", "lead_id")
