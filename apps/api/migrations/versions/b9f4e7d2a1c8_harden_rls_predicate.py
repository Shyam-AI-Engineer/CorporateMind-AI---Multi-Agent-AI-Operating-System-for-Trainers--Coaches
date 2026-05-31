"""Harden RLS predicate: wrap current_setting in NULLIF to handle empty-string reset.

Revision ID: b9f4e7d2a1c8
Revises: a3f7e2d5b8c4
Create Date: 2026-05-31

The original predicate:
  tenant_id = current_setting('app.tenant_id', true)::uuid

…has a latent failure mode: when app.tenant_id is RESET within a long
transaction (after a prior SET LOCAL), PostgreSQL may return '' (empty
string) from current_setting() rather than NULL.  Casting '' to uuid
raises ``invalid input syntax for type uuid`` instead of silently
failing closed.

The fix wraps the call with NULLIF so both the missing-GUC (NULL) and
the reset-to-empty ('') cases are treated identically — both produce
NULL, which makes the predicate evaluate to NULL (= FALSE in RLS),
yielding zero visible rows.  Fail-closed, no error raised.

New predicate:
  tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
"""

from alembic import op

revision = "b9f4e7d2a1c8"
down_revision = "a3f7e2d5b8c4"
branch_labels = None
depends_on = None

_TENANT_TABLES: tuple[str, ...] = (
    "analytics_daily",
    "campaign_recipients",
    "campaigns",
    "companies",
    "hr_contacts",
    "leads",
    "model_runs",
    "outbound_messages",
    "proposals",
    "social_posts",
    "subscriptions",
    "trainer_profiles",
    "unsubscribe_list",
    "usage_meters",
    "whatsapp_sessions",
    "whatsapp_templates",
)

_OLD_PREDICATE = "tenant_id = current_setting('app.tenant_id', true)::uuid"
_NEW_PREDICATE = "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table}"
            f"  USING ({_NEW_PREDICATE})"
            f"  WITH CHECK ({_NEW_PREDICATE})"
        )


def downgrade() -> None:
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table}"
            f"  USING ({_OLD_PREDICATE})"
            f"  WITH CHECK ({_OLD_PREDICATE})"
        )
