"""Billing repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.billing.models import Subscription, UsageMeter


class SubscriptionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_active(self) -> Subscription | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Subscription).where(
                Subscription.tenant_id == ctx.org_id,
                Subscription.status == "active",
            )
        )
        return result.scalar_one_or_none()


class UsageMeterRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_subscription(self, subscription_id: uuid.UUID) -> UsageMeter | None:
        result = await self._session.execute(
            select(UsageMeter).where(UsageMeter.subscription_id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def increment_ai_spend(self, subscription_id: uuid.UUID, amount_inr: float) -> None:
        """Upsert the UsageMeter row for the given subscription.

        INSERT on first call (brand-new tenant), UPDATE on every subsequent call.
        Uses ON CONFLICT on the named unique constraint so the operation is
        atomic — no race condition between concurrent LLM calls for the same tenant.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        ctx = get_tenant_context()
        stmt = (
            pg_insert(UsageMeter)
            .values(
                id=uuid.uuid4(),
                subscription_id=subscription_id,
                tenant_id=ctx.org_id,
                ai_spend_inr=amount_inr,
                ai_runs_used=1,
                outreach_sends_used=0,
            )
            .on_conflict_do_update(
                constraint="uq_usage_meters_subscription_id",
                set_={
                    "ai_spend_inr": UsageMeter.ai_spend_inr + amount_inr,
                    "ai_runs_used": UsageMeter.ai_runs_used + 1,
                },
            )
        )
        await self._session.execute(stmt)

    async def increment_outreach_sends(self, subscription_id: uuid.UUID) -> None:
        """Increment the outreach send counter by 1 for the given subscription.

        Same upsert pattern as increment_ai_spend — atomic, idempotency-safe.
        Called by the Celery send task after a successful channel dispatch.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        ctx = get_tenant_context()
        stmt = (
            pg_insert(UsageMeter)
            .values(
                id=uuid.uuid4(),
                subscription_id=subscription_id,
                tenant_id=ctx.org_id,
                ai_spend_inr=0.0,
                ai_runs_used=0,
                outreach_sends_used=1,
            )
            .on_conflict_do_update(
                constraint="uq_usage_meters_subscription_id",
                set_={
                    "outreach_sends_used": UsageMeter.outreach_sends_used + 1,
                },
            )
        )
        await self._session.execute(stmt)
