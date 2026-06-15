"""Sprint 12A proposal approval — add approval_status columns (additive, reversible).

Revision ID: c2e8f5a4d9b7
Revises: b1d7c4e9f2a8
Create Date: 2026-06-14

EXPAND step only (ADR-0006 expand-then-contract).  All changes are additive and
reversible — no column is dropped, no existing column is altered.

Adds to proposals:
  • approval_status  VARCHAR(30) NOT NULL DEFAULT 'pending_approval'
      State machine: pending_approval → approved | rejected
      server_default backfills every existing draft row in place.
  • approved_by   UUID NULL — user_id of the OrgAdmin who approved
  • approved_at   TIMESTAMPTZ NULL — timestamp of approval
  • rejected_reason  TEXT NULL — reason given on rejection

Indexes:
  • ix_proposals_tenant_approval_status  (tenant_id, approval_status)
      Powers the approval_status filter on GET /proposals/ without a
      full table scan per tenant.

Check constraint:
  • ck_proposals_no_sent_without_approval
      Prevents the impossible states (sent, pending_approval) and
      (sent, rejected) at the database layer, outside the service.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PgUUID


revision = "c2e8f5a4d9b7"
down_revision = "b1d7c4e9f2a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column(
            "approval_status",
            sa.String(30),
            nullable=False,
            server_default="pending_approval",
        ),
    )
    op.add_column(
        "proposals",
        sa.Column("approved_by", PgUUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("rejected_reason", sa.Text, nullable=True),
    )

    # Backfill: proposals already sent before the approval workflow existed are
    # treated as retroactively approved.  The CHECK constraint below cannot be
    # added until this UPDATE runs, because the server_default backfills every
    # existing row — including already-sent ones — with 'pending_approval'.
    op.execute(
        "UPDATE proposals SET approval_status = 'approved' WHERE status = 'sent'"
    )

    op.create_index(
        "ix_proposals_tenant_approval_status",
        "proposals",
        ["tenant_id", "approval_status"],
    )

    op.create_check_constraint(
        "ck_proposals_no_sent_without_approval",
        "proposals",
        "NOT (status = 'sent' AND approval_status IN ('pending_approval', 'rejected'))",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_proposals_no_sent_without_approval", "proposals", type_="check"
    )
    op.drop_index("ix_proposals_tenant_approval_status", table_name="proposals")
    op.drop_column("proposals", "rejected_reason")
    op.drop_column("proposals", "approved_at")
    op.drop_column("proposals", "approved_by")
    op.drop_column("proposals", "approval_status")
