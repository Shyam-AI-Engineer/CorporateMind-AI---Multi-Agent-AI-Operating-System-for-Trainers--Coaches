"""Harden RLS on 33 post-Sprint-20 tables: NULLIF predicate, WITH CHECK, FORCE RLS.

Revision ID: h9a3b2c1d4e5
Revises: g1a2b3c4d5e6
Create Date: 2026-07-11

BACKGROUND
──────────
Migration b9f4e7d2a1c8 hardened the original 16 tenant tables with the NULLIF
predicate.  Tables created after that migration (Sprints 14–59) were never
included.  A production audit identified 33 tables with one or more gaps:

  GAP 1 — Old predicate variant A (no missing_ok flag):
    current_setting('app.tenant_id')::uuid
    Raises "unrecognized configuration parameter" when app.tenant_id is not
    set, instead of failing closed.

  GAP 2 — Old predicate variant B (missing_ok but no NULLIF):
    current_setting('app.tenant_id', true)::uuid
    Returns NULL on missing GUC (safe) but raises
    "invalid input syntax for type uuid" when the GUC was previously SET and
    then RESET within a long transaction (returns '' not NULL).

  GAP 3 — Missing WITH CHECK:
    Policies with only USING govern SELECT/UPDATE row visibility but do NOT
    prevent INSERT or UPDATE of a row whose tenant_id belongs to a different
    tenant.  A cross-tenant INSERT would succeed if only USING is present.

  GAP 4 — Missing FORCE ROW LEVEL SECURITY:
    Without FORCE, the table owner role (the 'corpmind' application role)
    bypasses all policies.  20 tables were missing this guard.

TARGET PATTERN (applied to every affected table)
──────────────────────────────────────────────────
  tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid

  • missing_ok=true  → NULL when GUC is absent (safe).
  • NULLIF(…, '')    → NULL when GUC was RESET to '' within a transaction (safe).
  • Both USING + WITH CHECK use the identical predicate.
  • FORCE ROW LEVEL SECURITY subjects the table owner to the same policy.

SCOPE
─────
Tables hardened: 33
Tables already correct (not touched):
  • Original 16 from b9f4e7d2a1c8 (analytics_daily … whatsapp_templates).
  • inbox_connections, inbox_messages, crm_activities, follow_up_tasks,
    inbox_message_automation_log — each created with the full hardened pattern.
  • audit_events, orgs, users, workspaces — intentionally excluded (no RLS or
    cross-tenant by design; architectural decision documented in f5a3c8d92e1b).

REVERSIBILITY
─────────────
Downgrade restores each table's original policy (predicate variant and
USING-only shape) and removes FORCE RLS only from the 20 tables where it was
newly added.  Zero-downtime safe: DROP POLICY / CREATE POLICY on live tables
does not lock reads; the policy gap during replacement is bounded to a single
DDL statement (< 1 ms typical on an idle table).
"""

from __future__ import annotations

from alembic import op

revision = "h9a3b2c1d4e5"
down_revision = "g1a2b3c4d5e6"
branch_labels = None
depends_on = None

# ── Target pattern ─────────────────────────────────────────────────────────────

_NEW = "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"

# ── Original predicate variants ────────────────────────────────────────────────

# Used by Sprint 21–39 recommendation/business/team/workflow tables
# and Sprint 41–59 customer/training/billing tables where missing_ok was omitted.
_OLD_BARE = "tenant_id = current_setting('app.tenant_id')::uuid"

# Used by Sprint 14 (booking_webhook_events), Sprint 34 (workflow_runs/steps),
# Sprint 41 (customers), Sprint 48 (customer_renewals), Sprint 51 (customer_invoices).
_OLD_TRUE = "tenant_id = current_setting('app.tenant_id', true)::uuid"

# ── Table registry ─────────────────────────────────────────────────────────────
#
# Each entry: (table_name, policy_name, old_predicate, added_force_rls)
#
# added_force_rls=False  → table already had FORCE RLS; upgrade only replaces policy.
# added_force_rls=True   → table was missing FORCE RLS; upgrade adds it.
#
# ORDER MATTERS for downgrade (reversed): process child tables before parents
# where there is a logical dependency (e.g. workflow_run_steps before workflow_runs).

_TABLES: tuple[tuple[str, str, str, bool], ...] = (
    # ── Sprint 14 ──────────────────────────────────────────────────────────────
    # booking_webhook_events: FORCE already present; policy has old_true + no WITH CHECK.
    ("booking_webhook_events",        "tenant_isolation",                    _OLD_TRUE,  False),

    # ── Sprint 21–26 Recommendation tables ────────────────────────────────────
    # All have FORCE RLS; policies use old_bare + no WITH CHECK.
    ("recommendation_snapshots",      "rec_snapshots_tenant_isolation",      _OLD_BARE,  False),
    ("recommendation_feedback",       "rec_feedback_tenant_isolation",       _OLD_BARE,  False),
    ("recommendation_outcomes",       "rec_outcomes_tenant_isolation",       _OLD_BARE,  False),
    ("recommendation_quality_scores", "rec_quality_scores_tenant_isolation", _OLD_BARE,  False),
    ("recommendation_actions",        "rec_actions_tenant_isolation",        _OLD_BARE,  False),

    # ── Sprint 29 Business tasks ───────────────────────────────────────────────
    # Has FORCE RLS; policy uses old_bare + no WITH CHECK.
    ("business_tasks",                "business_tasks_tenant_isolation",     _OLD_BARE,  False),

    # ── Sprint 30 Team collaboration ───────────────────────────────────────────
    # All have FORCE RLS; policies use old_bare + no WITH CHECK.
    ("workspace_members",             "workspace_members_tenant_isolation",  _OLD_BARE,  False),
    ("activity_feed",                 "activity_feed_tenant_isolation",      _OLD_BARE,  False),
    ("task_comments",                 "task_comments_tenant_isolation",      _OLD_BARE,  False),

    # ── Sprint 31 Approval workflow ────────────────────────────────────────────
    # Both have FORCE RLS; policies use old_bare + no WITH CHECK.
    ("approval_requests",             "approval_requests_tenant_isolation",  _OLD_BARE,  False),
    ("approval_timeline",             "approval_timeline_tenant_isolation",  _OLD_BARE,  False),

    # ── Sprint 32 Notifications ────────────────────────────────────────────────
    # Missing FORCE RLS; policy uses old_bare + no WITH CHECK.
    ("notifications",                 "notifications_tenant_isolation",      _OLD_BARE,  True),

    # ── Sprint 33 Workflow templates ───────────────────────────────────────────
    # Both missing FORCE RLS; policies use old_bare + no WITH CHECK.
    ("workflow_templates",            "workflow_templates_tenant_isolation",  _OLD_BARE,  True),
    ("workflow_steps",                "workflow_steps_tenant_isolation",      _OLD_BARE,  True),

    # ── Sprint 34 Workflow runs ────────────────────────────────────────────────
    # Both missing FORCE RLS; policies use old_true + no WITH CHECK.
    # workflow_run_steps FK-depends on workflow_runs; list child first for downgrade safety.
    ("workflow_run_steps",            "workflow_run_steps_tenant_isolation",  _OLD_TRUE,  True),
    ("workflow_runs",                 "workflow_runs_tenant_isolation",       _OLD_TRUE,  True),

    # ── Sprint 41 Customers ────────────────────────────────────────────────────
    # Missing FORCE RLS; policy uses old_true + no WITH CHECK.
    ("customers",                     "customers_tenant_isolation",           _OLD_TRUE,  True),

    # ── Sprint 42–45 Training ──────────────────────────────────────────────────
    # All missing FORCE RLS; policies use old_bare + no WITH CHECK.
    # Ordered leaf → root for downgrade safety.
    ("training_attendance",           "training_attendance_tenant_isolation",  _OLD_BARE, True),
    ("training_sessions",             "training_sessions_tenant_isolation",    _OLD_BARE, True),
    ("training_engagements",          "training_engagements_tenant_isolation", _OLD_BARE, True),
    ("training_certificates",         "training_certificates_tenant_isolation", _OLD_BARE, True),

    # ── Sprint 46 Training feedback ────────────────────────────────────────────
    # Missing FORCE RLS; policy uses old_bare + no WITH CHECK.
    ("training_feedback",             "training_feedback_tenant_isolation",   _OLD_BARE,  True),

    # ── Sprint 47 Customer success ─────────────────────────────────────────────
    # Missing FORCE RLS; policy uses old_bare + no WITH CHECK.
    ("customer_success",              "customer_success_tenant_isolation",    _OLD_BARE,  True),

    # ── Sprint 48 Customer renewals ────────────────────────────────────────────
    # Missing FORCE RLS; policy uses old_true + no WITH CHECK.
    ("customer_renewals",             "customer_renewals_tenant_isolation",   _OLD_TRUE,  True),

    # ── Sprint 51 Customer invoices ────────────────────────────────────────────
    # Missing FORCE RLS; policy uses old_true + no WITH CHECK.
    ("customer_invoices",             "customer_invoices_tenant_isolation",   _OLD_TRUE,  True),

    # ── Sprint 52 Invoice payments ─────────────────────────────────────────────
    # Missing FORCE RLS; policy uses old_bare + no WITH CHECK.
    ("invoice_payments",              "invoice_payments_tenant_isolation",    _OLD_BARE,  True),

    # ── Sprint 53 Audit logs ───────────────────────────────────────────────────
    # Missing FORCE RLS; policy uses old_bare + no WITH CHECK.
    ("audit_logs",                    "audit_logs_tenant_isolation",          _OLD_BARE,  True),

    # ── Sprint 54 Organization settings ───────────────────────────────────────
    # Missing FORCE RLS; policy uses old_bare + no WITH CHECK.
    ("organization_settings",         "organization_settings_tenant_isolation", _OLD_BARE, True),

    # ── Sprint 55 API keys & webhooks ──────────────────────────────────────────
    # Both missing FORCE RLS; policies use old_bare + no WITH CHECK.
    ("api_keys",                      "api_keys_tenant_isolation",            _OLD_BARE,  True),
    ("webhooks",                      "webhooks_tenant_isolation",            _OLD_BARE,  True),

    # ── Sprint 56 Report exports ───────────────────────────────────────────────
    # Missing FORCE RLS; policy uses old_bare + no WITH CHECK.
    ("report_exports",                "report_exports_tenant_isolation",      _OLD_BARE,  True),

    # ── Sprint 59 Bulk operations ──────────────────────────────────────────────
    # Has FORCE RLS; policy uses old_bare + no WITH CHECK.
    ("bulk_operations",               "bulk_operations_tenant_isolation",     _OLD_BARE,  False),
)


def upgrade() -> None:
    for table, policy, _, added_force in _TABLES:
        if added_force:
            # Table was missing FORCE ROW LEVEL SECURITY — add it now.
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # Replace the old USING-only policy with the hardened USING + WITH CHECK policy.
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(
            f"CREATE POLICY {policy} ON {table}"
            f"  USING ({_NEW})"
            f"  WITH CHECK ({_NEW})"
        )


def downgrade() -> None:
    for table, policy, old_pred, added_force in reversed(_TABLES):
        # Restore the original USING-only policy with the original predicate.
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(
            f"CREATE POLICY {policy} ON {table}"
            f"  USING ({old_pred})"
        )
        if added_force:
            # Remove FORCE ROW LEVEL SECURITY only from tables where we added it.
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
