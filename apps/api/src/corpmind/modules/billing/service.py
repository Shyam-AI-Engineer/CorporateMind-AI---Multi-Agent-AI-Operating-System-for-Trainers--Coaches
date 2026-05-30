"""Billing service — tenant provisioning and subscription lifecycle."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.billing.models import Subscription, UsageMeter

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
