"""Billing module REST API."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.billing.schemas import BillingSummaryOut, SubscriptionOut, UsageSummary
from corpmind.modules.billing.service import BillingService

router = APIRouter()


@router.get(
    "/subscription",
    response_model=SubscriptionOut,
    summary="Active subscription — plan tier, limits, and billing period",
)
async def get_subscription(
    session: AsyncSession = Depends(get_session),
) -> SubscriptionOut:
    return await BillingService(session).get_subscription()


@router.get(
    "/usage",
    response_model=UsageSummary,
    summary="Current-period usage — spend, runs, and sends consumed",
)
async def get_usage(
    session: AsyncSession = Depends(get_session),
) -> UsageSummary:
    return await BillingService(session).get_usage()


@router.get(
    "/summary",
    response_model=BillingSummaryOut,
    summary="Subscription + usage combined — the dashboard billing widget",
)
async def get_summary(
    session: AsyncSession = Depends(get_session),
) -> BillingSummaryOut:
    return await BillingService(session).get_summary()
