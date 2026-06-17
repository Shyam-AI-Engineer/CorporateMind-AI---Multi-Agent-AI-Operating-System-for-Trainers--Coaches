"""Sprint 14 — add booking_webhook_events table (expand step, ADR-0009).

Revision ID: f1a8e5d3c2b9
Revises: e4a9b2c7f1d6
Create Date: 2026-06-17

EXPAND step only (ADR-0006).  All changes are additive and reversible.

Creates `booking_webhook_events`:
  • Idempotency anchor for inbound booking webhooks.
  • UNIQUE(tenant_id, provider, provider_event_id) prevents double-processing.
  • outcome vocabulary: processing | applied | skipped | failed (app-controlled string).
  • lead_id nullable — set to the matched lead on applied, NULL on skipped/failed.
  • raw_payload JSONB — full provider payload retained for replay/debugging.

RLS: ENABLE + FORCE ROW LEVEL SECURITY with the standard tenant_isolation policy
matching every other TenantBase table.

The NOT NULL constraint on `workspace_id` is safe at creation time — all rows
produced by the webhook handler carry a valid workspace_id from the path parameter.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "f1a8e5d3c2b9"
down_revision = "e4a9b2c7f1d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_webhook_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("invitee_email", sa.String(255), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", JSONB(), nullable=False),
        sa.Column(
            "outcome",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'processing'"),
        ),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "provider_event_id",
            name="uq_booking_webhook_events_tenant_provider_event",
        ),
    )
    op.create_index("ix_booking_webhook_events_tenant_id", "booking_webhook_events", ["tenant_id"])
    op.create_index("ix_booking_webhook_events_lead_id", "booking_webhook_events", ["lead_id"])

    # Enable RLS — matches every other TenantBase table in the schema.
    op.execute("ALTER TABLE booking_webhook_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE booking_webhook_events FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON booking_webhook_events "
        "USING (tenant_id = current_setting('app.tenant_id', TRUE)::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON booking_webhook_events")
    op.drop_index("ix_booking_webhook_events_lead_id", table_name="booking_webhook_events")
    op.drop_index("ix_booking_webhook_events_tenant_id", table_name="booking_webhook_events")
    op.drop_table("booking_webhook_events")
