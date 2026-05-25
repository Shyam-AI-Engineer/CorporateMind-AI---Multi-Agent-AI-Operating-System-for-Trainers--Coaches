"""Billing repository."""

from __future__ import annotations

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

    async def increment_ai_spend(self, subscription_id: object, amount_inr: float) -> None:
        from sqlalchemy import update
        await self._session.execute(
            update(UsageMeter)
            .where(UsageMeter.subscription_id == subscription_id)
            .values(
                ai_spend_inr=UsageMeter.ai_spend_inr + amount_inr,
                ai_runs_used=UsageMeter.ai_runs_used + 1,
            )
        )
