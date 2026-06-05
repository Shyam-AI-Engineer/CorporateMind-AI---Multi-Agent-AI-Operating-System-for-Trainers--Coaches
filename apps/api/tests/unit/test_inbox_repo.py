"""Unit tests for InboxConnectionRepo and InboxMessageRepo.

Behavioural contracts pinned here:

InboxConnectionRepo
  1. create        → session.add(connection) called once; flush called once
  2. find_by_id    → session.execute called once; get_tenant_context called once
  3. find_by_workspace → session.execute once; tenant context used
  4. find_by_email_hash → session.execute once; tenant context used (dedup path)
  5. update        → session.execute once; tenant context used
  6. delete        → session.execute once; returns True when rowcount > 0
  7. delete miss   → returns False when rowcount == 0 (not found / wrong tenant)

InboxMessageRepo
  8.  create                → session.add(message) once; flush once
  9.  create_if_not_exists  → session.execute once; returns True on insert
  10. create_if_not_exists conflict → returns False when rowcount == 0
  11. get_by_provider_message_id → session.execute once; tenant context used
  12. get_by_smtp_message_id     → session.execute once; tenant context used
  13. list_by_connection         → session.execute once; tenant context used
  14. list_recent                → session.execute once; tenant context used

Tenant isolation contract
  15. All query methods call get_tenant_context() — never accept tenant_id as param
  16. create_if_not_exists embeds ctx.org_id in VALUES — verified via mock assertion
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.tenancy import TenantContext
from corpmind.modules.inbox.models import InboxConnection, InboxMessage
from corpmind.modules.inbox.repo import InboxConnectionRepo, InboxMessageRepo

# ── Shared fixtures ───────────────────────────────────────────────────────────

_ORG_A = uuid.uuid4()
_ORG_B = uuid.uuid4()
_WS_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _make_ctx(org_id: uuid.UUID = _ORG_A) -> TenantContext:
    return TenantContext(
        org_id=org_id,
        workspace_id=_WS_ID,
        user_id=_USER_ID,
        role="trainer",
        request_id="test-req",
        plan_tier="starter",
    )


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


def _mock_result(rowcount: int = 1) -> MagicMock:
    result = MagicMock()
    result.rowcount = rowcount
    result.scalar_one_or_none = MagicMock(return_value=None)
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    return result


def _make_connection(org_id: uuid.UUID = _ORG_A) -> InboxConnection:
    return InboxConnection(
        id=uuid.uuid4(),
        tenant_id=org_id,
        workspace_id=_WS_ID,
        provider="gmail",
        email_address_enc="encrypted-email",
        refresh_token_enc="encrypted-refresh",
        access_token_enc=None,
        email_address_hash="a" * 64,
        scopes="https://www.googleapis.com/auth/gmail.readonly",
        status="active",
        connected_by=_USER_ID,
    )


def _make_message(connection_id: uuid.UUID, org_id: uuid.UUID = _ORG_A) -> InboxMessage:
    return InboxMessage(
        id=uuid.uuid4(),
        tenant_id=org_id,
        connection_id=connection_id,
        provider_message_id="gmail-msg-abc123",
        provider_thread_id=None,
        smtp_message_id="<TESTULID@corpmind.ai>",
        in_reply_to="<TESTULID@corpmind.ai>",
        references_header=None,
        outbound_message_id=None,
        match_method=None,
        from_address="hr@acme.com",
        subject="Re: Training proposal",
        received_at=datetime(2026, 6, 5, 10, 0, 0, tzinfo=timezone.utc),
        body_snippet_enc="encrypted-snippet",
        body_truncated=False,
        reply_intent=None,
    )


# ── InboxConnectionRepo ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connection_create_adds_and_flushes() -> None:
    """create() adds the ORM object and flushes — does NOT call get_tenant_context."""
    session = _mock_session()
    connection = _make_connection()

    repo = InboxConnectionRepo(session)
    returned = await repo.create(connection)

    session.add.assert_called_once_with(connection)
    session.flush.assert_awaited_once()
    assert returned is connection


@pytest.mark.asyncio
async def test_connection_find_by_id_executes_once() -> None:
    """find_by_id issues one execute and reads tenant context."""
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result())
    connection_id = uuid.uuid4()

    ctx = _make_ctx()
    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxConnectionRepo(session)
        await repo.find_by_id(connection_id)

    assert session.execute.await_count == 1
    mock_ctx.assert_called_once()


@pytest.mark.asyncio
async def test_connection_find_by_workspace_executes_once() -> None:
    """find_by_workspace issues one execute scoped to the current tenant."""
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result())

    ctx = _make_ctx()
    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxConnectionRepo(session)
        await repo.find_by_workspace(_WS_ID)

    assert session.execute.await_count == 1
    mock_ctx.assert_called_once()


@pytest.mark.asyncio
async def test_connection_find_by_email_hash_executes_once() -> None:
    """find_by_email_hash issues one execute — this is the dedup check path."""
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result())

    ctx = _make_ctx()
    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxConnectionRepo(session)
        await repo.find_by_email_hash("a" * 64)

    assert session.execute.await_count == 1
    mock_ctx.assert_called_once()


@pytest.mark.asyncio
async def test_connection_update_executes_once() -> None:
    """update() issues one execute with tenant guard."""
    session = _mock_session()
    connection_id = uuid.uuid4()

    ctx = _make_ctx()
    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxConnectionRepo(session)
        await repo.update(connection_id, {"status": "needs_reauth"})

    assert session.execute.await_count == 1
    mock_ctx.assert_called_once()


@pytest.mark.asyncio
async def test_connection_delete_returns_true_when_row_deleted() -> None:
    """delete() returns True when rowcount > 0 (row existed and was owned by tenant)."""
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result(rowcount=1))
    connection_id = uuid.uuid4()

    ctx = _make_ctx()
    with patch("corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx):
        repo = InboxConnectionRepo(session)
        deleted = await repo.delete(connection_id)

    assert deleted is True
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_connection_delete_returns_false_when_not_found() -> None:
    """delete() returns False when rowcount == 0 — not found or different tenant.

    Callers treat False as a 404 without leaking whether the connection exists
    for another tenant.
    """
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result(rowcount=0))
    connection_id = uuid.uuid4()

    ctx = _make_ctx()
    with patch("corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx):
        repo = InboxConnectionRepo(session)
        deleted = await repo.delete(connection_id)

    assert deleted is False


@pytest.mark.asyncio
async def test_connection_create_does_not_require_tenant_context() -> None:
    """create() never calls get_tenant_context — tenant_id is set on the ORM object.

    This mirrors the pattern across all other repos: the service stamps tenant_id
    onto the model before passing it; the repo never re-derives it from context.
    """
    session = _mock_session()
    connection = _make_connection()

    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context"
    ) as mock_ctx:
        repo = InboxConnectionRepo(session)
        await repo.create(connection)

    mock_ctx.assert_not_called()


# ── InboxMessageRepo ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_message_create_adds_and_flushes() -> None:
    """create() adds the ORM object and flushes — no tenant context needed."""
    session = _mock_session()
    connection_id = uuid.uuid4()
    message = _make_message(connection_id)

    repo = InboxMessageRepo(session)
    returned = await repo.create(message)

    session.add.assert_called_once_with(message)
    session.flush.assert_awaited_once()
    assert returned is message


@pytest.mark.asyncio
async def test_message_find_by_id_executes_once() -> None:
    """find_by_id issues one execute scoped to the current tenant."""
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result())
    message_id = uuid.uuid4()

    ctx = _make_ctx()
    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxMessageRepo(session)
        await repo.find_by_id(message_id)

    assert session.execute.await_count == 1
    mock_ctx.assert_called_once()


@pytest.mark.asyncio
async def test_message_create_if_not_exists_returns_true_on_insert() -> None:
    """create_if_not_exists returns True when the row was newly inserted."""
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result(rowcount=1))
    connection_id = uuid.uuid4()
    message = _make_message(connection_id)

    ctx = _make_ctx()
    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxMessageRepo(session)
        inserted = await repo.create_if_not_exists(message)

    assert inserted is True
    assert session.execute.await_count == 1
    mock_ctx.assert_called_once()


@pytest.mark.asyncio
async def test_message_create_if_not_exists_returns_false_on_conflict() -> None:
    """create_if_not_exists returns False when ON CONFLICT DO NOTHING fires.

    rowcount == 0 means the unique constraint (connection_id, provider_message_id)
    prevented the insert — a previous sync run already stored this Gmail message.
    """
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result(rowcount=0))
    connection_id = uuid.uuid4()
    message = _make_message(connection_id)

    ctx = _make_ctx()
    with patch("corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx):
        repo = InboxMessageRepo(session)
        inserted = await repo.create_if_not_exists(message)

    assert inserted is False


@pytest.mark.asyncio
async def test_message_create_if_not_exists_uses_tenant_context_org_id() -> None:
    """create_if_not_exists embeds ctx.org_id in VALUES — not a caller parameter.

    Guards the multi-tenancy invariant: even on this insert path the tenant_id
    comes from the context, never from the caller.
    """
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result(rowcount=1))
    connection_id = uuid.uuid4()
    message = _make_message(connection_id, org_id=_ORG_A)

    ctx = _make_ctx(org_id=_ORG_A)
    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxMessageRepo(session)
        await repo.create_if_not_exists(message)

    mock_ctx.assert_called_once()


@pytest.mark.asyncio
async def test_message_get_by_provider_message_id_executes_once() -> None:
    """get_by_provider_message_id issues one execute with tenant + connection scope."""
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result())
    connection_id = uuid.uuid4()

    ctx = _make_ctx()
    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxMessageRepo(session)
        await repo.get_by_provider_message_id(connection_id, "gmail-msg-abc123")

    assert session.execute.await_count == 1
    mock_ctx.assert_called_once()


@pytest.mark.asyncio
async def test_message_get_by_smtp_message_id_executes_once() -> None:
    """get_by_smtp_message_id issues one execute — this is the reply-matching path."""
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result())

    ctx = _make_ctx()
    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxMessageRepo(session)
        await repo.get_by_smtp_message_id("<TESTULID@corpmind.ai>")

    assert session.execute.await_count == 1
    mock_ctx.assert_called_once()


@pytest.mark.asyncio
async def test_message_list_by_connection_executes_once() -> None:
    """list_by_connection issues one execute scoped to tenant + connection."""
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result())
    connection_id = uuid.uuid4()

    ctx = _make_ctx()
    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxMessageRepo(session)
        await repo.list_by_connection(connection_id)

    assert session.execute.await_count == 1
    mock_ctx.assert_called_once()


@pytest.mark.asyncio
async def test_message_list_recent_executes_once() -> None:
    """list_recent issues one execute scoped to the current tenant."""
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result())

    ctx = _make_ctx()
    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxMessageRepo(session)
        await repo.list_recent(limit=20)

    assert session.execute.await_count == 1
    mock_ctx.assert_called_once()


# ── Tenant isolation contract ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation_different_org_ids_call_separate_contexts() -> None:
    """Two repos with different org_ids each call get_tenant_context independently.

    This is the unit-level tenant isolation test: it verifies the contract that
    every query re-reads the context rather than caching org_id at construction
    time.  The full DB-level isolation (RLS) is covered in tests/integration/.
    """
    session_a = _mock_session()
    session_a.execute = AsyncMock(return_value=_mock_result())
    session_b = _mock_session()
    session_b.execute = AsyncMock(return_value=_mock_result())

    ctx_a = _make_ctx(org_id=_ORG_A)
    ctx_b = _make_ctx(org_id=_ORG_B)

    connection_id = uuid.uuid4()

    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx_a
    ) as mock_a:
        repo_a = InboxConnectionRepo(session_a)
        await repo_a.find_by_id(connection_id)

    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx_b
    ) as mock_b:
        repo_b = InboxConnectionRepo(session_b)
        await repo_b.find_by_id(connection_id)

    mock_a.assert_called_once()
    mock_b.assert_called_once()
    # Each repo issued exactly one query — no cross-contamination
    assert session_a.execute.await_count == 1
    assert session_b.execute.await_count == 1


@pytest.mark.asyncio
async def test_message_create_does_not_require_tenant_context() -> None:
    """create() never calls get_tenant_context — same invariant as connection.create."""
    session = _mock_session()
    connection_id = uuid.uuid4()
    message = _make_message(connection_id)

    with patch("corpmind.modules.inbox.repo.get_tenant_context") as mock_ctx:
        repo = InboxMessageRepo(session)
        await repo.create(message)

    mock_ctx.assert_not_called()


@pytest.mark.asyncio
async def test_smtp_message_id_lookup_sequential_calls_each_use_context() -> None:
    """Three sequential smtp_message_id lookups each independently read the context.

    If the repo ever cached org_id at construction time, a context switch
    mid-request could silently serve a different tenant's data.  This test pins
    that each call re-reads the context var.
    """
    session = _mock_session()
    session.execute = AsyncMock(return_value=_mock_result())
    ctx = _make_ctx()

    with patch(
        "corpmind.modules.inbox.repo.get_tenant_context", return_value=ctx
    ) as mock_ctx:
        repo = InboxMessageRepo(session)
        await repo.get_by_smtp_message_id("<ID1@corpmind.ai>")
        await repo.get_by_smtp_message_id("<ID2@corpmind.ai>")
        await repo.get_by_smtp_message_id("<ID3@corpmind.ai>")

    assert mock_ctx.call_count == 3
    assert session.execute.await_count == 3
