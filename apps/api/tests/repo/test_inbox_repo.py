"""Integration tests for InboxConnectionRepo and InboxMessageRepo.

Uses the session-scoped PostgreSQL testcontainer from root conftest.
Tests are isolated by UUID uniqueness — no per-test rollback needed.

Both layers of tenant protection are exercised:
  1. App-layer  — repo queries filter via TenantContext.org_id from ContextVar.
  2. DB-layer   — PostgreSQL RLS enforced because db_session runs as the
                  non-superuser corpmind_test role (see conftest._setup_test_role).

All writes use session.flush() within the shared transaction; data is visible
to subsequent reads in the same test without touching the persistent store.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from corpmind.core.database import set_rls_tenant
from corpmind.core.tenancy import clear_tenant_context, set_tenant_context
from corpmind.modules.inbox.models import InboxConnection, InboxMessage
from corpmind.modules.inbox.repo import InboxConnectionRepo, InboxMessageRepo


# ── Object factories ───────────────────────────────────────────────────────────

def _conn(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    connected_by: uuid.UUID,
) -> InboxConnection:
    return InboxConnection(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        email_address_enc="fake_enc_email",
        email_address_hash=uuid.uuid4().hex,   # unique per call — avoids uq constraint
        refresh_token_enc="fake_enc_refresh",
        scopes="openid email https://www.googleapis.com/auth/gmail.readonly",
        status="active",
        connected_by=connected_by,
    )


def _msg(
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID,
    *,
    provider_message_id: str | None = None,
    smtp_message_id: str | None = None,
) -> InboxMessage:
    return InboxMessage(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connection_id=connection_id,
        provider_message_id=provider_message_id or uuid.uuid4().hex,
        provider_thread_id=uuid.uuid4().hex,
        smtp_message_id=smtp_message_id,
        from_address="sender@example.com",
        subject="Test subject",
        received_at=datetime.now(UTC),
        body_truncated=True,
        synced_at=datetime.now(UTC),
    )


# ── InboxConnectionRepo ────────────────────────────────────────────────────────

class TestInboxConnectionRepoCreate:
    @pytest.mark.asyncio
    async def test_create_and_find_by_id(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            repo = InboxConnectionRepo(db_session)
            created = await repo.create(conn)
            await db_session.flush()

            found = await repo.find_by_id(created.id)
            assert found is not None
            assert found.id == created.id
            assert found.tenant_id == tenant_a.org_id
            assert found.status == "active"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_when_not_found(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = InboxConnectionRepo(db_session)
            result = await repo.find_by_id(uuid.uuid4())
            assert result is None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_find_by_workspace_returns_created_connection(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            repo = InboxConnectionRepo(db_session)
            created = await repo.create(conn)
            await db_session.flush()

            results = await repo.find_by_workspace(tenant_a.workspace_id)
            ids = [c.id for c in results]
            assert created.id in ids
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_find_by_workspace_returns_empty_for_unknown_workspace(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = InboxConnectionRepo(db_session)
            results = await repo.find_by_workspace(uuid.uuid4())
            assert results == []
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_find_by_email_hash_returns_connection(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            email_hash = conn.email_address_hash
            repo = InboxConnectionRepo(db_session)
            await repo.create(conn)
            await db_session.flush()

            found = await repo.find_by_email_hash(email_hash)
            assert found is not None
            assert found.email_address_hash == email_hash
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_find_by_email_hash_returns_none_for_unknown_hash(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = InboxConnectionRepo(db_session)
            result = await repo.find_by_email_hash("nonexistent" + "0" * 53)
            assert result is None
        finally:
            clear_tenant_context(token)


class TestInboxConnectionRepoUpdate:
    @pytest.mark.asyncio
    async def test_update_status_field(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            repo = InboxConnectionRepo(db_session)
            created = await repo.create(conn)
            await db_session.flush()

            conn_id = created.id   # save before expiring
            await repo.update(conn_id, {"status": "needs_reauth", "last_error": "token expired"})
            await db_session.flush()

            # Expire so the next find_by_id fetches fresh data from the DB
            db_session.expire(created)
            found = await repo.find_by_id(conn_id)
            assert found is not None
            assert found.status == "needs_reauth"
            assert found.last_error == "token expired"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_update_wrong_tenant_is_noop(self, db_session, tenant_a, tenant_b):
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
        repo = InboxConnectionRepo(db_session)
        created = await repo.create(conn)
        await db_session.flush()
        clear_tenant_context(token_a)

        # Attempt update as tenant B — no rows should be touched
        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            await repo.update(created.id, {"status": "revoked"})
            await db_session.flush()
        finally:
            clear_tenant_context(token_b)

        # Verify original status unchanged when reading as tenant A
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        conn_id = created.id   # read PK before expire to avoid sync lazy-load
        db_session.expire(created)
        found = await repo.find_by_id(conn_id)
        assert found is not None
        assert found.status == "active"
        clear_tenant_context(token_a)


class TestInboxConnectionRepoDelete:
    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            repo = InboxConnectionRepo(db_session)
            created = await repo.create(conn)
            await db_session.flush()

            deleted = await repo.delete(created.id)
            assert deleted is True
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_nonexistent_id(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = InboxConnectionRepo(db_session)
            deleted = await repo.delete(uuid.uuid4())
            assert deleted is False
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_delete_wrong_tenant_returns_false(self, db_session, tenant_a, tenant_b):
        # Create under tenant A
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
        repo = InboxConnectionRepo(db_session)
        created = await repo.create(conn)
        await db_session.flush()
        clear_tenant_context(token_a)

        # Attempt delete as tenant B — must return False (not found for B)
        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            deleted = await repo.delete(created.id)
            assert deleted is False
        finally:
            clear_tenant_context(token_b)


class TestInboxConnectionRepoTenantIsolation:
    @pytest.mark.asyncio
    async def test_find_by_id_invisible_to_other_tenant(self, db_session, tenant_a, tenant_b):
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
        repo = InboxConnectionRepo(db_session)
        created = await repo.create(conn)
        await db_session.flush()
        clear_tenant_context(token_a)

        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            result = await repo.find_by_id(created.id)
            assert result is None, "Tenant B must not see Tenant A's connection"
        finally:
            clear_tenant_context(token_b)

    @pytest.mark.asyncio
    async def test_rls_blocks_direct_sql_cross_tenant_read(self, db_session, tenant_a, tenant_b):
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
        repo = InboxConnectionRepo(db_session)
        created = await repo.create(conn)
        await db_session.flush()
        clear_tenant_context(token_a)

        # Switch to B's RLS context and issue raw SQL — no WHERE on tenant_id
        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            rows = await db_session.execute(
                text("SELECT id FROM inbox_connections WHERE id = :cid"),
                {"cid": str(created.id)},
            )
            assert rows.first() is None, "RLS must block direct SQL cross-tenant read"
        finally:
            clear_tenant_context(token_b)

    @pytest.mark.asyncio
    async def test_rls_fail_closed_without_tenant_context(self, db_session, tenant_a):
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
        repo = InboxConnectionRepo(db_session)
        created = await repo.create(conn)
        await db_session.flush()
        clear_tenant_context(token_a)

        await db_session.execute(text("RESET app.tenant_id"))
        rows = await db_session.execute(
            text("SELECT id FROM inbox_connections WHERE id = :cid"),
            {"cid": str(created.id)},
        )
        assert rows.first() is None, "Without app.tenant_id, RLS must return zero rows"


# ── InboxMessageRepo ───────────────────────────────────────────────────────────

class TestInboxMessageRepoCreate:
    @pytest.mark.asyncio
    async def test_create_and_find_by_id(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            db_session.add(conn)
            await db_session.flush()

            msg = _msg(tenant_a.org_id, conn.id)
            msg_repo = InboxMessageRepo(db_session)
            created = await msg_repo.create(msg)
            await db_session.flush()

            found = await msg_repo.find_by_id(created.id)
            assert found is not None
            assert found.id == created.id
            assert found.tenant_id == tenant_a.org_id
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_find_by_id_invisible_to_other_tenant(self, db_session, tenant_a, tenant_b):
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
        db_session.add(conn)
        await db_session.flush()

        msg = _msg(tenant_a.org_id, conn.id)
        msg_repo = InboxMessageRepo(db_session)
        created = await msg_repo.create(msg)
        await db_session.flush()
        clear_tenant_context(token_a)

        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            result = await msg_repo.find_by_id(created.id)
            assert result is None, "Tenant B must not see Tenant A's message"
        finally:
            clear_tenant_context(token_b)


class TestInboxMessageRepoIdempotent:
    @pytest.mark.asyncio
    async def test_create_if_not_exists_inserts_new_row(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            db_session.add(conn)
            await db_session.flush()

            msg = _msg(tenant_a.org_id, conn.id)
            msg_repo = InboxMessageRepo(db_session)
            was_inserted = await msg_repo.create_if_not_exists(msg)
            assert was_inserted is True
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_create_if_not_exists_skips_duplicate(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            db_session.add(conn)
            await db_session.flush()

            provider_id = uuid.uuid4().hex
            msg1 = _msg(tenant_a.org_id, conn.id, provider_message_id=provider_id)
            msg2 = _msg(tenant_a.org_id, conn.id, provider_message_id=provider_id)

            msg_repo = InboxMessageRepo(db_session)
            first = await msg_repo.create_if_not_exists(msg1)
            await db_session.flush()
            second = await msg_repo.create_if_not_exists(msg2)

            assert first is True
            assert second is False, "Duplicate provider_message_id must return False"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_create_if_not_exists_different_connections_both_inserted(self, db_session, tenant_a):
        """Same provider_message_id on different connections is allowed."""
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn1 = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            conn2 = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            db_session.add(conn1)
            db_session.add(conn2)
            await db_session.flush()

            shared_provider_id = uuid.uuid4().hex
            msg1 = _msg(tenant_a.org_id, conn1.id, provider_message_id=shared_provider_id)
            msg2 = _msg(tenant_a.org_id, conn2.id, provider_message_id=shared_provider_id)
            msg_repo = InboxMessageRepo(db_session)

            r1 = await msg_repo.create_if_not_exists(msg1)
            await db_session.flush()
            r2 = await msg_repo.create_if_not_exists(msg2)
            assert r1 is True
            assert r2 is True
        finally:
            clear_tenant_context(token)


class TestInboxMessageRepoQuery:
    @pytest.mark.asyncio
    async def test_get_by_provider_message_id(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            db_session.add(conn)
            await db_session.flush()

            provider_id = uuid.uuid4().hex
            msg = _msg(tenant_a.org_id, conn.id, provider_message_id=provider_id)
            msg_repo = InboxMessageRepo(db_session)
            await msg_repo.create(msg)
            await db_session.flush()

            found = await msg_repo.get_by_provider_message_id(conn.id, provider_id)
            assert found is not None
            assert found.provider_message_id == provider_id
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_get_by_smtp_message_id(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            db_session.add(conn)
            await db_session.flush()

            smtp_id = f"<{uuid.uuid4()}@test.local>"
            msg = _msg(tenant_a.org_id, conn.id, smtp_message_id=smtp_id)
            msg_repo = InboxMessageRepo(db_session)
            await msg_repo.create(msg)
            await db_session.flush()

            found = await msg_repo.get_by_smtp_message_id(smtp_id)
            assert found is not None
            assert found.smtp_message_id == smtp_id
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_get_by_smtp_message_id_returns_none_for_unknown(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            msg_repo = InboxMessageRepo(db_session)
            result = await msg_repo.get_by_smtp_message_id("<nonexistent@test.local>")
            assert result is None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_list_by_connection_returns_messages(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            db_session.add(conn)
            await db_session.flush()

            msg1 = _msg(tenant_a.org_id, conn.id)
            msg2 = _msg(tenant_a.org_id, conn.id)
            msg_repo = InboxMessageRepo(db_session)
            await msg_repo.create(msg1)
            await msg_repo.create(msg2)
            await db_session.flush()

            results = await msg_repo.list_by_connection(conn.id)
            ids = [m.id for m in results]
            assert msg1.id in ids
            assert msg2.id in ids
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_list_by_connection_excludes_other_connections(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn1 = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            conn2 = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            db_session.add(conn1)
            db_session.add(conn2)
            await db_session.flush()

            msg1 = _msg(tenant_a.org_id, conn1.id)
            msg2 = _msg(tenant_a.org_id, conn2.id)
            msg_repo = InboxMessageRepo(db_session)
            await msg_repo.create(msg1)
            await msg_repo.create(msg2)
            await db_session.flush()

            results = await msg_repo.list_by_connection(conn1.id)
            ids = [m.id for m in results]
            assert msg1.id in ids
            assert msg2.id not in ids
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_list_recent_returns_tenant_messages(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
            db_session.add(conn)
            await db_session.flush()

            msg = _msg(tenant_a.org_id, conn.id)
            msg_repo = InboxMessageRepo(db_session)
            await msg_repo.create(msg)
            await db_session.flush()

            results = await msg_repo.list_recent()
            ids = [m.id for m in results]
            assert msg.id in ids
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_rls_blocks_message_read_across_tenants(self, db_session, tenant_a, tenant_b):
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        conn = _conn(tenant_a.org_id, tenant_a.workspace_id, tenant_a.user_id)
        db_session.add(conn)
        await db_session.flush()
        msg = _msg(tenant_a.org_id, conn.id)
        msg_repo = InboxMessageRepo(db_session)
        await msg_repo.create(msg)
        await db_session.flush()
        clear_tenant_context(token_a)

        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            rows = await db_session.execute(
                text("SELECT id FROM inbox_messages WHERE id = :mid"),
                {"mid": str(msg.id)},
            )
            assert rows.first() is None, "RLS must block Tenant B from reading Tenant A's messages"
        finally:
            clear_tenant_context(token_b)
