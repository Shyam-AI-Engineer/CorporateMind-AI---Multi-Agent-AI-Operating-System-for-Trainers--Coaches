"""Analytics schemas."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel


class DailyRollupOut(BaseModel):
    rollup_date: date
    channel: str | None
    outreach_sent: int
    outreach_delivered: int
    outreach_opened: int
    outreach_replied: int
    compliance_blocks: int
    meetings_scheduled: int
    ai_spend_inr: float
    model_config = {"from_attributes": True}


class AnalyticsSummary(BaseModel):
    period_days: int
    total_sent: int
    reply_rate: float
    delivery_rate: float
    total_spend_inr: float
    meetings_booked: int
