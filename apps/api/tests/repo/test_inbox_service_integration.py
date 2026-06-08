"""Integration tests for InboxService against the real PostgreSQL testcontainer.

InboxService commits internally — each service call ends the current transaction
and a new one begins automatically (SQLAlchemy autobegin).  After each commit,
SET LOCAL app.tenant_id is reset, which would block the session.refresh() call
inside create_connection().  To prevent this, all service tests use a
session-level SET (not SET LOCAL) via _rls(), so the GUC persists across
internal commits.  This matches production behaviour where the DB role has
BYPASSRLS (SET LOCAL does not apply at that level).

Encryption is tested end-to-end: the real AES-256-GCM encrypt/decrypt path runs
with a test key injected via patch.dict.

Google API calls are mocked with AsyncMock — no live network calls.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.core.tenancy import clear_tenant_context, set_tenant_context
from corpmind.modules.inbox.models import InboxConnection, InboxMessage
from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens
from corpmind.modules.inbox.repo import InboxConnectionRepo, InboxMessageRepo
from corpmind.modules.inbox.schemas import InboxConnectionCreate
from corpmind.modules.inbox.service import InboxService


# ── Encryption test key ────────────────────────────────────────────────────────
# encryption.py documents this as the correct patching approach:
#   patch.dict("corpmind.core.encryption._KEY_REGISTRY", {1: key}, clear=True)
#   patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 1)

_TEST_ENC_KEY = bytes.fromhex("ab" * 32)  # 32 bytes — valid AES-256 key


async def _rls(session, tenant_id: uuid.UUID) -> None:
    """Set app.tenant_id at SESSION level (not LOCAL) so it survives internal commits.

    InboxService calls session.commit() then session.refresh() internally.
    SET LOCAL resets on commit, blocking the refresh under RLS.  SET (session-level)
    persists across commits within the same connection — matching production behaviour
    where the app role has BYPASSRLS and the GUC is set once per session.
    """
    await session.execute(text(f"SET app.tenant_id = '{tenant_id}'"))


@pytest.fixture(autouse=True)
def _enc_key():
    """Inject a test AES-256 key so service tests can round-trip encrypt/decrypt."""
    with (
        patch.dict("corpmind.core.encryption._KEY_REGISTRY", {1: _TEST_ENC_KEY}, clear=True),
        patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 1),
    ):
        yield


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _create_req(
    workspace_id: uuid.UUID,
    connected_by: uuid.UUID,
    *,
    email: str | None = None,
) -> InboxConnectionCreate:
    return InboxConnectionCreate(
        workspace_id=workspace_id,
        provider="gmail",
        email_address=email or f"test-{uuid.uuid4().hex[:8]}@example.com",
        refresh_token="refresh_tok_abc",
        access_token="access_tok_xyz",
        scopes="openid email https://www.googleapis.com/auth/gmail.readonly",
        token_expiry_at=None,
        connected_by=connected_by,
    )


def _msg_obj(
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
        subject="Hello",
        received_at=datetime.now(UTC),
        body_truncated=True,
        synced_at=datetime.now(UTC),
    )


# ── InboxService — connection management ──────────────────────────────────────

class TestInboxServiceCreateConnection:
    @pytest.mark.asyncio
    async def test_create_connection_persists_and_encrypts(self, db_session, tenant_a):
        """Tokens are stored encrypted; the returned DTO contains plaintext email."""
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            out = await InboxService(db_session).create_connection(req)

            assert out.id is not None
            assert out.email_address == req.email_address
            assert out.status == "active"

            # Re-activate RLS after the internal commit, then verify the raw row
            await _rls(db_session, tenant_a.org_id)
            raw = await InboxConnectionRepo(db_session).find_by_id(out.id)
            assert raw is not None
            # Stored ciphertext must differ from plaintext
            assert raw.email_address_enc != req.email_address
            assert raw.refresh_token_enc != req.refresh_token
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_create_connection_duplicate_email_raises_conflict(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id, email=email)

            await _rls(db_session, tenant_a.org_id)
            await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            with pytest.raises(ConflictError):
                await InboxService(db_session).create_connection(req)
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_create_connection_same_email_different_tenants_allowed(
        self, db_session, tenant_a, tenant_b
    ):
        """Same email address is allowed across different tenants (separate hashes)."""
        email = f"shared-{uuid.uuid4().hex[:8]}@example.com"

        token_a = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        req_a = _create_req(tenant_a.workspace_id, tenant_a.user_id, email=email)
        out_a = await InboxService(db_session).create_connection(req_a)
        clear_tenant_context(token_a)
        assert out_a.id is not None

        token_b = set_tenant_context(tenant_b)
        await _rls(db_session, tenant_b.org_id)
        req_b = _create_req(tenant_b.workspace_id, tenant_b.user_id, email=email)
        try:
            out_b = await InboxService(db_session).create_connection(req_b)
            assert out_b.id is not None
            assert out_b.id != out_a.id
        finally:
            clear_tenant_context(token_b)


class TestInboxServiceGetConnection:
    @pytest.mark.asyncio
    async def test_get_connection_decrypts_email(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            created = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            out = await InboxService(db_session).get_connection(created.id)
            assert out.email_address == req.email_address
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_get_connection_not_found_raises(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            with pytest.raises(NotFoundError):
                await InboxService(db_session).get_connection(uuid.uuid4())
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_get_workspace_connection_returns_first(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            created = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            out = await InboxService(db_session).get_workspace_connection()
            assert out.id == created.id
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_get_workspace_connection_not_found_raises(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            with pytest.raises(NotFoundError):
                await InboxService(db_session).get_workspace_connection()
        finally:
            clear_tenant_context(token)


class TestInboxServiceUpdateDeleteConnection:
    @pytest.mark.asyncio
    async def test_update_connection_changes_status(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            created = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            await InboxService(db_session).update_connection(
                created.id, {"status": "needs_reauth", "last_error": "expired"}
            )

            await _rls(db_session, tenant_a.org_id)
            out = await InboxService(db_session).get_connection(created.id)
            assert out.status == "needs_reauth"
            assert out.last_error == "expired"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_update_connection_not_found_raises(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            with pytest.raises(NotFoundError):
                await InboxService(db_session).update_connection(uuid.uuid4(), {"status": "revoked"})
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_delete_connection_removes_row(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            created = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            await InboxService(db_session).delete_connection(created.id)

            await _rls(db_session, tenant_a.org_id)
            with pytest.raises(NotFoundError):
                await InboxService(db_session).get_connection(created.id)
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_delete_connection_not_found_raises(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            with pytest.raises(NotFoundError):
                await InboxService(db_session).delete_connection(uuid.uuid4())
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_disconnect_connection_calls_google_revoke(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            created = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            with patch(
                "corpmind.modules.inbox.service.revoke_google_token",
                new_callable=AsyncMock,
            ) as mock_revoke:
                await InboxService(db_session).disconnect_connection(created.id)
                mock_revoke.assert_awaited_once()

            await _rls(db_session, tenant_a.org_id)
            with pytest.raises(NotFoundError):
                await InboxService(db_session).get_connection(created.id)
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_disconnect_connection_succeeds_even_when_revoke_fails(self, db_session, tenant_a):
        """Token revocation is best-effort — connection must be deleted regardless."""
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            created = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            with patch(
                "corpmind.modules.inbox.service.revoke_google_token",
                new_callable=AsyncMock,
                side_effect=Exception("network error"),
            ):
                await InboxService(db_session).disconnect_connection(created.id)

            await _rls(db_session, tenant_a.org_id)
            with pytest.raises(NotFoundError):
                await InboxService(db_session).get_connection(created.id)
        finally:
            clear_tenant_context(token)


# ── InboxService — token operations ───────────────────────────────────────────

class TestInboxServiceTokenOperations:
    @pytest.mark.asyncio
    async def test_refresh_access_token_updates_status_to_active(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            req_set_needs_reauth = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            created = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            await InboxService(db_session).update_connection(created.id, {"status": "needs_reauth"})

            new_tokens = GoogleTokens(
                access_token="new_access_tok",
                refresh_token=None,
                expires_in=3600,
                scope="openid email",
            )
            await _rls(db_session, tenant_a.org_id)
            with patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                return_value=new_tokens,
            ):
                out = await InboxService(db_session).refresh_access_token(created.id)

            assert out.status == "active"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_refresh_access_token_revoked_marks_status_revoked(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            created = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            with patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                side_effect=ValidationError("token_revoked"),
            ):
                with pytest.raises(ValidationError):
                    await InboxService(db_session).refresh_access_token(created.id)

            await _rls(db_session, tenant_a.org_id)
            out = await InboxService(db_session).get_connection(created.id)
            assert out.status == "revoked"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_check_connection_health_healthy(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            created = await InboxService(db_session).create_connection(req)

            good_tokens = GoogleTokens(
                access_token="fresh_tok", refresh_token=None, expires_in=3600, scope="openid email"
            )
            good_profile = GmailProfile(email=req.email_address, name="Test")

            await _rls(db_session, tenant_a.org_id)
            with (
                patch(
                    "corpmind.modules.inbox.service.refresh_google_token",
                    new_callable=AsyncMock,
                    return_value=good_tokens,
                ),
                patch(
                    "corpmind.modules.inbox.service.fetch_gmail_profile",
                    new_callable=AsyncMock,
                    return_value=good_profile,
                ),
            ):
                result = await InboxService(db_session).check_connection_health(created.id)

            assert result.healthy is True
            assert result.status == "active"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_check_connection_health_revoked_token(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            created = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            with patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                side_effect=ValidationError("revoked"),
            ):
                result = await InboxService(db_session).check_connection_health(created.id)

            assert result.healthy is False
            assert result.status == "revoked"
        finally:
            clear_tenant_context(token)


# ── InboxService — message operations ─────────────────────────────────────────

class TestInboxServiceMessages:
    @pytest.mark.asyncio
    async def test_create_message_encrypts_body_snippet(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            conn_out = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            msg = _msg_obj(tenant_a.org_id, conn_out.id)
            out = await InboxService(db_session).create_message(msg, body_snippet="Hello reply")

            assert out.body_snippet == "Hello reply"

            # Raw stored value must be ciphertext
            await _rls(db_session, tenant_a.org_id)
            raw = await InboxMessageRepo(db_session).find_by_id(out.id)
            assert raw is not None
            assert raw.body_snippet_enc != "Hello reply"
            assert raw.body_snippet_enc is not None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_get_message_decrypts_body_snippet(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            conn_out = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            msg = _msg_obj(tenant_a.org_id, conn_out.id)
            created = await InboxService(db_session).create_message(msg, body_snippet="Decrypted snippet")

            await _rls(db_session, tenant_a.org_id)
            fetched = await InboxService(db_session).get_message(created.id)
            assert fetched.body_snippet == "Decrypted snippet"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_create_message_without_snippet(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            conn_out = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            msg = _msg_obj(tenant_a.org_id, conn_out.id)
            out = await InboxService(db_session).create_message(msg, body_snippet=None)
            assert out.body_snippet is None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_create_if_not_exists_returns_true_on_first_insert(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            conn_out = await InboxService(db_session).create_connection(req)

            await _rls(db_session, tenant_a.org_id)
            msg = _msg_obj(tenant_a.org_id, conn_out.id)
            was_inserted, out = await InboxService(db_session).create_if_not_exists(msg, "snippet")
            assert was_inserted is True
            assert out.body_snippet == "snippet"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_create_if_not_exists_returns_false_on_duplicate(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
            conn_out = await InboxService(db_session).create_connection(req)

            provider_id = uuid.uuid4().hex
            await _rls(db_session, tenant_a.org_id)
            msg1 = _msg_obj(tenant_a.org_id, conn_out.id, provider_message_id=provider_id)
            was_inserted, _ = await InboxService(db_session).create_if_not_exists(msg1)
            assert was_inserted is True

            await _rls(db_session, tenant_a.org_id)
            msg2 = _msg_obj(tenant_a.org_id, conn_out.id, provider_message_id=provider_id)
            was_inserted2, _ = await InboxService(db_session).create_if_not_exists(msg2)
            assert was_inserted2 is False
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_get_message_not_found_raises(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            with pytest.raises(NotFoundError):
                await InboxService(db_session).get_message(uuid.uuid4())
        finally:
            clear_tenant_context(token)


# ── InboxService — reply matching ─────────────────────────────────────────────

class TestInboxServiceReplyMatching:
    @pytest.mark.asyncio
    async def test_match_reply_returns_none_when_no_outbound_match(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            result = await InboxService(db_session).match_reply("<nonexistent@test.local>")
            assert result is None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_match_reply_returns_outbound_id_on_match(self, db_engine, db_session, tenant_a):
        """Seed a minimal outbound_messages row via NullPool (bypasses RLS for setup),
        then verify match_reply() resolves the smtp_message_id to its UUID."""
        smtp_id = f"<{uuid.uuid4()}@test.local>"
        outbound_id = str(uuid.uuid4())
        contact_id = str(uuid.uuid4())

        # NullPool seed uses the postgres superuser — bypasses RLS for test data setup
        seed_engine = create_async_engine(
            db_engine.url.render_as_string(hide_password=False), poolclass=NullPool
        )
        try:
            async with seed_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO outbound_messages"
                        " (id, tenant_id, contact_id, channel, body, status, smtp_message_id)"
                        " VALUES (:id, :tid, :cid, 'email', 'Test body', 'sent', :mid)"
                    ),
                    {
                        "id": outbound_id,
                        "tid": str(tenant_a.org_id),
                        "cid": contact_id,
                        "mid": smtp_id,
                    },
                )
        finally:
            await seed_engine.dispose()

        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            result = await InboxService(db_session).match_reply(smtp_id)
            assert result is not None
            assert str(result) == outbound_id
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_match_reply_is_tenant_scoped(self, db_engine, db_session, tenant_a, tenant_b):
        """match_reply must not return a match from a different tenant's outbound_messages."""
        smtp_id = f"<{uuid.uuid4()}@cross-tenant.local>"
        outbound_id = str(uuid.uuid4())
        contact_id = str(uuid.uuid4())

        seed_engine = create_async_engine(
            db_engine.url.render_as_string(hide_password=False), poolclass=NullPool
        )
        try:
            async with seed_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO outbound_messages"
                        " (id, tenant_id, contact_id, channel, body, status, smtp_message_id)"
                        " VALUES (:id, :tid, :cid, 'email', 'Body', 'sent', :mid)"
                    ),
                    {
                        "id": outbound_id,
                        "tid": str(tenant_a.org_id),   # seeded under tenant A
                        "cid": contact_id,
                        "mid": smtp_id,
                    },
                )
        finally:
            await seed_engine.dispose()

        # Querying as tenant B — must return None (different tenant)
        token_b = set_tenant_context(tenant_b)
        await _rls(db_session, tenant_b.org_id)
        try:
            result = await InboxService(db_session).match_reply(smtp_id)
            assert result is None, "match_reply must be tenant-scoped"
        finally:
            clear_tenant_context(token_b)


# ── Tenant isolation — service layer ──────────────────────────────────────────

class TestInboxServiceTenantIsolation:
    @pytest.mark.asyncio
    async def test_connection_invisible_across_tenants(self, db_session, tenant_a, tenant_b):
        token_a = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
        created = await InboxService(db_session).create_connection(req)
        clear_tenant_context(token_a)

        # Tenant B cannot read tenant A's connection
        token_b = set_tenant_context(tenant_b)
        await _rls(db_session, tenant_b.org_id)
        try:
            with pytest.raises(NotFoundError):
                await InboxService(db_session).get_connection(created.id)
        finally:
            clear_tenant_context(token_b)

    @pytest.mark.asyncio
    async def test_message_invisible_across_tenants(self, db_session, tenant_a, tenant_b):
        token_a = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        req = _create_req(tenant_a.workspace_id, tenant_a.user_id)
        conn_out = await InboxService(db_session).create_connection(req)

        await _rls(db_session, tenant_a.org_id)
        msg = _msg_obj(tenant_a.org_id, conn_out.id)
        msg_out = await InboxService(db_session).create_message(msg)
        clear_tenant_context(token_a)

        token_b = set_tenant_context(tenant_b)
        await _rls(db_session, tenant_b.org_id)
        try:
            with pytest.raises(NotFoundError):
                await InboxService(db_session).get_message(msg_out.id)
        finally:
            clear_tenant_context(token_b)
