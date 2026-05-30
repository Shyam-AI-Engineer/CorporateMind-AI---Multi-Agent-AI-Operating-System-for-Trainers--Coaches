"""Enable PostgreSQL Row-Level Security on all tenant-scoped tables.

Revision ID: f5a3c8d92e1b
Revises: 2085253d0300
Create Date: 2026-05-30

Every TenantBase table receives three DDL statements:

  1. ENABLE ROW LEVEL SECURITY  — activates RLS machinery on the table.
  2. FORCE ROW LEVEL SECURITY   — subjects the table owner (the 'corpmind'
                                   role that runs the application) to the same
                                   policies as every other role.  Without this,
                                   the owner silently bypasses all policies.
  3. CREATE POLICY tenant_isolation — restricts ALL DML to rows whose
                                       tenant_id matches the GUC
                                       app.tenant_id set for the current
                                       transaction by set_rls_tenant().

Policy expression (USING and WITH CHECK):
  tenant_id = current_setting('app.tenant_id', true)::uuid

  The 'true' (missing_ok) flag returns NULL instead of raising an error
  when app.tenant_id has not been set — e.g. for the public session
  (login / register / refresh) or for Alembic DDL statements.
  NULL = NULL evaluates to NULL in PostgreSQL, which RLS treats as FALSE:
  no rows are visible and no writes are permitted.  Fail-closed by design.

Tables excluded (documented reasoning):
  - orgs           — tenant root; no tenant_id column.
  - users          — auth table;  no tenant_id column.
  - workspaces     — org-level containers; no tenant_id column.
  - audit_events   — intentionally cross-tenant; the admin panel and
                     compliance tooling read across all tenants.
                     The model comment (compliance/models.py) documents
                     this architectural decision.

Downgrade reverses all three DDL steps per table.
"""

from alembic import op

revision = "f5a3c8d92e1b"
down_revision = "2085253d0300"
branch_labels = None
depends_on = None

# All 16 TenantBase tables, alphabetically ordered.
# audit_events, orgs, users, workspaces are intentionally absent.
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

# Both USING (governs SELECT / UPDATE row visibility) and WITH CHECK
# (governs INSERT / UPDATE write permission) use the same predicate so
# that a row can never be written into a tenant_id the caller does not own.
_PREDICATE = "tenant_id = current_setting('app.tenant_id', true)::uuid"


def upgrade() -> None:
    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table}"
            f"  USING ({_PREDICATE})"
            f"  WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    for table in reversed(_TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
