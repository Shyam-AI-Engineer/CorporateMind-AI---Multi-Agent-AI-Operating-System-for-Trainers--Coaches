"""Billing schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    plan_tier: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    ai_run_limit: int
    outreach_send_limit: int
    ai_budget_inr: float
    model_config = {"from_attributes": True}


class UsageSummary(BaseModel):
    ai_runs_used: int
    ai_runs_limit: int
    outreach_sends_used: int
    outreach_sends_limit: int
    ai_spend_inr: float
    ai_budget_inr: float
    budget_utilization_pct: float


class BillingSummaryOut(BaseModel):
    subscription: SubscriptionOut
    usage: UsageSummary
