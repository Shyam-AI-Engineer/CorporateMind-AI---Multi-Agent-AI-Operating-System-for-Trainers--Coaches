"""Billing service — tenant provisioning and subscription lifecycle."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError
from corpmind.modules.billing.models import Subscription, UsageMeter
from corpmind.modules.billing.repo import SubscriptionRepo, UsageMeterRepo
from corpmind.modules.billing.schemas import BillingSummaryOut, SubscriptionOut, UsageSummary

log = structlog.get_logger(__name__)

_STARTER_BUDGET_INR = 400.0
_STARTER_AI_RUNS = 1000
_STARTER_SENDS = 500
_PERIOD_DAYS = 30


class BillingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def provision_new_tenant(self, org_id: uuid.UUID) -> None:
        """Create the initial Subscription + UsageMeter for a freshly registered org.

        Both rows are added to the caller's session and flushed (but not
        committed) so that foreign-key lookups within the same transaction
        can reference subscription.id immediately.

        Caller contract: set_rls_tenant(session, org_id) MUST be called before
        this method so that the RLS WITH CHECK policy accepts the INSERTs.
        """
        now = datetime.now(timezone.utc)
        subscription = Subscription(
            tenant_id=org_id,
            plan_tier="starter",
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=_PERIOD_DAYS),
            ai_run_limit=_STARTER_AI_RUNS,
            outreach_send_limit=_STARTER_SENDS,
            ai_budget_inr=_STARTER_BUDGET_INR,
        )
        self._session.add(subscription)
        await self._session.flush()

        meter = UsageMeter(
            tenant_id=org_id,
            subscription_id=subscription.id,
            ai_runs_used=0,
            outreach_sends_used=0,
            ai_spend_inr=0.0,
        )
        self._session.add(meter)
        await self._session.flush()

        log.info(
            "billing.tenant_provisioned",
            org_id=str(org_id),
            subscription_id=str(subscription.id),
            budget_inr=_STARTER_BUDGET_INR,
        )

    async def get_subscription(self) -> SubscriptionOut:
        sub = await SubscriptionRepo(self._session).find_active()
        if sub is None:
            raise NotFoundError("No active subscription found for this tenant")
        return SubscriptionOut.model_validate(sub)

    async def get_usage(self) -> UsageSummary:
        sub = await SubscriptionRepo(self._session).find_active()
        if sub is None:
            raise NotFoundError("No active subscription found for this tenant")
        meter = await UsageMeterRepo(self._session).find_by_subscription(sub.id)
        return _build_usage_summary(sub, meter)

    async def get_summary(self) -> BillingSummaryOut:
        sub = await SubscriptionRepo(self._session).find_active()
        if sub is None:
            raise NotFoundError("No active subscription found for this tenant")
        meter = await UsageMeterRepo(self._session).find_by_subscription(sub.id)
        return BillingSummaryOut(
            subscription=SubscriptionOut.model_validate(sub),
            usage=_build_usage_summary(sub, meter),
        )


def _build_usage_summary(sub: Subscription, meter: UsageMeter | None) -> UsageSummary:
    spent = meter.ai_spend_inr if meter else 0.0
    pct = round(spent / sub.ai_budget_inr * 100, 2) if sub.ai_budget_inr > 0 else 0.0
    return UsageSummary(
        ai_runs_used=meter.ai_runs_used if meter else 0,
        ai_runs_limit=sub.ai_run_limit,
        outreach_sends_used=meter.outreach_sends_used if meter else 0,
        outreach_sends_limit=sub.outreach_send_limit,
        ai_spend_inr=spent,
        ai_budget_inr=sub.ai_budget_inr,
        budget_utilization_pct=pct,
    )
