"""Integration tests for the full AI spend persistence path.

Tests the complete chain:
  provision_new_tenant() → _record_usage() → UsageMeter updated → _check_budget() sees balance

These run against a real Postgres testcontainer (via the shared db_session
fixture in tests/conftest.py).  They verify the three bugs fixed in P1-1:

  Bug A: _record_usage() never called increment_ai_spend().
  Bug B: register() never created a Subscription or UsageMeter.
  Bug C: increment_ai_spend() was UPDATE-only, silent no-op on missing row.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy import text

from corpmind.ai.euri_client import EuriClient
from corpmind.core.database import set_rls_tenant
from corpmind.core.exceptions import BudgetExceededError
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.billing.models import Subscription, UsageMeter
from corpmind.modules.billing.service import BillingService


def _make_ctx(org_id: uuid.UUID) -> TenantContext:
    return TenantContext(
        org_id=org_id,
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="OrgAdmin",
        request_id="integ-test",
        plan_tier="starter",
    )


@pytest.mark.asyncio
async def test_provision_creates_subscription_and_meter(db_session) -> None:
    """provision_new_tenant() writes both a Subscription row and a zeroed UsageMeter."""
    org_id = uuid.uuid4()
    await set_rls_tenant(db_session, org_id)

    billing = BillingService(db_session)
    await billing.provision_new_tenant(org_id)

    sub_row = await db_session.execute(
        select(Subscription).where(Subscription.tenant_id == org_id)
    )
    sub = sub_row.scalar_one_or_none()
    assert sub is not None, "Subscription row must exist after provisioning"
    assert sub.status == "active"
    assert sub.ai_budget_inr == pytest.approx(400.0)

    meter_row = await db_session.execute(
        select(UsageMeter).where(UsageMeter.subscription_id == sub.id)
    )
    meter = meter_row.scalar_one_or_none()
    assert meter is not None, "UsageMeter row must exist after provisioning"
    assert meter.ai_spend_inr == pytest.approx(0.0)
    assert meter.ai_runs_used == 0


@pytest.mark.asyncio
async def test_record_usage_increments_meter(db_session, tenant_a) -> None:
    """_record_usage() updates UsageMeter.ai_spend_inr and ai_runs_used."""
    org_id = tenant_a.org_id
    token = set_tenant_context(tenant_a)
    await set_rls_tenant(db_session, org_id)

    try:
        # Provision billing rows
        await BillingService(db_session).provision_new_tenant(org_id)

        client = EuriClient(session=db_session)
        await client._record_usage(
            tenant_id=org_id,
            task="outreach_copy",
            prompt_name="outreach.email.v1",
            prompt_version="v1",
            model="deepseek-chat",
            tokens_in=100,
            tokens_out=200,
            cost_inr=25.0,
            cached=False,
            latency_ms=500,
            request_id="integ-req-001",
            agent=None,
            run_id=None,
        )
        await db_session.flush()

        sub_row = await db_session.execute(
            select(Subscription).where(Subscription.tenant_id == org_id)
        )
        sub = sub_row.scalar_one()

        meter_row = await db_session.execute(
            select(UsageMeter).where(UsageMeter.subscription_id == sub.id)
        )
        meter = meter_row.scalar_one()

        assert meter.ai_spend_inr == pytest.approx(25.0), "Spend must be recorded in meter"
        assert meter.ai_runs_used == 1, "Run count must increment"
    finally:
        clear_tenant_context(token)


@pytest.mark.asyncio
async def test_record_usage_accumulates_across_calls(db_session, tenant_a) -> None:
    """Multiple _record_usage() calls accumulate correctly."""
    org_id = tenant_a.org_id
    token = set_tenant_context(tenant_a)
    await set_rls_tenant(db_session, org_id)

    try:
        await BillingService(db_session).provision_new_tenant(org_id)
        client = EuriClient(session=db_session)

        for cost in [10.0, 15.0, 5.0]:
            await client._record_usage(
                tenant_id=org_id,
                task="outreach_copy",
                prompt_name="outreach.email.v1",
                prompt_version="v1",
                model="deepseek-chat",
                tokens_in=50,
                tokens_out=100,
                cost_inr=cost,
                cached=False,
                latency_ms=300,
                request_id=f"integ-req-{cost}",
                agent=None,
                run_id=None,
            )

        await db_session.flush()

        sub = (await db_session.execute(
            select(Subscription).where(Subscription.tenant_id == org_id)
        )).scalar_one()
        meter = (await db_session.execute(
            select(UsageMeter).where(UsageMeter.subscription_id == sub.id)
        )).scalar_one()

        assert meter.ai_spend_inr == pytest.approx(30.0), "10 + 15 + 5 = 30"
        assert meter.ai_runs_used == 3
    finally:
        clear_tenant_context(token)


@pytest.mark.asyncio
async def test_check_budget_sees_recorded_spend(db_session, tenant_a) -> None:
    """_check_budget() reads the updated meter — budget enforcement is end-to-end live."""
    org_id = tenant_a.org_id
    token = set_tenant_context(tenant_a)
    await set_rls_tenant(db_session, org_id)

    try:
        # Provision with a tight ₹30 budget so we can test the boundary cheaply
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        sub = Subscription(
            tenant_id=org_id,
            plan_tier="starter",
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            ai_run_limit=100,
            outreach_send_limit=100,
            ai_budget_inr=30.0,
        )
        db_session.add(sub)
        await db_session.flush()
        meter = UsageMeter(
            tenant_id=org_id,
            subscription_id=sub.id,
            ai_runs_used=0,
            outreach_sends_used=0,
            ai_spend_inr=0.0,
        )
        db_session.add(meter)
        await db_session.flush()

        client = EuriClient(session=db_session)

        # First call: 25 of 30 spent — must NOT raise
        await client._record_usage(
            tenant_id=org_id,
            task="outreach_copy",
            prompt_name="outreach.email.v1",
            prompt_version="v1",
            model="deepseek-chat",
            tokens_in=100,
            tokens_out=200,
            cost_inr=25.0,
            cached=False,
            latency_ms=400,
            request_id="budget-test-1",
            agent=None,
            run_id=None,
        )
        await db_session.flush()

        # Budget check: 25 < 30 → passes
        await client._check_budget(org_id, "outreach_copy")

        # Second call: pushes total to 30 — at-boundary must raise
        await client._record_usage(
            tenant_id=org_id,
            task="outreach_copy",
            prompt_name="outreach.email.v1",
            prompt_version="v1",
            model="deepseek-chat",
            tokens_in=50,
            tokens_out=50,
            cost_inr=5.0,
            cached=False,
            latency_ms=200,
            request_id="budget-test-2",
            agent=None,
            run_id=None,
        )
        await db_session.flush()

        # Budget check: 30 >= 30 → BudgetExceededError
        with pytest.raises(BudgetExceededError) as exc_info:
            await client._check_budget(org_id, "outreach_copy")

        assert exc_info.value.http_status == 402
        assert "30" in exc_info.value.message
    finally:
        clear_tenant_context(token)


@pytest.mark.asyncio
async def test_record_usage_without_subscription_is_noop(db_session, tenant_a) -> None:
    """_record_usage() with no subscription row is a silent no-op on the meter.

    Sandbox tenants without a subscription still get a ModelRun audit record,
    but the meter is not touched (no subscription to look up).
    """
    org_id = tenant_a.org_id
    token = set_tenant_context(tenant_a)
    await set_rls_tenant(db_session, org_id)

    try:
        client = EuriClient(session=db_session)
        # No subscription provisioned — must not raise
        await client._record_usage(
            tenant_id=org_id,
            task="outreach_copy",
            prompt_name="outreach.email.v1",
            prompt_version="v1",
            model="deepseek-chat",
            tokens_in=50,
            tokens_out=100,
            cost_inr=10.0,
            cached=False,
            latency_ms=300,
            request_id="no-sub-test",
            agent=None,
            run_id=None,
        )
        await db_session.flush()

        # No UsageMeter row should exist (nothing to update)
        rows = await db_session.execute(
            select(UsageMeter).where(UsageMeter.tenant_id == org_id)
        )
        assert rows.first() is None, "No meter row should exist without a subscription"
    finally:
        clear_tenant_context(token)
