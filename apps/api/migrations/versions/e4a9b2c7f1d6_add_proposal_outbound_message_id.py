"""Sprint 12B proposal delivery — add outbound_message_id to proposals.

Revision ID: e4a9b2c7f1d6
Revises: c2e8f5a4d9b7
Create Date: 2026-06-16

EXPAND step only (ADR-0006 expand-then-contract). Additive and reversible —
no existing column is altered, no data is dropped.

Adds to proposals:
  • outbound_message_id  UUID NULL
      Links the proposal to the OutboundMessage created when deliver() is
      called.  NULL  = delivery not yet initiated.
      Non-NULL = delivery attempted; see outbound_messages.status for the
      execution state (draft → queued → sent | blocked | failed).

Design notes:
  • No btree index — the lookup is always from a known proposal PK; the
    join target outbound_messages.id is already indexed by PK.
  • No FK constraint — mirrors FollowUpTask.result_outbound_message_id
    (Sprint 8B, migration b1d7c4e9f2a8).  Cross-module FK constraints
    couple migrations and create hard dependencies between independent
    table ownership.  The service layer enforces the link at write time.

Reversible: downgrade is a single DROP COLUMN on a low-write table.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PgUUID


revision = "e4a9b2c7f1d6"
down_revision = "c2e8f5a4d9b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column("outbound_message_id", PgUUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proposals", "outbound_message_id")
