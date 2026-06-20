"""Analytics schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, computed_field


class DailyRollupOut(BaseModel):
    rollup_date: date
    channel: str | None
    outreach_sent: int
    outreach_delivered: int
    outreach_opened: int
    outreach_replied: int
    compliance_blocks: int
    meetings_scheduled: int
    meetings_completed: int
    leads_created: int
    leads_booked: int
    proposals_generated: int
    proposals_approved: int
    proposals_sent: int
    ai_spend_inr: float
    model_config = {"from_attributes": True}


class AnalyticsSummary(BaseModel):
    period_days: int
    total_sent: int
    total_delivered: int
    total_replied: int
    reply_rate: float        # 0.0-1.0
    delivery_rate: float     # 0.0-1.0
    total_spend_inr: float
    meetings_scheduled: int
    meetings_completed: int
    leads_created: int
    leads_booked: int
    proposals_generated: int
    proposals_approved: int
    proposals_sent: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def proposal_approval_rate(self) -> float:
        if self.proposals_generated == 0:
            return 0.0
        return round(self.proposals_approved / self.proposals_generated, 4)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def booking_rate(self) -> float:
        """Ratio of booked leads to total proposals sent — the headline conversion."""
        if self.proposals_sent == 0:
            return 0.0
        return round(self.leads_booked / self.proposals_sent, 4)


class AnalyticsTrendOut(BaseModel):
    """One day in a trend series — used by GET /analytics/trend."""

    rollup_date: date
    outreach_sent: int
    outreach_replied: int
    leads_created: int
    leads_booked: int
    proposals_sent: int
    ai_spend_inr: float
    model_config = {"from_attributes": True}


class AnalyticsFunnelOut(BaseModel):
    """Trainer revenue funnel — live counts from transactional tables."""

    contacts: int
    outreach_sent: int
    replies: int
    meetings: int
    proposals: int
    bookings: int


class AnalyticsChannelSummary(BaseModel):
    """Per-channel outreach performance summary.

    sent / delivered / opened roll up from analytics_daily (channel-specific rows).
    failed is computed live from outbound_messages because analytics_daily has
    no outreach_failed column — same pattern as get_funnel().
    delivery_rate and read_rate are computed fields clamped to [0.0, 1.0].
    """

    channel: str
    period_days: int
    sent: int
    delivered: int
    opened: int
    failed: int
    compliance_blocks: int
    delivery_rate: float   # delivered / sent
    read_rate: float       # opened / delivered
