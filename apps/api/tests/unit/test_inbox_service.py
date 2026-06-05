"""Unit tests for InboxService — 100% coverage target.

Encryption is patched via patch.dict on the module-level key registry for
roundtrip tests; for all other service tests encrypt/decrypt are patched as
returning predictable sentinel strings so tests remain fast and focused on
service logic rather than cryptographic correctness (which is covered in
test_encryption.py).

Session refresh mock: after commit() SQLAlchemy expires server-default columns
(created_at, updated_at).  The _make_refresh_side_effect() helper simulates
refresh() reloading those columns from the "database".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import ConflictError, DecryptionError, NotFoundError
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.inbox.models import InboxConnection, InboxMessage
from corpmind.modules.inbox.schemas import InboxConnectionCreate
from corpmind.modules.inbox.service import (
    InboxService,
    _email_address_hash,
    _to_connection_out,
    _to_message_out,
)

# ── Test key material (same as test_encryption.py) ───────────────────────────

_KEY_V1 = bytes(range(32))
_REGISTRY_V1 = {1: _KEY_V1}

# ── Shared fixtures ────────────────────────────────────────────────────────────

_ORG_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_CONN_ID = uuid.uuid4()
_MSG_ID = uuid.uuid4()
_OUTBOUND_ID = uuid.uuid4()

_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="trainer",
    request_id="req-svc-test-001",
    plan_tier="starter",
)

_NOW = datetime(2026, 6, 6, 10, 0, 0, tzinfo=UTC)


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _make_conn(
    conn_id: uuid.UUID = _CONN_ID,
    org_id: uuid.UUID = _ORG_ID,
) -> InboxConnection:
    conn = InboxConnection(
        id=conn_id,
        tenant_id=org_id,
        workspace_id=_WS_ID,
        provider="gmail",
        email_address_enc="enc:email@example.com",
        refresh_token_enc="enc:refresh-token",
        access_token_enc=None,
        email_address_hash="a" * 64,
        scopes="https://www.googleapis.com/auth/gmail.readonly",
        status="active",
        last_sync_at=None,
        last_error=None,
        connected_by=_USER_ID,
    )
    conn.created_at = _NOW
    conn.updated_at = _NOW
    return conn


def _make_msg(
    connection_id: uuid.UUID = _CONN_ID,
    org_id: uuid.UUID = _ORG_ID,
) -> InboxMessage:
    msg = InboxMessage(
        id=_MSG_ID,
        tenant_id=org_id,
        connection_id=connection_id,
        provider_message_id="gmail-abc123",
        provider_thread_id=None,
        smtp_message_id="<TEST@corpmind.ai>",
        in_reply_to="<TEST@corpmind.ai>",
        references_header=None,
        outbound_message_id=None,
        match_method=None,
        from_address="hr@acme.example",
        subject="Re: Training",
        received_at=_NOW,
        body_snippet_enc=None,
        body_truncated=False,
        reply_intent=None,
    )
    msg.synced_at = _NOW
    return msg


def _make_create_req(
    email: str = "trainer@example.com",
    access_token: str | None = None,
) -> InboxConnectionCreate:
    return InboxConnectionCreate(
        workspace_id=_WS_ID,
        provider="gmail",
        email_address=email,
        refresh_token="raw-refresh-token",
        access_token=access_token,
        scopes="https://www.googleapis.com/auth/gmail.readonly",
        connected_by=_USER_ID,
    )


def _make_refresh_side_effect(conn: InboxConnection):
    """Return an async side_effect that stamps created_at/updated_at on the object."""
    async def _refresh(obj: object) -> None:
        if obj is conn:
            obj.created_at = _NOW  # type: ignore[attr-defined]
            obj.updated_at = _NOW  # type: ignore[attr-defined]
    return _refresh


# ── _email_address_hash ────────────────────────────────────────────────────────

def test_email_address_hash_is_deterministic():
    """Same email + same tenant always produce the same hash."""
    org = uuid.uuid4()
    h1 = _email_address_hash("trainer@example.com", org)
    h2 = _email_address_hash("trainer@example.com", org)
    assert h1 == h2


def test_email_address_hash_is_tenant_scoped():
    """Same email produces different hashes for different tenants."""
    email = "trainer@example.com"
    h_a = _email_address_hash(email, uuid.uuid4())
    h_b = _email_address_hash(email, uuid.uuid4())
    assert h_a != h_b


def test_email_address_hash_is_64_hex_chars():
    """HMAC-SHA256 hexdigest is always 64 hexadecimal characters."""
    h = _email_address_hash("x@y.com", uuid.uuid4())
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_email_address_hash_differs_from_recipient_hmac():
    """_email_address_hash(tenant_id.bytes) ≠ recipient_hmac(str(tenant_id)) for same input."""
    from corpmind.modules.outreach.service import recipient_hmac

    org = uuid.uuid4()
    email = "trainer@example.com"
    inbox_hash = _email_address_hash(email, org)
    outreach_hash = recipient_hmac(email, org)
    assert inbox_hash != outreach_hash


# ── create_connection ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_connection_happy_path():
    """New connection is persisted and DTO contains the plaintext email."""
    token = set_tenant_context(_CTX)
    session = _mock_session()
    conn = _make_conn()
    session.refresh = AsyncMock(side_effect=_make_refresh_side_effect(conn))

    with patch("corpmind.modules.inbox.service.encrypt", return_value="enc:value") as mock_enc:
        svc = InboxService(session)
        svc._conn_repo.find_by_email_hash = AsyncMock(return_value=None)
        svc._conn_repo.create = AsyncMock(side_effect=lambda c: setattr(c, "id", _CONN_ID) or c)

        # Inject pre-populated conn so refresh has something to work with.
        async def _create_side(c: InboxConnection):
            c.id = conn.id
            c.created_at = _NOW
            c.updated_at = _NOW
            return c

        svc._conn_repo.create = AsyncMock(side_effect=_create_side)

        req = _make_create_req(email="trainer@example.com")
        result = await svc.create_connection(req)

    clear_tenant_context(token)

    assert result.email_address == "trainer@example.com"
    assert result.provider == "gmail"
    assert result.status == "active"
    assert mock_enc.call_count >= 2  # email + refresh_token at minimum
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_connection_with_access_token_encrypts_three_fields():
    """Access token is encrypted when present."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    with patch("corpmind.modules.inbox.service.encrypt", return_value="enc:value") as mock_enc:
        svc = InboxService(session)
        svc._conn_repo.find_by_email_hash = AsyncMock(return_value=None)

        async def _create_side(c: InboxConnection):
            c.id = uuid.uuid4()
            c.created_at = _NOW
            c.updated_at = _NOW
            return c

        svc._conn_repo.create = AsyncMock(side_effect=_create_side)

        req = _make_create_req(email="trainer@example.com", access_token="raw-access-token")
        await svc.create_connection(req)

    clear_tenant_context(token)
    # email, refresh_token, access_token → 3 encrypt() calls
    assert mock_enc.call_count == 3


@pytest.mark.asyncio
async def test_create_connection_none_access_token_not_encrypted():
    """No encrypt() call is made for a None access token."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    with patch("corpmind.modules.inbox.service.encrypt", return_value="enc:value") as mock_enc:
        svc = InboxService(session)
        svc._conn_repo.find_by_email_hash = AsyncMock(return_value=None)

        async def _create_side(c: InboxConnection):
            c.id = uuid.uuid4()
            c.created_at = _NOW
            c.updated_at = _NOW
            return c

        svc._conn_repo.create = AsyncMock(side_effect=_create_side)

        req = _make_create_req(access_token=None)
        result = await svc.create_connection(req)

    clear_tenant_context(token)
    assert mock_enc.call_count == 2  # email + refresh only
    assert result.status == "active"


@pytest.mark.asyncio
async def test_create_connection_duplicate_raises_conflict():
    """ConflictError when find_by_email_hash returns an existing connection."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    with patch("corpmind.modules.inbox.service.encrypt", return_value="enc:value"):
        svc = InboxService(session)
        svc._conn_repo.find_by_email_hash = AsyncMock(return_value=_make_conn())

        with pytest.raises(ConflictError, match="already exists"):
            await svc.create_connection(_make_create_req())

    clear_tenant_context(token)
    session.commit.assert_not_awaited()


# ── get_connection ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_connection_happy_path():
    """DTO contains the decrypted email address."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    with patch(
        "corpmind.modules.inbox.service.decrypt", return_value="trainer@example.com"
    ):
        svc = InboxService(session)
        svc._conn_repo.find_by_id = AsyncMock(return_value=_make_conn())

        result = await svc.get_connection(_CONN_ID)

    clear_tenant_context(token)

    assert result.email_address == "trainer@example.com"
    assert result.id == _CONN_ID
    assert result.provider == "gmail"


@pytest.mark.asyncio
async def test_get_connection_not_found_raises():
    """NotFoundError when connection does not exist for the tenant."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    svc = InboxService(session)
    svc._conn_repo.find_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError, match=str(_CONN_ID)):
        await svc.get_connection(_CONN_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_get_connection_decryption_error_propagates():
    """DecryptionError from corrupted ciphertext is not swallowed."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    with patch(
        "corpmind.modules.inbox.service.decrypt",
        side_effect=DecryptionError("tampered ciphertext"),
    ):
        svc = InboxService(session)
        svc._conn_repo.find_by_id = AsyncMock(return_value=_make_conn())

        with pytest.raises(DecryptionError):
            await svc.get_connection(_CONN_ID)

    clear_tenant_context(token)


# ── update_connection ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_connection_happy_path():
    """update() is called and session is committed."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    svc = InboxService(session)
    svc._conn_repo.find_by_id = AsyncMock(return_value=_make_conn())
    svc._conn_repo.update = AsyncMock()

    await svc.update_connection(_CONN_ID, {"status": "needs_reauth"})

    clear_tenant_context(token)

    svc._conn_repo.update.assert_awaited_once_with(_CONN_ID, {"status": "needs_reauth"})
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_connection_not_found_raises():
    """NotFoundError when connection does not exist; repo.update is not called."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    svc = InboxService(session)
    svc._conn_repo.find_by_id = AsyncMock(return_value=None)
    svc._conn_repo.update = AsyncMock()

    with pytest.raises(NotFoundError):
        await svc.update_connection(_CONN_ID, {"status": "error"})

    clear_tenant_context(token)
    svc._conn_repo.update.assert_not_awaited()
    session.commit.assert_not_awaited()


# ── delete_connection ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_connection_happy_path():
    """Commit is called after successful deletion."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    svc = InboxService(session)
    svc._conn_repo.delete = AsyncMock(return_value=True)

    await svc.delete_connection(_CONN_ID)

    clear_tenant_context(token)
    svc._conn_repo.delete.assert_awaited_once_with(_CONN_ID)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_connection_not_found_raises():
    """NotFoundError when repo.delete returns False; commit is not called."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    svc = InboxService(session)
    svc._conn_repo.delete = AsyncMock(return_value=False)

    with pytest.raises(NotFoundError):
        await svc.delete_connection(_CONN_ID)

    clear_tenant_context(token)
    session.commit.assert_not_awaited()


# ── create_message ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_message_encrypts_body_snippet():
    """body_snippet_enc is set on the ORM object before the repo call."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    msg = _make_msg()

    with patch(
        "corpmind.modules.inbox.service.encrypt", return_value="enc:body"
    ) as mock_enc:
        svc = InboxService(session)
        svc._msg_repo.create = AsyncMock(return_value=msg)

        result = await svc.create_message(msg, body_snippet="Hello, reply here.")

    clear_tenant_context(token)

    mock_enc.assert_called_once_with("Hello, reply here.")
    assert msg.body_snippet_enc == "enc:body"
    assert result.body_snippet == "Hello, reply here."
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_message_none_body_snippet_skips_encrypt():
    """No encrypt() call and body_snippet_enc unchanged when body_snippet is None."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    msg = _make_msg()

    with patch("corpmind.modules.inbox.service.encrypt") as mock_enc:
        svc = InboxService(session)
        svc._msg_repo.create = AsyncMock(return_value=msg)

        result = await svc.create_message(msg, body_snippet=None)

    clear_tenant_context(token)

    mock_enc.assert_not_called()
    assert result.body_snippet is None


# ── create_if_not_exists ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_if_not_exists_inserts_and_commits():
    """Returns (True, out) and commits when the row is new."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    msg = _make_msg()

    with patch("corpmind.modules.inbox.service.encrypt", return_value="enc:body"):
        svc = InboxService(session)
        svc._msg_repo.create_if_not_exists = AsyncMock(return_value=True)

        was_inserted, out = await svc.create_if_not_exists(msg, body_snippet="Reply text")

    clear_tenant_context(token)

    assert was_inserted is True
    assert out.body_snippet == "Reply text"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_if_not_exists_duplicate_skips_commit():
    """Returns (False, out) and does NOT commit when ON CONFLICT DO NOTHING fires."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    msg = _make_msg()

    with patch("corpmind.modules.inbox.service.encrypt", return_value="enc:body"):
        svc = InboxService(session)
        svc._msg_repo.create_if_not_exists = AsyncMock(return_value=False)

        was_inserted, out = await svc.create_if_not_exists(msg, body_snippet="Reply text")

    clear_tenant_context(token)

    assert was_inserted is False
    assert out.connection_id == msg.connection_id
    session.commit.assert_not_awaited()


# ── get_message ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_message_happy_path():
    """DTO contains the decrypted body snippet."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    msg = _make_msg()
    msg.body_snippet_enc = "enc:body"

    with patch(
        "corpmind.modules.inbox.service.decrypt", return_value="Decrypted body text"
    ):
        svc = InboxService(session)
        svc._msg_repo.find_by_id = AsyncMock(return_value=msg)

        result = await svc.get_message(_MSG_ID)

    clear_tenant_context(token)

    assert result.body_snippet == "Decrypted body text"
    assert result.id == _MSG_ID


@pytest.mark.asyncio
async def test_get_message_null_body_snippet_returns_none():
    """body_snippet is None in the DTO when body_snippet_enc is None (no decrypt call)."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    msg = _make_msg()
    msg.body_snippet_enc = None

    with patch("corpmind.modules.inbox.service.decrypt") as mock_dec:
        svc = InboxService(session)
        svc._msg_repo.find_by_id = AsyncMock(return_value=msg)

        result = await svc.get_message(_MSG_ID)

    clear_tenant_context(token)

    mock_dec.assert_not_called()
    assert result.body_snippet is None


@pytest.mark.asyncio
async def test_get_message_not_found_raises():
    """NotFoundError when message does not exist for this tenant."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    svc = InboxService(session)
    svc._msg_repo.find_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError, match=str(_MSG_ID)):
        await svc.get_message(_MSG_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_get_message_decryption_error_propagates():
    """DecryptionError from a corrupted body_snippet_enc is not swallowed."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    msg = _make_msg()
    msg.body_snippet_enc = "corrupted-ciphertext"

    with patch(
        "corpmind.modules.inbox.service.decrypt",
        side_effect=DecryptionError("GCM tag mismatch"),
    ):
        svc = InboxService(session)
        svc._msg_repo.find_by_id = AsyncMock(return_value=msg)

        with pytest.raises(DecryptionError):
            await svc.get_message(_MSG_ID)

    clear_tenant_context(token)


# ── match_reply ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_match_reply_returns_outbound_id_on_match():
    """Returns the UUID from outbound_messages when smtp_message_id is found."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    row = (str(_OUTBOUND_ID),)
    result_mock = MagicMock()
    result_mock.one_or_none = MagicMock(return_value=row)
    session.execute = AsyncMock(return_value=result_mock)

    svc = InboxService(session)
    result = await svc.match_reply("<ULID@corpmind.ai>")

    clear_tenant_context(token)

    assert result == _OUTBOUND_ID
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_match_reply_returns_none_when_unmatched():
    """Returns None when no outbound message has this smtp_message_id."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    result_mock = MagicMock()
    result_mock.one_or_none = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=result_mock)

    svc = InboxService(session)
    result = await svc.match_reply("<UNKNOWN@corpmind.ai>")

    clear_tenant_context(token)

    assert result is None


# ── DTO mapping ────────────────────────────────────────────────────────────────

def test_to_connection_out_maps_all_fields():
    """_to_connection_out produces a DTO with every field from the ORM model."""
    conn = _make_conn()
    out = _to_connection_out(conn, "decrypted@example.com")

    assert out.id == conn.id
    assert out.workspace_id == conn.workspace_id
    assert out.provider == "gmail"
    assert out.email_address == "decrypted@example.com"
    assert out.scopes == conn.scopes
    assert out.status == "active"
    assert out.last_sync_at is None
    assert out.last_error is None
    assert out.connected_by == conn.connected_by
    assert out.created_at == _NOW
    assert out.updated_at == _NOW


def test_to_message_out_maps_all_fields():
    """_to_message_out produces a DTO with every field from the ORM model."""
    msg = _make_msg()
    out = _to_message_out(msg, "Decrypted snippet")

    assert out.id == msg.id
    assert out.connection_id == msg.connection_id
    assert out.provider_message_id == "gmail-abc123"
    assert out.smtp_message_id == "<TEST@corpmind.ai>"
    assert out.from_address == "hr@acme.example"
    assert out.subject == "Re: Training"
    assert out.received_at == _NOW
    assert out.body_snippet == "Decrypted snippet"
    assert out.body_truncated is False
    assert out.reply_intent is None
    assert out.synced_at == _NOW


# ── Encryption roundtrip (uses real keys via patched registry) ────────────────

@pytest.mark.asyncio
async def test_encryption_roundtrip_through_service():
    """create_connection + get_connection roundtrip with real AES-256-GCM keys."""
    token = set_tenant_context(_CTX)
    session = _mock_session()

    email = "roundtrip@example.com"

    with (
        patch.dict("corpmind.core.encryption._KEY_REGISTRY", _REGISTRY_V1, clear=True),
        patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 1),
    ):
        svc = InboxService(session)
        svc._conn_repo.find_by_email_hash = AsyncMock(return_value=None)

        stored_enc: list[str] = []

        async def _create_side(c: InboxConnection):
            c.id = _CONN_ID
            c.created_at = _NOW
            c.updated_at = _NOW
            stored_enc.append(c.email_address_enc)
            return c

        svc._conn_repo.create = AsyncMock(side_effect=_create_side)

        await svc.create_connection(_make_create_req(email=email))

        # Verify that the stored ciphertext is not the plaintext
        assert len(stored_enc) == 1
        assert stored_enc[0] != email
        assert len(stored_enc[0]) > 10  # non-empty ciphertext

        # Now simulate get_connection: return a conn with the stored ciphertext
        conn_with_enc = _make_conn()
        conn_with_enc.email_address_enc = stored_enc[0]
        svc._conn_repo.find_by_id = AsyncMock(return_value=conn_with_enc)

        result = await svc.get_connection(_CONN_ID)

    clear_tenant_context(token)
    assert result.email_address == email
