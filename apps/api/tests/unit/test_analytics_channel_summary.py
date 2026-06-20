"""Unit tests for AnalyticsService.get_channel_summary() — mocked repo + session.

Covers:
  - empty analytics_daily → all zeros, no division errors
  - sent/delivered/opened aggregated from channel rows only (not cross-channel rows)
  - delivery_rate = delivered / sent (rounded to 4 dp)
  - read_rate = opened / delivered (rounded to 4 dp)
  - delivery_rate = 0.0 when sent == 0 (no ZeroDivisionError)
  - read_rate = 0.0 when delivered == 0 (no ZeroDivisionError)
  - failed comes from live session.execute (not repo)
  - compliance_blocks aggregated from channel rows
  - channel and period_days echoed in output
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.models import AnalyticsDaily  # noqa: TC001
from corpmind.modules.analytics.service import AnalyticsService


TENANT_ID = uuid.uuid4()


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = TENANT_ID
    return ctx


def _row(
    *,
    channel: str | None = None,
    outreach_sent: int = 0,
    outreach_delivered: int = 0,
    outreach_opened: int = 0,
    outreach_replied: int = 0,
    compliance_blocks: int = 0,
    **kwargs,
) -> MagicMock:
    r = MagicMock(spec=AnalyticsDaily)
    r.rollup_date = kwargs.get("rollup_date", date.today())
    r.channel = channel
    r.outreach_sent = outreach_sent
    r.outreach_delivered = outreach_delivered
    r.outreach_opened = outreach_opened
    r.outreach_replied = outreach_replied
    r.compliance_blocks = compliance_blocks
    r.meetings_scheduled = 0
    r.meetings_completed = 0
    r.leads_created = 0
    r.leads_booked = 0
    r.proposals_generated = 0
    r.proposals_approved = 0
    r.proposals_sent = 0
    r.ai_spend_inr = 0.0
    return r


def _make_service(repo_rows: list, failed_count: int = 0):
    session = MagicMock()
    failed_result = MagicMock()
    failed_result.scalar_one = MagicMock(return_value=failed_count)
    session.execute = AsyncMock(return_value=failed_result)

    svc = AnalyticsService(session)

    mock_repo = MagicMock()
    mock_repo.list_by_date_range = AsyncMock(return_value=repo_rows)

    return svc, mock_repo


# ── Zero state ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_channel_summary_empty_returns_zeros():
    svc, mock_repo = _make_service([], failed_count=0)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_channel_summary(channel="whatsapp", days=30)

    assert result.sent == 0
    assert result.delivered == 0
    assert result.opened == 0
    assert result.failed == 0
    assert result.compliance_blocks == 0
    assert result.delivery_rate == 0.0
    assert result.read_rate == 0.0
    assert result.channel == "whatsapp"
    assert result.period_days == 30


# ── Aggregation ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_channel_summary_aggregates_wa_rows_only():
    """Cross-channel (channel=None) and other-channel rows must be excluded."""
    rows = [
        _row(channel="whatsapp", outreach_sent=100, outreach_delivered=85, outreach_opened=60, compliance_blocks=2),
        _row(channel="whatsapp", outreach_sent=50, outreach_delivered=40, outreach_opened=30, compliance_blocks=1),
        _row(channel=None, outreach_sent=200, outreach_delivered=180),   # cross-channel: excluded
        _row(channel="email", outreach_sent=300, outreach_delivered=250),  # other channel: excluded
    ]
    svc, mock_repo = _make_service(rows, failed_count=5)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_channel_summary(channel="whatsapp", days=30)

    assert result.sent == 150
    assert result.delivered == 125
    assert result.opened == 90
    assert result.compliance_blocks == 3
    assert result.failed == 5


# ── Rate calculations ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delivery_rate_computed_correctly():
    rows = [_row(channel="whatsapp", outreach_sent=200, outreach_delivered=150)]
    svc, mock_repo = _make_service(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_channel_summary(channel="whatsapp")

    assert result.delivery_rate == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_read_rate_computed_correctly():
    rows = [_row(channel="whatsapp", outreach_sent=100, outreach_delivered=80, outreach_opened=40)]
    svc, mock_repo = _make_service(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_channel_summary(channel="whatsapp")

    assert result.read_rate == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_delivery_rate_zero_when_no_sent():
    svc, mock_repo = _make_service([])
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_channel_summary(channel="whatsapp")

    assert result.delivery_rate == 0.0


@pytest.mark.asyncio
async def test_read_rate_zero_when_no_delivered():
    rows = [_row(channel="whatsapp", outreach_sent=50, outreach_delivered=0, outreach_opened=0)]
    svc, mock_repo = _make_service(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_channel_summary(channel="whatsapp")

    assert result.read_rate == 0.0


# ── failed is a live query ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failed_comes_from_live_query():
    """failed count must come from session.execute (live query), not repo."""
    rows = [_row(channel="whatsapp", outreach_sent=100, outreach_delivered=90)]
    svc, mock_repo = _make_service(rows, failed_count=7)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.AnalyticsDailyRepo", return_value=mock_repo),
    ):
        result = await svc.get_channel_summary(channel="whatsapp")

    assert result.failed == 7
    # session.execute must have been called for the live failed query
    assert svc._session.execute.called
