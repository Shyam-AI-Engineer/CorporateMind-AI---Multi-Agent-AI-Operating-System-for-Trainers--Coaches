"""Sprint 16A — expand hr_contacts with WhatsApp channel fields.

Revision ID: c4f2a8e1d9b6
Revises: a3c7f1e9d4b2
Create Date: 2026-06-18

EXPAND step only (ADR-0006 / ADR-0010).

Adds to hr_contacts:
  phone_e164              — E.164-normalised phone for WA dispatch
                            (kept separate from raw `phone` used for display)
  whatsapp_opt_in_at      — WA-specific consent timestamp (Meta policy + DPDP)
  whatsapp_opt_in_evidence— URL / screenshot reference for WA consent proof
  phone_deliverable       — set False on WA permanent delivery failure
  whatsapp_last_message_at— UTC timestamp of most recent outbound WA message;
                            used to enforce quiet hours without a full scan

All columns are nullable (or have a safe server-side default) so existing rows
require no backfill and the migration is instantly reversible.

Adds index:
  ix_hr_contacts_phone_e164 on (tenant_id, phone_e164)
  — supports the outreach send lookup (fetch phone by tenant + contact_id)
    and future segmentation queries on phone.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4f2a8e1d9b6"
down_revision = "a3c7f1e9d4b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hr_contacts",
        sa.Column("phone_e164", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "hr_contacts",
        sa.Column("whatsapp_opt_in_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hr_contacts",
        sa.Column("whatsapp_opt_in_evidence", sa.Text(), nullable=True),
    )
    op.add_column(
        "hr_contacts",
        sa.Column(
            "phone_deliverable",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )
    op.add_column(
        "hr_contacts",
        sa.Column("whatsapp_last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Index on (tenant_id, phone_e164) for send-path lookups and WA segmentation.
    op.create_index(
        "ix_hr_contacts_phone_e164",
        "hr_contacts",
        ["tenant_id", "phone_e164"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_hr_contacts_phone_e164", table_name="hr_contacts")
    op.drop_column("hr_contacts", "whatsapp_last_message_at")
    op.drop_column("hr_contacts", "phone_deliverable")
    op.drop_column("hr_contacts", "whatsapp_opt_in_evidence")
    op.drop_column("hr_contacts", "whatsapp_opt_in_at")
    op.drop_column("hr_contacts", "phone_e164")
