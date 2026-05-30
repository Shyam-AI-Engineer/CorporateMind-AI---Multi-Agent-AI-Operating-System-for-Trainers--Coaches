"""Add unique constraint on usage_meters.subscription_id.

Revision ID: a3f7e2d5b8c4
Revises: f5a3c8d92e1b
Create Date: 2026-05-30

Prerequisite for the billing upsert introduced alongside this migration:
  INSERT ... ON CONFLICT (constraint) DO UPDATE requires a named unique
  constraint, not a plain index.

Change:
  - Drop the non-unique ix_usage_meters_subscription_id index.
  - Replace it with uq_usage_meters_subscription_id (UNIQUE CONSTRAINT).

Design intent: one UsageMeter row per Subscription, always.  Any attempt to
insert a second meter for the same subscription hits the conflict target and
is redirected to an atomic UPDATE instead.
"""

from __future__ import annotations

from alembic import op

revision = "a3f7e2d5b8c4"
down_revision = "f5a3c8d92e1b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_usage_meters_subscription_id", table_name="usage_meters")
    op.create_unique_constraint(
        "uq_usage_meters_subscription_id",
        "usage_meters",
        ["subscription_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_usage_meters_subscription_id",
        "usage_meters",
        type_="unique",
    )
    op.create_index(
        "ix_usage_meters_subscription_id",
        "usage_meters",
        ["subscription_id"],
        unique=False,
    )
