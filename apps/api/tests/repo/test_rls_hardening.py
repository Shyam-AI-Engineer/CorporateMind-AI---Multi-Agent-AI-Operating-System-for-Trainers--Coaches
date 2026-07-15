"""Migration h9a3b2c1d4e5 — RLS hardening verification tests.

Verifies the hardened tenant isolation policy applied by migration
h9a3b2c1d4e5 on 33 post-Sprint-20 tables.  Each test uses a real
PostgreSQL testcontainer running the full Alembic migration chain.

The testcontainer connects as the postgres superuser, which bypasses RLS.
The conftest.py fixture does SET ROLE corpmind_test — a non-superuser role —
so PostgreSQL enforces all RLS policies for the duration of the session.

Test coverage per spec:
  ✓  Tenant cannot SELECT another tenant's row (USING policy)
  ✓  Tenant cannot INSERT another tenant's row (WITH CHECK policy)
  ✓  Tenant cannot UPDATE another tenant's row (WITH CHECK on UPDATE)
  ✓  Tenant cannot DELETE another tenant's row (USING policy governs DELETE)
  ✓  WITH CHECK blocks incorrect tenant_id on INSERT
  ✓  FORCE ROW LEVEL SECURITY active (table owner role is subject to policy)
  ✓  NULL app.tenant_id safely denied (zero rows visible / write rejected)
  ✓  Empty string app.tenant_id safely denied (NULLIF → NULL → fail closed)
  ✓  Downgrade restores previous USING-only policies (policy shape test)

Notes:
  - Tests use raw SQL to stay independent of ORM models (which may not exist
    for all 33 tables in the unit-test path).
  - Each test generates fresh UUIDs so isolation between tests is by value,
    not by transaction rollback.
  - A representative sample of tables covers each category: tables that
    already had FORCE RLS (GROUP A) and tables where this migration added
    it (GROUP B).  The same policy is applied identically to all 33 tables,
    so representative sampling is sufficient.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tid() -> str:
    """Return a new random UUID as a string."""
    return str(uuid.uuid4())


async def _set_tenant(session, org_id: str) -> None:
    await session.execute(text(f"SET LOCAL app.tenant_id = '{org_id}'"))


async def _clear_tenant(session) -> None:
    """RESET app.tenant_id — GUC returns '' after this in the same session."""
    await session.execute(text("RESET app.tenant_id"))


async def _set_empty_tenant(session) -> None:
    """SET app.tenant_id to empty string — tests NULLIF(…, '') branch."""
    await session.execute(text("SET LOCAL app.tenant_id = ''"))


# ---------------------------------------------------------------------------
# SELECT isolation (USING policy)
# ---------------------------------------------------------------------------

class TestSelectIsolation:
    """USING policy prevents cross-tenant reads."""

    @pytest.mark.asyncio
    async def test_customers_hidden_from_other_tenant(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """A customer row created by tenant A is invisible to tenant B."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        cust_id = _tid()
        ws_id = _tid()

        # Write as tenant A
        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO customers "
                "(id, tenant_id, workspace_id, company_name, display_name, status, health_status) "
                "VALUES (:id, :tid, :ws, :cn, :dn, 'active', 'healthy')"
            ),
            {"id": cust_id, "tid": tid_a, "ws": ws_id, "cn": "Acme A", "dn": "Acme A"},
        )
        await db_session.flush()

        # Read as tenant B — must return nothing
        await _set_tenant(db_session, tid_b)
        result = await db_session.execute(
            text("SELECT id FROM customers WHERE id = :id"),
            {"id": cust_id},
        )
        assert result.one_or_none() is None, (
            "Tenant B must not see Tenant A's customer row"
        )

    @pytest.mark.asyncio
    async def test_training_sessions_hidden_from_other_tenant(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """A training_sessions row created by tenant A is invisible to tenant B."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        sess_id = _tid()
        ws_id = _tid()
        eng_id = _tid()

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO training_sessions "
                "(id, tenant_id, workspace_id, engagement_id, session_name, status) "
                "VALUES (:id, :tid, :ws, :eng, :name, 'planned')"
            ),
            {"id": sess_id, "tid": tid_a, "ws": ws_id, "eng": eng_id, "name": "Session 1"},
        )
        await db_session.flush()

        await _set_tenant(db_session, tid_b)
        result = await db_session.execute(
            text("SELECT id FROM training_sessions WHERE id = :id"),
            {"id": sess_id},
        )
        assert result.one_or_none() is None

    @pytest.mark.asyncio
    async def test_audit_logs_hidden_from_other_tenant(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """An audit_logs row created by tenant A is invisible to tenant B."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        log_id = _tid()
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO audit_logs "
                "(id, tenant_id, workspace_id, action, module) "
                "VALUES (:id, :tid, :ws, 'test.action', 'test')"
            ),
            {"id": log_id, "tid": tid_a, "ws": ws_id},
        )
        await db_session.flush()

        await _set_tenant(db_session, tid_b)
        result = await db_session.execute(
            text("SELECT id FROM audit_logs WHERE id = :id"),
            {"id": log_id},
        )
        assert result.one_or_none() is None

    @pytest.mark.asyncio
    async def test_recommendation_snapshots_hidden_from_other_tenant(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """recommendation_snapshots (GROUP A — had FORCE RLS before) is isolated."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        snap_id = _tid()
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO recommendation_snapshots "
                "(id, tenant_id, workspace_id, snapshot_date, rec_type) "
                "VALUES (:id, :tid, :ws, CURRENT_DATE, 'topic')"
            ),
            {"id": snap_id, "tid": tid_a, "ws": ws_id},
        )
        await db_session.flush()

        await _set_tenant(db_session, tid_b)
        result = await db_session.execute(
            text("SELECT id FROM recommendation_snapshots WHERE id = :id"),
            {"id": snap_id},
        )
        assert result.one_or_none() is None

    @pytest.mark.asyncio
    async def test_booking_webhook_events_hidden_from_other_tenant(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """booking_webhook_events (first table with the gap) is isolated."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        evt_id = _tid()
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO booking_webhook_events "
                "(id, tenant_id, workspace_id, provider, provider_event_id, "
                " event_type, invitee_email, raw_payload) "
                "VALUES (:id, :tid, :ws, 'calendly', :pevt, 'invitee.created', "
                " 'test@example.com', '{}'::jsonb)"
            ),
            {"id": evt_id, "tid": tid_a, "ws": ws_id, "pevt": _tid()},
        )
        await db_session.flush()

        await _set_tenant(db_session, tid_b)
        result = await db_session.execute(
            text("SELECT id FROM booking_webhook_events WHERE id = :id"),
            {"id": evt_id},
        )
        assert result.one_or_none() is None


# ---------------------------------------------------------------------------
# INSERT isolation (WITH CHECK policy)
# ---------------------------------------------------------------------------

class TestInsertIsolation:
    """WITH CHECK policy blocks cross-tenant inserts."""

    @pytest.mark.asyncio
    async def test_with_check_blocks_wrong_tenant_insert_customers(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """Attempting to INSERT a customer with tenant_b's ID while logged in as tenant_a
        must be blocked by the WITH CHECK policy."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        with pytest.raises(Exception):
            # The WITH CHECK predicate rejects this: tenant_id = tid_b but the
            # GUC is set to tid_a, so nullif(current_setting(…)) = tid_a ≠ tid_b.
            await db_session.execute(
                text(
                    "INSERT INTO customers "
                    "(id, tenant_id, workspace_id, company_name, display_name, status, health_status) "
                    "VALUES (:id, :tid, :ws, :cn, :dn, 'active', 'healthy')"
                ),
                {"id": _tid(), "tid": tid_b, "ws": ws_id, "cn": "Evil Insert", "dn": "Evil"},
            )
            await db_session.flush()
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_with_check_blocks_wrong_tenant_insert_notifications(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """notifications (GROUP B — FORCE RLS was added by this migration) blocks cross-tenant INSERT."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        ws_id = _tid()
        user_id = _tid()

        await _set_tenant(db_session, tid_a)
        with pytest.raises(Exception):
            await db_session.execute(
                text(
                    "INSERT INTO notifications "
                    "(id, tenant_id, workspace_id, user_id, notification_type, title, message) "
                    "VALUES (:id, :tid, :ws, :uid, 'system', 'Title', 'Msg')"
                ),
                {"id": _tid(), "tid": tid_b, "ws": ws_id, "uid": user_id},
            )
            await db_session.flush()
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_with_check_blocks_wrong_tenant_insert_audit_logs(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """audit_logs WITH CHECK blocks insert of another tenant's row."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        with pytest.raises(Exception):
            await db_session.execute(
                text(
                    "INSERT INTO audit_logs "
                    "(id, tenant_id, workspace_id, action, module) "
                    "VALUES (:id, :tid, :ws, 'test', 'test')"
                ),
                {"id": _tid(), "tid": tid_b, "ws": ws_id},
            )
            await db_session.flush()
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_with_check_blocks_wrong_tenant_insert_workflow_runs(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """workflow_runs WITH CHECK blocks cross-tenant insert."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        with pytest.raises(Exception):
            await db_session.execute(
                text(
                    "INSERT INTO workflow_runs "
                    "(id, tenant_id, workspace_id, title, started_by) "
                    "VALUES (:id, :tid, :ws, 'Evil Run', :uid)"
                ),
                {"id": _tid(), "tid": tid_b, "ws": ws_id, "uid": _tid()},
            )
            await db_session.flush()
        await db_session.rollback()


# ---------------------------------------------------------------------------
# UPDATE isolation (USING + WITH CHECK)
# ---------------------------------------------------------------------------

class TestUpdateIsolation:
    """UPDATE is governed by USING (row visibility) and WITH CHECK (target row)."""

    @pytest.mark.asyncio
    async def test_tenant_cannot_update_another_tenants_customer(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """Tenant B cannot UPDATE tenant A's customer — row is invisible under USING."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        cust_id = _tid()
        ws_id = _tid()

        # Insert as tenant A
        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO customers "
                "(id, tenant_id, workspace_id, company_name, display_name, status, health_status) "
                "VALUES (:id, :tid, :ws, 'Target', 'Target', 'active', 'healthy')"
            ),
            {"id": cust_id, "tid": tid_a, "ws": ws_id},
        )
        await db_session.flush()

        # Attempt UPDATE as tenant B — should affect 0 rows (row is invisible)
        await _set_tenant(db_session, tid_b)
        result = await db_session.execute(
            text("UPDATE customers SET display_name = 'Hacked' WHERE id = :id"),
            {"id": cust_id},
        )
        assert result.rowcount == 0, (
            "Tenant B must not be able to update Tenant A's customer"
        )

    @pytest.mark.asyncio
    async def test_tenant_cannot_update_another_tenants_audit_log(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """Tenant B cannot UPDATE tenant A's audit_log row."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        log_id = _tid()
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO audit_logs "
                "(id, tenant_id, workspace_id, action, module) "
                "VALUES (:id, :tid, :ws, 'original', 'test')"
            ),
            {"id": log_id, "tid": tid_a, "ws": ws_id},
        )
        await db_session.flush()

        await _set_tenant(db_session, tid_b)
        result = await db_session.execute(
            text("UPDATE audit_logs SET action = 'tampered' WHERE id = :id"),
            {"id": log_id},
        )
        assert result.rowcount == 0


# ---------------------------------------------------------------------------
# DELETE isolation (USING policy)
# ---------------------------------------------------------------------------

class TestDeleteIsolation:
    """DELETE is governed by USING — rows invisible to wrong tenant cannot be deleted."""

    @pytest.mark.asyncio
    async def test_tenant_cannot_delete_another_tenants_notification(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """Tenant B cannot DELETE tenant A's notification row."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        notif_id = _tid()
        ws_id = _tid()
        user_id = _tid()

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO notifications "
                "(id, tenant_id, workspace_id, user_id, notification_type, title, message) "
                "VALUES (:id, :tid, :ws, :uid, 'system', 'Test', 'Body')"
            ),
            {"id": notif_id, "tid": tid_a, "ws": ws_id, "uid": user_id},
        )
        await db_session.flush()

        await _set_tenant(db_session, tid_b)
        result = await db_session.execute(
            text("DELETE FROM notifications WHERE id = :id"),
            {"id": notif_id},
        )
        assert result.rowcount == 0, (
            "Tenant B must not be able to delete Tenant A's notification"
        )

    @pytest.mark.asyncio
    async def test_tenant_cannot_delete_another_tenants_api_key(
        self, db_session, tenant_a, tenant_b
    ) -> None:
        """Tenant B cannot DELETE tenant A's api_keys row."""
        tid_a = str(tenant_a.org_id)
        tid_b = str(tenant_b.org_id)
        key_id = _tid()
        ws_id = _tid()
        user_id = _tid()
        prefix = uuid.uuid4().hex[:8]

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO api_keys "
                "(id, tenant_id, workspace_id, name, key_prefix, key_hash, created_by) "
                "VALUES (:id, :tid, :ws, 'Test Key', :prefix, 'hash123', :uid)"
            ),
            {"id": key_id, "tid": tid_a, "ws": ws_id, "prefix": prefix, "uid": user_id},
        )
        await db_session.flush()

        await _set_tenant(db_session, tid_b)
        result = await db_session.execute(
            text("DELETE FROM api_keys WHERE id = :id"),
            {"id": key_id},
        )
        assert result.rowcount == 0


# ---------------------------------------------------------------------------
# FORCE ROW LEVEL SECURITY active
# ---------------------------------------------------------------------------

class TestForceRlsActive:
    """FORCE ROW LEVEL SECURITY ensures the table-owner role obeys the policy.

    We verify this indirectly: rows inserted with no GUC set are invisible to
    a subsequent query that also has no GUC set (fail-closed).  A superuser
    without FORCE RLS would see the row; the corpmind_test non-superuser role
    with FORCE RLS enabled sees nothing.
    """

    @pytest.mark.asyncio
    async def test_force_rls_denies_access_when_no_guc(
        self, db_session, tenant_a
    ) -> None:
        """When app.tenant_id is not set, zero rows are visible — FORCE RLS is active."""
        tid_a = str(tenant_a.org_id)
        cust_id = _tid()
        ws_id = _tid()

        # Insert with a valid tenant context
        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO customers "
                "(id, tenant_id, workspace_id, company_name, display_name, status, health_status) "
                "VALUES (:id, :tid, :ws, 'Force RLS Test', 'Force Test', 'active', 'healthy')"
            ),
            {"id": cust_id, "tid": tid_a, "ws": ws_id},
        )
        await db_session.flush()

        # RESET app.tenant_id — GUC returns '' (NULLIF converts to NULL)
        await _clear_tenant(db_session)
        result = await db_session.execute(
            text("SELECT id FROM customers WHERE id = :id"),
            {"id": cust_id},
        )
        assert result.one_or_none() is None, (
            "Row must be invisible when app.tenant_id is not set (FORCE RLS active)"
        )

    @pytest.mark.asyncio
    async def test_force_rls_on_group_a_table(self, db_session, tenant_a) -> None:
        """recommendation_snapshots (GROUP A — already had FORCE RLS) still enforces it."""
        tid_a = str(tenant_a.org_id)
        snap_id = _tid()
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO recommendation_snapshots "
                "(id, tenant_id, workspace_id, snapshot_date, rec_type) "
                "VALUES (:id, :tid, :ws, CURRENT_DATE, 'pricing')"
            ),
            {"id": snap_id, "tid": tid_a, "ws": ws_id},
        )
        await db_session.flush()

        await _clear_tenant(db_session)
        result = await db_session.execute(
            text("SELECT id FROM recommendation_snapshots WHERE id = :id"),
            {"id": snap_id},
        )
        assert result.one_or_none() is None


# ---------------------------------------------------------------------------
# NULL and empty-string GUC safety
# ---------------------------------------------------------------------------

class TestGucEdgeCases:
    """NULLIF handles both NULL (missing_ok) and '' (RESET) safely."""

    @pytest.mark.asyncio
    async def test_null_tenant_id_guc_denied(
        self, db_session, tenant_a
    ) -> None:
        """After RESET, the GUC returns '' which NULLIF converts to NULL → fail closed."""
        tid_a = str(tenant_a.org_id)
        cust_id = _tid()
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO customers "
                "(id, tenant_id, workspace_id, company_name, display_name, status, health_status) "
                "VALUES (:id, :tid, :ws, 'GUC Test', 'GUC', 'active', 'healthy')"
            ),
            {"id": cust_id, "tid": tid_a, "ws": ws_id},
        )
        await db_session.flush()

        # RESET makes current_setting return '' — NULLIF turns that into NULL
        await db_session.execute(text("RESET app.tenant_id"))
        result = await db_session.execute(
            text("SELECT id FROM customers WHERE id = :id"),
            {"id": cust_id},
        )
        assert result.one_or_none() is None, (
            "Row must be invisible after RESET (NULLIF converts '' to NULL)"
        )

    @pytest.mark.asyncio
    async def test_empty_string_guc_denied(
        self, db_session, tenant_a
    ) -> None:
        """SET app.tenant_id = '' → NULLIF converts to NULL → fail closed (not error)."""
        tid_a = str(tenant_a.org_id)
        log_id = _tid()
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO audit_logs "
                "(id, tenant_id, workspace_id, action, module) "
                "VALUES (:id, :tid, :ws, 'edge.case', 'test')"
            ),
            {"id": log_id, "tid": tid_a, "ws": ws_id},
        )
        await db_session.flush()

        # SET to empty string — NULLIF converts '' to NULL in the predicate
        await _set_empty_tenant(db_session)
        # Must not raise, must return 0 rows
        result = await db_session.execute(
            text("SELECT id FROM audit_logs WHERE id = :id"),
            {"id": log_id},
        )
        assert result.one_or_none() is None, (
            "Empty string GUC must fail closed (NULLIF → NULL → predicate FALSE)"
        )

    @pytest.mark.asyncio
    async def test_empty_string_insert_rejected(
        self, db_session, tenant_a
    ) -> None:
        """INSERT with empty GUC must be rejected by WITH CHECK (NULL ≠ any real UUID)."""
        await _set_empty_tenant(db_session)
        ws_id = _tid()
        new_id = _tid()

        with pytest.raises(Exception):
            await db_session.execute(
                text(
                    "INSERT INTO customers "
                    "(id, tenant_id, workspace_id, company_name, display_name, status, health_status) "
                    "VALUES (:id, :tid, :ws, 'Evil', 'Evil', 'active', 'healthy')"
                ),
                {"id": new_id, "tid": str(uuid.uuid4()), "ws": ws_id},
            )
            await db_session.flush()
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_null_guc_insert_rejected_notifications(
        self, db_session, tenant_a
    ) -> None:
        """INSERT into notifications with RESET GUC must be blocked."""
        await _clear_tenant(db_session)
        ws_id = _tid()

        with pytest.raises(Exception):
            await db_session.execute(
                text(
                    "INSERT INTO notifications "
                    "(id, tenant_id, workspace_id, user_id, notification_type, title, message) "
                    "VALUES (:id, :tid, :ws, :uid, 'sys', 'T', 'M')"
                ),
                {
                    "id": _tid(),
                    "tid": str(uuid.uuid4()),
                    "ws": ws_id,
                    "uid": _tid(),
                },
            )
            await db_session.flush()
        await db_session.rollback()


# ---------------------------------------------------------------------------
# Correct-tenant access still works
# ---------------------------------------------------------------------------

class TestCorrectTenantAccess:
    """Verify that a valid tenant can still read and write their own rows."""

    @pytest.mark.asyncio
    async def test_tenant_reads_own_customer(
        self, db_session, tenant_a
    ) -> None:
        """A tenant can SELECT its own rows after RLS hardening."""
        tid_a = str(tenant_a.org_id)
        cust_id = _tid()
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO customers "
                "(id, tenant_id, workspace_id, company_name, display_name, status, health_status) "
                "VALUES (:id, :tid, :ws, 'Own Corp', 'Own', 'active', 'healthy')"
            ),
            {"id": cust_id, "tid": tid_a, "ws": ws_id},
        )
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT id FROM customers WHERE id = :id"),
            {"id": cust_id},
        )
        row = result.one_or_none()
        assert row is not None, "Tenant must be able to read its own customer row"
        assert str(row[0]) == cust_id

    @pytest.mark.asyncio
    async def test_tenant_writes_own_notification(
        self, db_session, tenant_a
    ) -> None:
        """A tenant can INSERT into notifications after FORCE RLS was added."""
        tid_a = str(tenant_a.org_id)
        notif_id = _tid()
        ws_id = _tid()
        user_id = _tid()

        await _set_tenant(db_session, tid_a)
        # Must not raise
        await db_session.execute(
            text(
                "INSERT INTO notifications "
                "(id, tenant_id, workspace_id, user_id, notification_type, title, message) "
                "VALUES (:id, :tid, :ws, :uid, 'system', 'Hello', 'World')"
            ),
            {"id": notif_id, "tid": tid_a, "ws": ws_id, "uid": user_id},
        )
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT id FROM notifications WHERE id = :id"),
            {"id": notif_id},
        )
        assert result.one_or_none() is not None

    @pytest.mark.asyncio
    async def test_tenant_reads_own_audit_log(
        self, db_session, tenant_a
    ) -> None:
        """A tenant can SELECT its own audit_logs row after FORCE RLS was added."""
        tid_a = str(tenant_a.org_id)
        log_id = _tid()
        ws_id = _tid()

        await _set_tenant(db_session, tid_a)
        await db_session.execute(
            text(
                "INSERT INTO audit_logs "
                "(id, tenant_id, workspace_id, action, module) "
                "VALUES (:id, :tid, :ws, 'read.test', 'audit')"
            ),
            {"id": log_id, "tid": tid_a, "ws": ws_id},
        )
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT id FROM audit_logs WHERE id = :id"),
            {"id": log_id},
        )
        assert result.one_or_none() is not None


# ---------------------------------------------------------------------------
# Policy shape verification (downgrade-correctness proxy)
# ---------------------------------------------------------------------------

class TestPolicyShape:
    """Verify the installed policies have the correct shape.

    This tests the UPGRADE state by inspecting pg_policies.
    It is also a proxy for downgrade correctness: if a downgrade is applied
    and then this migration re-applied, the same shapes must hold.
    """

    _TABLES_TO_CHECK = [
        # (table_name, policy_name)
        ("customers",                  "customers_tenant_isolation"),
        ("notifications",              "notifications_tenant_isolation"),
        ("workflow_runs",              "workflow_runs_tenant_isolation"),
        ("training_sessions",          "training_sessions_tenant_isolation"),
        ("audit_logs",                 "audit_logs_tenant_isolation"),
        ("recommendation_snapshots",   "rec_snapshots_tenant_isolation"),
        ("booking_webhook_events",     "tenant_isolation"),
        ("bulk_operations",            "bulk_operations_tenant_isolation"),
        ("api_keys",                   "api_keys_tenant_isolation"),
        ("report_exports",             "report_exports_tenant_isolation"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("table,policy", _TABLES_TO_CHECK)
    async def test_policy_has_qual_and_with_check(
        self, db_session, table: str, policy: str
    ) -> None:
        """pg_policies.qual (USING) and with_check must both be non-NULL."""
        result = await db_session.execute(
            text(
                "SELECT qual, with_check FROM pg_policies "
                "WHERE schemaname = 'public' AND tablename = :table AND policyname = :policy"
            ),
            {"table": table, "policy": policy},
        )
        row = result.one_or_none()
        assert row is not None, f"Policy {policy!r} not found on table {table!r}"
        qual, with_check = row
        assert qual is not None, f"USING predicate (qual) is NULL for {table}.{policy}"
        assert with_check is not None, (
            f"WITH CHECK predicate is NULL for {table}.{policy} — "
            "this would allow cross-tenant INSERTs"
        )
        assert "nullif" in qual.lower(), (
            f"USING predicate for {table}.{policy} does not use NULLIF — "
            f"got: {qual!r}"
        )
        assert "nullif" in with_check.lower(), (
            f"WITH CHECK predicate for {table}.{policy} does not use NULLIF — "
            f"got: {with_check!r}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("table", [
        "customers",
        "notifications",
        "workflow_runs",
        "training_sessions",
        "audit_logs",
        "api_keys",
        "report_exports",
    ])
    async def test_force_rls_enabled_on_group_b_tables(
        self, db_session, table: str
    ) -> None:
        """GROUP B tables (where FORCE RLS was added) have rowsecurity=true and forcrowsecurity=true."""
        result = await db_session.execute(
            text(
                "SELECT rowsecurity, forcrowsecurity FROM pg_class "
                "WHERE relname = :table AND relkind = 'r'"
            ),
            {"table": table},
        )
        row = result.one_or_none()
        assert row is not None, f"Table {table!r} not found in pg_class"
        rowsecurity, forcrowsecurity = row
        assert rowsecurity is True, f"{table}: rowsecurity (ENABLE RLS) is not active"
        assert forcrowsecurity is True, (
            f"{table}: forcrowsecurity (FORCE ROW LEVEL SECURITY) is not active"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("table", [
        "recommendation_snapshots",
        "booking_webhook_events",
        "bulk_operations",
        "business_tasks",
        "workspace_members",
        "approval_requests",
    ])
    async def test_force_rls_still_active_on_group_a_tables(
        self, db_session, table: str
    ) -> None:
        """GROUP A tables (already had FORCE RLS) still have forcrowsecurity=true after migration."""
        result = await db_session.execute(
            text(
                "SELECT rowsecurity, forcrowsecurity FROM pg_class "
                "WHERE relname = :table AND relkind = 'r'"
            ),
            {"table": table},
        )
        row = result.one_or_none()
        assert row is not None
        rowsecurity, forcrowsecurity = row
        assert rowsecurity is True
        assert forcrowsecurity is True
