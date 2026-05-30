"""Unit tests for EuriClient._check_budget — the AI budget guard.

The budget guard runs *before* every LLM call. These tests pin its four
behavioral contracts:

  1. No session bound          → permissive no-op (agent scaffolding path).
  2. No active subscription    → permissive no-op + WARN log.
  3. Spend below budget        → call proceeds (no raise).
  4. Spend at or above budget  → BudgetExceededError (boundary is >=).

We mock the AsyncSession to keep this a true unit test — the DB-backed
behavior is covered by repo tests once the budget guard is integrated.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from corpmind.ai.euri_client import EuriClient
from corpmind.core.exceptions import BudgetExceededError


def _mock_session(subscription, meter):
    """Build an AsyncSession stub that returns subscription, then meter."""
    sub_result = MagicMock()
    sub_result.scalar_one_or_none.return_value = subscription

    meter_result = MagicMock()
    meter_result.scalar_one_or_none.return_value = meter

    session = MagicMock()
    session.execute = AsyncMock(side_effect=[sub_result, meter_result])
    return session


@pytest.mark.asyncio
async def test_no_session_skips_check():
    """Sessionless EuriClient (agent scaffolding) must not raise or query."""
    client = EuriClient(session=None)
    # No exception means the path is permissive — exactly what we want
    # until agents are wired into request-scoped sessions.
    await client._check_budget(uuid.uuid4(), "outreach_copy")


@pytest.mark.asyncio
async def test_no_active_subscription_skips_check():
    """Sandbox/seed tenants without a Subscription row are not blocked."""
    session = MagicMock()
    sub_result = MagicMock()
    sub_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=sub_result)

    client = EuriClient(session=session)
    await client._check_budget(uuid.uuid4(), "outreach_copy")

    # Exactly one query (subscription); no meter lookup attempted.
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_under_budget_allows_call():
    """spent (50) < budget (400) → no raise."""
    subscription = SimpleNamespace(id=uuid.uuid4(), ai_budget_inr=400.0)
    meter = SimpleNamespace(ai_spend_inr=50.0)
    session = _mock_session(subscription, meter)

    client = EuriClient(session=session)
    await client._check_budget(uuid.uuid4(), "outreach_copy")


@pytest.mark.asyncio
async def test_at_budget_boundary_blocks():
    """spent (400) == budget (400) → BudgetExceededError.

    The boundary is strict >= because the *next* call must be denied as
    soon as the ceiling is reached. Trainers should never overshoot.
    """
    subscription = SimpleNamespace(id=uuid.uuid4(), ai_budget_inr=400.0)
    meter = SimpleNamespace(ai_spend_inr=400.0)
    session = _mock_session(subscription, meter)

    client = EuriClient(session=session)
    with pytest.raises(BudgetExceededError) as exc_info:
        await client._check_budget(uuid.uuid4(), "outreach_copy")

    assert exc_info.value.http_status == 402
    assert exc_info.value.code == "budget_exceeded"
    assert "400" in exc_info.value.message


@pytest.mark.asyncio
async def test_over_budget_blocks():
    """spent (450) > budget (400) → BudgetExceededError."""
    subscription = SimpleNamespace(id=uuid.uuid4(), ai_budget_inr=400.0)
    meter = SimpleNamespace(ai_spend_inr=450.0)
    session = _mock_session(subscription, meter)

    client = EuriClient(session=session)
    with pytest.raises(BudgetExceededError):
        await client._check_budget(uuid.uuid4(), "outreach_copy")


@pytest.mark.asyncio
async def test_subscription_without_meter_treats_spend_as_zero():
    """Brand-new tenant: Subscription exists, UsageMeter row not yet inserted.

    Spend defaults to 0.0 so the first call is never falsely blocked.
    """
    subscription = SimpleNamespace(id=uuid.uuid4(), ai_budget_inr=400.0)
    session = _mock_session(subscription, meter=None)

    client = EuriClient(session=session)
    await client._check_budget(uuid.uuid4(), "outreach_copy")


@pytest.mark.asyncio
async def test_zero_budget_blocks_everything():
    """Edge case: subscription with budget=0 (suspended tenant) blocks immediately."""
    subscription = SimpleNamespace(id=uuid.uuid4(), ai_budget_inr=0.0)
    meter = SimpleNamespace(ai_spend_inr=0.0)
    session = _mock_session(subscription, meter)

    client = EuriClient(session=session)
    with pytest.raises(BudgetExceededError):
        await client._check_budget(uuid.uuid4(), "outreach_copy")
