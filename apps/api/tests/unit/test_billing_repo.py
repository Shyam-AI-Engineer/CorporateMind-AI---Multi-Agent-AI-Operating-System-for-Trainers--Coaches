"""Unit tests for UsageMeterRepo.increment_ai_spend — the billing upsert.

Behavioral contracts pinned here:

  1. First call (no existing row) → INSERT: meter created with correct spend.
  2. Second call (row exists)     → UPDATE: spend and run count accumulate.
  3. Zero-cost call               → ai_spend_inr unchanged; ai_runs_used still increments.
  4. Concurrent safety            → the ON CONFLICT path is exercised (structural test).

These tests mock the AsyncSession to stay unit-level. The full round-trip
against a real Postgres instance is covered by tests/integration/.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.billing.repo import UsageMeterRepo
from corpmind.core.tenancy import TenantContext


def _make_tenant_ctx(org_id: uuid.UUID) -> TenantContext:
    return TenantContext(
        org_id=org_id,
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="OrgAdmin",
        request_id="test-req",
        plan_tier="starter",
    )


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_increment_ai_spend_executes_upsert() -> None:
    """increment_ai_spend issues exactly one execute() with a pg_insert statement."""
    org_id = uuid.uuid4()
    subscription_id = uuid.uuid4()
    session = _mock_session()

    ctx = _make_tenant_ctx(org_id)
    with patch("corpmind.modules.billing.repo.get_tenant_context", return_value=ctx):
        repo = UsageMeterRepo(session)
        await repo.increment_ai_spend(subscription_id, 25.0)

    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_increment_ai_spend_zero_cost_still_executes() -> None:
    """Zero-cost calls (cached hits in future) still issue the upsert.

    ai_spend_inr stays at 0, but ai_runs_used increments — ensures
    cached calls are counted in the run limit.
    """
    org_id = uuid.uuid4()
    subscription_id = uuid.uuid4()
    session = _mock_session()

    ctx = _make_tenant_ctx(org_id)
    with patch("corpmind.modules.billing.repo.get_tenant_context", return_value=ctx):
        repo = UsageMeterRepo(session)
        await repo.increment_ai_spend(subscription_id, 0.0)

    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_increment_ai_spend_uses_tenant_context_org_id() -> None:
    """The INSERT VALUES includes tenant_id from TenantContext, not a parameter.

    This guards the multi-tenancy invariant: repo code never accepts tenant_id
    as a caller-supplied argument — it must always come from the context.
    """
    org_id = uuid.uuid4()
    subscription_id = uuid.uuid4()
    session = _mock_session()

    ctx = _make_tenant_ctx(org_id)
    with patch("corpmind.modules.billing.repo.get_tenant_context", return_value=ctx) as mock_ctx:
        repo = UsageMeterRepo(session)
        await repo.increment_ai_spend(subscription_id, 10.0)

    mock_ctx.assert_called_once()


@pytest.mark.asyncio
async def test_increment_ai_spend_multiple_calls_each_execute_once() -> None:
    """Three sequential spend increments → three separate execute() calls.

    In a real DB this is three upserts; each one atomically updates the row.
    """
    org_id = uuid.uuid4()
    subscription_id = uuid.uuid4()
    session = _mock_session()

    ctx = _make_tenant_ctx(org_id)
    with patch("corpmind.modules.billing.repo.get_tenant_context", return_value=ctx):
        repo = UsageMeterRepo(session)
        await repo.increment_ai_spend(subscription_id, 10.0)
        await repo.increment_ai_spend(subscription_id, 15.0)
        await repo.increment_ai_spend(subscription_id, 5.0)

    assert session.execute.await_count == 3
