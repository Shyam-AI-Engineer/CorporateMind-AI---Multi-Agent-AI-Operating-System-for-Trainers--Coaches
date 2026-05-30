"""Unit tests for BillingService read methods.

Behavioral contracts:
  1. get_subscription() returns SubscriptionOut from active subscription row.
  2. get_subscription() raises NotFoundError when no active subscription exists.
  3. get_usage() computes budget_utilization_pct correctly (spent / budget * 100).
  4. get_usage() returns zero-usage when meter row is absent (edge case: new tenant mid-provisioning).
  5. get_usage() handles zero-budget subscription without division-by-zero.
  6. get_summary() returns both subscription and usage in one response.
  7. get_summary() raises NotFoundError when no active subscription exists.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import NotFoundError
from corpmind.modules.billing.models import Subscription, UsageMeter
from corpmind.modules.billing.service import BillingService


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    return session


def _make_subscription(**overrides) -> Subscription:
    now = datetime.now(timezone.utc)
    sub = Subscription()
    sub.id = uuid.uuid4()
    sub.tenant_id = uuid.uuid4()
    sub.plan_tier = "starter"
    sub.status = "active"
    sub.current_period_start = now
    sub.current_period_end = now + timedelta(days=30)
    sub.ai_run_limit = 1000
    sub.outreach_send_limit = 500
    sub.ai_budget_inr = 400.0
    for k, v in overrides.items():
        setattr(sub, k, v)
    return sub


def _make_meter(subscription_id: uuid.UUID, **overrides) -> UsageMeter:
    meter = UsageMeter()
    meter.id = uuid.uuid4()
    meter.subscription_id = subscription_id
    meter.ai_runs_used = 10
    meter.outreach_sends_used = 5
    meter.ai_spend_inr = 50.0
    for k, v in overrides.items():
        setattr(meter, k, v)
    return meter


# ── get_subscription ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_subscription_returns_correct_fields() -> None:
    sub = _make_subscription()
    session = _mock_session()

    with patch("corpmind.modules.billing.service.SubscriptionRepo") as MockRepo:
        MockRepo.return_value.find_active = AsyncMock(return_value=sub)
        result = await BillingService(session).get_subscription()

    assert result.id == sub.id
    assert result.plan_tier == "starter"
    assert result.status == "active"
    assert result.ai_budget_inr == 400.0
    assert result.ai_run_limit == 1000
    assert result.outreach_send_limit == 500
    assert result.current_period_start == sub.current_period_start
    assert result.current_period_end == sub.current_period_end


@pytest.mark.asyncio
async def test_get_subscription_raises_not_found_when_no_subscription() -> None:
    session = _mock_session()

    with patch("corpmind.modules.billing.service.SubscriptionRepo") as MockRepo:
        MockRepo.return_value.find_active = AsyncMock(return_value=None)
        with pytest.raises(NotFoundError):
            await BillingService(session).get_subscription()


# ── get_usage ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_usage_computes_budget_utilization_pct() -> None:
    sub = _make_subscription(ai_budget_inr=400.0)
    meter = _make_meter(sub.id, ai_spend_inr=100.0)
    session = _mock_session()

    with patch("corpmind.modules.billing.service.SubscriptionRepo") as MockSub, \
         patch("corpmind.modules.billing.service.UsageMeterRepo") as MockMeter:
        MockSub.return_value.find_active = AsyncMock(return_value=sub)
        MockMeter.return_value.find_by_subscription = AsyncMock(return_value=meter)
        result = await BillingService(session).get_usage()

    assert result.ai_spend_inr == 100.0
    assert result.ai_budget_inr == 400.0
    assert result.budget_utilization_pct == pytest.approx(25.0)
    assert result.ai_runs_used == meter.ai_runs_used
    assert result.ai_runs_limit == 1000
    assert result.outreach_sends_used == meter.outreach_sends_used
    assert result.outreach_sends_limit == 500


@pytest.mark.asyncio
async def test_get_usage_returns_zeros_when_meter_absent() -> None:
    """Edge case: subscription exists but meter not yet written (mid-provisioning)."""
    sub = _make_subscription()
    session = _mock_session()

    with patch("corpmind.modules.billing.service.SubscriptionRepo") as MockSub, \
         patch("corpmind.modules.billing.service.UsageMeterRepo") as MockMeter:
        MockSub.return_value.find_active = AsyncMock(return_value=sub)
        MockMeter.return_value.find_by_subscription = AsyncMock(return_value=None)
        result = await BillingService(session).get_usage()

    assert result.ai_spend_inr == 0.0
    assert result.ai_runs_used == 0
    assert result.outreach_sends_used == 0
    assert result.budget_utilization_pct == 0.0


@pytest.mark.asyncio
async def test_get_usage_zero_budget_no_division_error() -> None:
    sub = _make_subscription(ai_budget_inr=0.0)
    meter = _make_meter(sub.id, ai_spend_inr=0.0)
    session = _mock_session()

    with patch("corpmind.modules.billing.service.SubscriptionRepo") as MockSub, \
         patch("corpmind.modules.billing.service.UsageMeterRepo") as MockMeter:
        MockSub.return_value.find_active = AsyncMock(return_value=sub)
        MockMeter.return_value.find_by_subscription = AsyncMock(return_value=meter)
        result = await BillingService(session).get_usage()

    assert result.budget_utilization_pct == 0.0


# ── get_summary ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_summary_returns_subscription_and_usage() -> None:
    sub = _make_subscription()
    meter = _make_meter(sub.id, ai_spend_inr=80.0)
    session = _mock_session()

    with patch("corpmind.modules.billing.service.SubscriptionRepo") as MockSub, \
         patch("corpmind.modules.billing.service.UsageMeterRepo") as MockMeter:
        MockSub.return_value.find_active = AsyncMock(return_value=sub)
        MockMeter.return_value.find_by_subscription = AsyncMock(return_value=meter)
        result = await BillingService(session).get_summary()

    assert result.subscription.id == sub.id
    assert result.usage.ai_spend_inr == 80.0
    assert result.usage.budget_utilization_pct == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_get_summary_raises_not_found_when_no_subscription() -> None:
    session = _mock_session()

    with patch("corpmind.modules.billing.service.SubscriptionRepo") as MockRepo:
        MockRepo.return_value.find_active = AsyncMock(return_value=None)
        with pytest.raises(NotFoundError):
            await BillingService(session).get_summary()
