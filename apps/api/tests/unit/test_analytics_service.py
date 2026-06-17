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


@pytest.mark.asyncio
async def test_funnel_maps_sql_results_correctly():
    session = MagicMock()

    def _scalar_result(val: int) -> MagicMock:
        r = MagicMock()
        r.scalar_one = MagicMock(return_value=val)
        return r

    session.execute = AsyncMock(side_effect=[
        _scalar_result(150),   # contacts
        _scalar_result(80),    # outreach_sent
        _scalar_result(20),    # replies (interested only)
        _scalar_result(8),     # meetings
        _scalar_result(5),     # proposals
        _scalar_result(3),     # bookings
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
