"""Unit tests for AnalyticsService — mocked repo + session, no DB.

Covers:
  get_summary()
    - empty analytics_daily (no rows) → all zeros, no division errors
    - aggregates across multiple rows correctly
    - computed fields: reply_rate, delivery_rate, proposal_approval_rate, booking_rate
    - respects the requested period_days value

  get_trend()
    - empty → empty list
    - filters out per-channel rows, returns only channel=None aggregate rows
    - maps fields correctly to AnalyticsTrendOut

  get_funnel()
    - all-zero workspace (empty tables) → zeros, no errors
    - correctly maps SQL scalar results to AnalyticsFunnelOut fields
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.models import AnalyticsDaily
from corpmind.modules.analytics.service import AnalyticsService


TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = TENANT_ID
    return ctx


def _row(
    *,
    rollup_date: date | None = None,
    channel: str | None = None,
    outreach_sent: int = 0,
    outreach_delivered: int = 0,
    outreach_opened: int = 0,
    outreach_replied: int = 0,
    compliance_blocks: int = 0,
    meetings_scheduled: int = 0,
    meetings_completed: int = 0,
    leads_created: int = 0,
    leads_booked: int = 0,
    proposals_generated: int = 0,
    proposals_approved: int = 0,
    proposals_sent: int = 0,
    ai_spend_inr: float = 0.0,
    proposals_accepted: int = 0,
    closed_revenue_inr: float = 0.0,
) -> AnalyticsDaily:
    r = MagicMock(spec=AnalyticsDaily)
    r.rollup_date = rollup_date or date.today()
    r.channel = channel
    r.outreach_sent = outreach_sent
    r.outreach_delivered = outreach_delivered
    r.outreach_opened = outreach_opened
    r.outreach_replied = outreach_replied
    r.compliance_blocks = compliance_blocks
    r.meetings_scheduled = meetings_scheduled
    r.meetings_completed = meetings_completed
    r.leads_created = leads_created
    r.leads_booked = leads_booked
    r.proposals_generated = proposals_generated
    r.proposals_approved = proposals_approved
    r.proposals_sent = proposals_sent
    r.ai_spend_inr = ai_spend_inr
    r.proposals_accepted = proposals_accepted
    r.closed_revenue_inr = closed_revenue_inr
    return r


def _make_service(repo_rows: list[AnalyticsDaily]) -> AnalyticsService:
    session = MagicMock()
    svc = AnalyticsService(session)
    svc._session = session

    mock_repo = MagicMock()
    mock_repo.list_by_date_range = AsyncMock(return_value=repo_rows)

    with patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo):
        svc._mock_repo = mock_repo

    return svc, mock_repo


# ── get_summary ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summary_empty_returns_zeros():
    svc, mock_repo = _make_service([])
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_summary(days=30)

    assert result.total_sent == 0
    assert result.total_replied == 0
    assert result.reply_rate == 0.0
    assert result.delivery_rate == 0.0
    assert result.period_days == 30


@pytest.mark.asyncio
async def test_summary_aggregates_correctly():
    rows = [
        _row(outreach_sent=100, outreach_delivered=90, outreach_replied=20,
             leads_created=5, leads_booked=2, proposals_generated=3,
             proposals_approved=2, proposals_sent=1, ai_spend_inr=10.0),
        _row(outreach_sent=50, outreach_delivered=45, outreach_replied=10,
             leads_created=3, leads_booked=1, ai_spend_inr=5.0),
    ]
    svc, mock_repo = _make_service(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_summary(days=30)

    assert result.total_sent == 150
    assert result.total_delivered == 135
    assert result.total_replied == 30
    assert result.leads_created == 8
    assert result.leads_booked == 3
    assert result.total_spend_inr == 15.0


@pytest.mark.asyncio
async def test_summary_reply_rate_computed():
    rows = [_row(outreach_sent=200, outreach_replied=50)]
    svc, mock_repo = _make_service(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_summary()

    assert result.reply_rate == pytest.approx(0.25)
    assert result.delivery_rate == 0.0  # no delivered count


@pytest.mark.asyncio
async def test_summary_computed_proposal_approval_rate():
    rows = [_row(proposals_generated=4, proposals_approved=3, proposals_sent=2, leads_booked=1)]
    svc, mock_repo = _make_service(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_summary()

    assert result.proposal_approval_rate == pytest.approx(0.75)
    assert result.booking_rate == pytest.approx(0.5)  # 1 booked / 2 sent


# ── get_trend ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trend_empty_returns_empty_list():
    svc, mock_repo = _make_service([])
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_trend(days=30)

    assert result == []


@pytest.mark.asyncio
async def test_trend_filters_out_per_channel_rows():
    today = date.today()
    rows = [
        _row(rollup_date=today, channel=None, outreach_sent=100),
        _row(rollup_date=today, channel="email", outreach_sent=80),
        _row(rollup_date=today, channel="whatsapp", outreach_sent=20),
    ]
    svc, mock_repo = _make_service(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_trend(days=30)

    assert len(result) == 1
    assert result[0].outreach_sent == 100


@pytest.mark.asyncio
async def test_trend_maps_fields_correctly():
    today = date.today()
    rows = [_row(
        rollup_date=today, channel=None,
        outreach_sent=50, outreach_replied=10,
        leads_created=3, leads_booked=1,
        proposals_sent=2, ai_spend_inr=7.5,
    )]
    svc, mock_repo = _make_service(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_trend()

    assert len(result) == 1
    t = result[0]
    assert t.rollup_date == today
    assert t.outreach_sent == 50
    assert t.outreach_replied == 10
    assert t.leads_created == 3
    assert t.leads_booked == 1
    assert t.proposals_sent == 2
    assert t.ai_spend_inr == pytest.approx(7.5)


# ── get_funnel ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_funnel_all_zeros_on_empty_workspace():
    session = MagicMock()

    def _scalar_result(val: int) -> MagicMock:
        r = MagicMock()
        r.scalar_one = MagicMock(return_value=val)
        return r

    session.execute = AsyncMock(side_effect=[
        _scalar_result(0),  # contacts
        _scalar_result(0),  # outreach_sent
        _scalar_result(0),  # replies
        _scalar_result(0),  # meetings
        _scalar_result(0),  # proposals
        _scalar_result(0),  # bookings
        _scalar_result(0),  # proposals_accepted (Sprint 18A)
        _scalar_result(0),  # pipeline_value_inr (Sprint 18A)
        _scalar_result(0),  # closed_revenue_inr (Sprint 18A)
        _scalar_result(0),  # proposals_sent_count for win_rate (Sprint 18A)
    ])

    svc = AnalyticsService(session)
    with patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()):
        result = await svc.get_funnel(workspace_id=WORKSPACE_ID)

    assert result.contacts == 0
    assert result.outreach_sent == 0
    assert result.replies == 0
    assert result.meetings == 0
    assert result.proposals == 0
    assert result.bookings == 0
    assert result.proposals_accepted == 0
    assert result.pipeline_value_inr == 0.0
    assert result.closed_revenue_inr == 0.0
    assert result.win_rate == 0.0


@pytest.mark.asyncio
async def test_funnel_maps_sql_results_correctly():
    session = MagicMock()

    def _scalar_result(val: int) -> MagicMock:
        r = MagicMock()
        r.scalar_one = MagicMock(return_value=val)
        return r

    session.execute = AsyncMock(side_effect=[
        _scalar_result(150),     # contacts
        _scalar_result(80),      # outreach_sent
        _scalar_result(20),      # replies (interested only)
        _scalar_result(8),       # meetings
        _scalar_result(5),       # proposals
        _scalar_result(3),       # bookings
        _scalar_result(2),       # proposals_accepted (Sprint 18A)
        _scalar_result(250000),  # pipeline_value_inr (Sprint 18A)
        _scalar_result(180000),  # closed_revenue_inr (Sprint 18A)
        _scalar_result(4),       # proposals_sent_count for win_rate (Sprint 18A)
    ])

    svc = AnalyticsService(session)
    with patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()):
        result = await svc.get_funnel(workspace_id=WORKSPACE_ID)

    assert result.contacts == 150
    assert result.outreach_sent == 80
    assert result.replies == 20
    assert result.meetings == 8
    assert result.proposals == 5
    assert result.bookings == 3
    assert result.proposals_accepted == 2
    assert result.pipeline_value_inr == 250000.0
    assert result.closed_revenue_inr == 180000.0
    assert result.win_rate == round(2 / 4, 4)


# ── Sprint 19: get_campaign_roi ───────────────────────────────────────────────

from decimal import Decimal
from datetime import datetime, UTC
from corpmind.modules.analytics.models import AnalyticsCampaignSummary


def _campaign_row(
    *,
    proposals_sent: int = 10,
    proposals_accepted: int = 3,
    closed_revenue_inr: float = 150000.0,
    avg_deal_size_inr: float | None = 50000.0,
    win_rate: float = 0.3,
    avg_days_to_accept: float | None = 7.5,
) -> MagicMock:
    r = MagicMock(spec=AnalyticsCampaignSummary)
    r.campaign_id = uuid.uuid4()
    r.campaign_name = "Test Campaign"
    r.channel = "whatsapp"
    r.campaign_status = "completed"
    r.recipients_count = 100
    r.messages_sent = 100
    r.messages_delivered = 90
    r.replies_received = 20
    r.leads_created = 5
    r.proposals_sent = proposals_sent
    r.proposals_accepted = proposals_accepted
    r.closed_revenue_inr = Decimal(str(closed_revenue_inr))
    r.avg_deal_size_inr = Decimal(str(avg_deal_size_inr)) if avg_deal_size_inr is not None else None
    r.win_rate = Decimal(str(win_rate))
    r.avg_days_to_accept = Decimal(str(avg_days_to_accept)) if avg_days_to_accept is not None else None
    r.last_refreshed_at = datetime.now(UTC)
    return r


@pytest.mark.asyncio
async def test_campaign_roi_confidence_metadata():
    """Rows with < 5 proposals_sent are flagged low_confidence (Amendment 2)."""
    row_high = _campaign_row(proposals_sent=10)
    row_low = _campaign_row(proposals_sent=3)

    session = MagicMock()
    svc = AnalyticsService(session)

    mock_repo = MagicMock()
    mock_repo.list_by_workspace = AsyncMock(return_value=[row_high, row_low])
    mock_repo.count_by_workspace = AsyncMock(return_value=2)

    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsCampaignSummaryRepo", return_value=mock_repo),
    ):
        result = await svc.get_campaign_roi(workspace_id=WORKSPACE_ID)

    assert result.total == 2
    assert result.attribution_model == "all_touch"

    items = result.items
    assert items[0].low_confidence is False
    assert items[0].sample_size == 10
    assert items[1].low_confidence is True
    assert items[1].sample_size == 3


@pytest.mark.asyncio
async def test_campaign_roi_attribution_model_always_all_touch():
    """attribution_model must always be 'all_touch' (Amendment 3)."""
    session = MagicMock()
    svc = AnalyticsService(session)

    mock_repo = MagicMock()
    mock_repo.list_by_workspace = AsyncMock(return_value=[])
    mock_repo.count_by_workspace = AsyncMock(return_value=0)

    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsCampaignSummaryRepo", return_value=mock_repo),
    ):
        result = await svc.get_campaign_roi(workspace_id=WORKSPACE_ID)

    assert result.attribution_model == "all_touch"
    assert result.items == []
    assert result.total == 0


@pytest.mark.asyncio
async def test_campaign_roi_avg_days_to_accept_none_when_no_accepted():
    """avg_days_to_accept should pass through as None when stored as None."""
    row = _campaign_row(proposals_sent=6, avg_days_to_accept=None)
    session = MagicMock()
    svc = AnalyticsService(session)

    mock_repo = MagicMock()
    mock_repo.list_by_workspace = AsyncMock(return_value=[row])
    mock_repo.count_by_workspace = AsyncMock(return_value=1)

    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsCampaignSummaryRepo", return_value=mock_repo),
    ):
        result = await svc.get_campaign_roi(workspace_id=WORKSPACE_ID)

    assert result.items[0].avg_days_to_accept is None


# ── Sprint 19: get_pricing_calibration ────────────────────────────────────────

@pytest.mark.asyncio
async def test_pricing_calibration_low_confidence_when_lt_5_samples():
    """low_confidence=True when fewer than 5 accepted proposals (Amendment 2)."""
    session = MagicMock()

    def _mapping(data: dict) -> MagicMock:
        m = MagicMock()
        m.__getitem__ = lambda self, k: data[k]
        return m

    profile_result = MagicMock()
    profile_result.mappings = MagicMock(return_value=MagicMock(
        first=MagicMock(return_value=_mapping({"pricing_min_inr": 50000, "pricing_max_inr": 200000}))
    ))

    stats_result = MagicMock()
    stats_result.mappings = MagicMock(return_value=MagicMock(
        first=MagicMock(return_value=_mapping({
            "sample_size": 3,
            "actual_min": 60000,
            "actual_max": 120000,
            "actual_avg": 90000,
            "actual_median": 85000,
            "avg_days": 8.5,
        }))
    ))

    session.execute = AsyncMock(side_effect=[profile_result, stats_result])

    svc = AnalyticsService(session)
    ctx = MagicMock()
    ctx.org_id = TENANT_ID

    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_pricing_calibration(workspace_id=WORKSPACE_ID)

    assert result.low_confidence is True
    assert result.sample_size == 3
    assert result.stated_min_inr == 50000
    assert result.stated_max_inr == 200000
    assert result.avg_days_to_accept == pytest.approx(8.5)


@pytest.mark.asyncio
async def test_pricing_calibration_not_low_confidence_when_gte_5():
    """low_confidence=False when 5+ accepted proposals."""
    session = MagicMock()

    def _mapping(data: dict) -> MagicMock:
        m = MagicMock()
        m.__getitem__ = lambda self, k: data[k]
        return m

    profile_result = MagicMock()
    profile_result.mappings = MagicMock(return_value=MagicMock(
        first=MagicMock(return_value=None)
    ))

    stats_result = MagicMock()
    stats_result.mappings = MagicMock(return_value=MagicMock(
        first=MagicMock(return_value=_mapping({
            "sample_size": 8,
            "actual_min": 40000,
            "actual_max": 300000,
            "actual_avg": 150000,
            "actual_median": 140000,
            "avg_days": 12.0,
        }))
    ))

    session.execute = AsyncMock(side_effect=[profile_result, stats_result])

    svc = AnalyticsService(session)
    ctx = MagicMock()
    ctx.org_id = TENANT_ID

    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_pricing_calibration(workspace_id=WORKSPACE_ID)

    assert result.low_confidence is False
    assert result.sample_size == 8
    assert result.stated_min_inr is None
    assert result.stated_max_inr is None
