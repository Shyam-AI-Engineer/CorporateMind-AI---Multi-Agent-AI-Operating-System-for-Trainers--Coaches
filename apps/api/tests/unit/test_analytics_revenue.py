"""Unit tests for Sprint 18A analytics revenue extensions.

Covers:
  AnalyticsSummary schema
    - proposals_accepted and closed_revenue_inr default to 0
    - win_rate computed field: proposals_accepted / proposals_sent
    - win_rate is 0.0 when proposals_sent is 0

  AnalyticsFunnelOut schema
    - new revenue fields present with correct defaults
    - win_rate stored as plain field (not computed — set by service)

  AnalyticsService.get_funnel()
    - issues SQL for proposals_accepted count
    - issues SQL for pipeline_value_inr (sent + no client response)
    - issues SQL for closed_revenue_inr (accepted proposals)
    - issues SQL for proposals_sent_count (win_rate denominator)
    - win_rate is proposals_accepted / proposals_sent
    - win_rate is 0.0 when no proposals sent

  AnalyticsService.get_summary()
    - proposals_accepted summed from analytics_daily rows
    - closed_revenue_inr summed from analytics_daily rows
    - win_rate computed field present on result

  _compute_tenant_rollup (analytics task)
    - issues SQL for proposals_accepted rollup
    - issues SQL for closed_revenue_inr rollup
    - passes both to upsert_rollup
"""

from __future__ import annotations

import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.schemas import AnalyticsFunnelOut, AnalyticsSummary
from corpmind.workers.tasks.analytics import _compute_tenant_rollup


# ── AnalyticsSummary schema ────────────────────────────────────────────────────

class TestAnalyticsSummaryRevenue:
    def _make_summary(self, **overrides) -> AnalyticsSummary:
        defaults = dict(
            period_days=30,
            total_sent=100,
            total_delivered=95,
            total_replied=20,
            reply_rate=0.2,
            delivery_rate=0.95,
            total_spend_inr=500.0,
            meetings_scheduled=10,
            meetings_completed=8,
            leads_created=15,
            leads_booked=5,
            proposals_generated=8,
            proposals_approved=6,
            proposals_sent=6,
        )
        defaults.update(overrides)
        return AnalyticsSummary(**defaults)

    def test_proposals_accepted_defaults_to_zero(self):
        s = self._make_summary()
        assert s.proposals_accepted == 0

    def test_closed_revenue_defaults_to_zero(self):
        s = self._make_summary()
        assert s.closed_revenue_inr == 0.0

    def test_win_rate_is_zero_when_no_proposals_sent(self):
        s = self._make_summary(proposals_sent=0, proposals_accepted=0)
        assert s.win_rate == 0.0

    def test_win_rate_computed_correctly(self):
        s = self._make_summary(proposals_sent=8, proposals_accepted=3)
        assert s.win_rate == round(3 / 8, 4)

    def test_win_rate_is_one_when_all_accepted(self):
        s = self._make_summary(proposals_sent=5, proposals_accepted=5)
        assert s.win_rate == 1.0

    def test_booking_rate_still_present(self):
        """booking_rate must not be removed — backward compat."""
        s = self._make_summary(proposals_sent=6, leads_booked=3)
        assert s.booking_rate == 0.5


# ── AnalyticsFunnelOut schema ──────────────────────────────────────────────────

class TestAnalyticsFunnelOutRevenue:
    def test_revenue_fields_default_to_zero(self):
        f = AnalyticsFunnelOut(
            contacts=100,
            outreach_sent=80,
            replies=20,
            meetings=10,
            proposals=8,
            bookings=5,
        )
        assert f.proposals_accepted == 0
        assert f.pipeline_value_inr == 0.0
        assert f.closed_revenue_inr == 0.0
        assert f.win_rate == 0.0

    def test_revenue_fields_populated(self):
        f = AnalyticsFunnelOut(
            contacts=100,
            outreach_sent=80,
            replies=20,
            meetings=10,
            proposals=8,
            bookings=5,
            proposals_accepted=3,
            pipeline_value_inr=450000.0,
            closed_revenue_inr=300000.0,
            win_rate=0.375,
        )
        assert f.proposals_accepted == 3
        assert f.pipeline_value_inr == 450000.0
        assert f.closed_revenue_inr == 300000.0
        assert f.win_rate == 0.375


# ── AnalyticsService.get_funnel() ─────────────────────────────────────────────

class TestGetFunnelRevenue:
    def _make_session(self, scalar_sequence: list) -> MagicMock:
        """Return a mock session whose execute() returns each scalar in sequence."""
        session = MagicMock()
        results = []
        for val in scalar_sequence:
            r = MagicMock()
            r.scalar_one.return_value = val
            results.append(r)
        session.execute = AsyncMock(side_effect=results)
        return session

    def _make_ctx(self) -> MagicMock:
        ctx = MagicMock()
        ctx.org_id = uuid.uuid4()
        return ctx

    @pytest.mark.asyncio
    async def test_funnel_includes_revenue_fields(self):
        """get_funnel() returns proposals_accepted, pipeline_value_inr,
        closed_revenue_inr, and win_rate."""
        from corpmind.modules.analytics.service import AnalyticsService

        # Sequence matches order of execute() calls in get_funnel():
        # contacts, outreach_sent, replies, meetings, proposals, bookings,
        # proposals_accepted, pipeline_value_inr, closed_revenue_inr, proposals_sent_count
        session = self._make_session([50, 40, 15, 8, 6, 4, 2, 150000, 200000, 5])

        with patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=self._make_ctx(),
        ):
            svc = AnalyticsService(session)
            result = await svc.get_funnel(workspace_id=uuid.uuid4())

        assert result.proposals_accepted == 2
        assert result.pipeline_value_inr == 150000.0
        assert result.closed_revenue_inr == 200000.0
        assert result.win_rate == round(2 / 5, 4)

    @pytest.mark.asyncio
    async def test_win_rate_zero_when_no_proposals_sent(self):
        """win_rate is 0.0 when proposals_sent_count is 0."""
        from corpmind.modules.analytics.service import AnalyticsService

        session = self._make_session([0, 0, 0, 0, 0, 0, 0, 0, 0, 0])

        with patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=self._make_ctx(),
        ):
            svc = AnalyticsService(session)
            result = await svc.get_funnel(workspace_id=uuid.uuid4())

        assert result.win_rate == 0.0


# ── _compute_tenant_rollup (Celery task) ──────────────────────────────────────

class TestComputeTenantRollupRevenue:
    def test_rollup_queries_proposals_accepted(self):
        """_compute_tenant_rollup must query client_accepted_at for accepted count."""
        source = inspect.getsource(_compute_tenant_rollup)
        assert "client_accepted_at" in source, (
            "revenue rollup must query client_accepted_at::date = :d"
        )
        assert "proposals_accepted" in source, (
            "proposals_accepted must be computed in the rollup"
        )

    def test_rollup_queries_closed_revenue(self):
        """_compute_tenant_rollup must query SUM(actual_value_inr) for revenue."""
        source = inspect.getsource(_compute_tenant_rollup)
        assert "actual_value_inr" in source, (
            "closed_revenue_inr rollup must sum actual_value_inr"
        )
        assert "closed_revenue_inr" in source, (
            "closed_revenue_inr must be passed to upsert_rollup"
        )

    def test_rollup_passes_revenue_to_upsert(self):
        """upsert_rollup call includes proposals_accepted and closed_revenue_inr."""
        source = inspect.getsource(_compute_tenant_rollup)
        assert "proposals_accepted=proposals_accepted" in source
        assert "closed_revenue_inr=closed_revenue_inr" in source


# ── Sprint 19: campaign + trainer rollup tasks ────────────────────────────────

class TestSprintNineCeleryTasks:
    def test_campaign_summary_queries_all_touch_join(self):
        """Campaign summary must use campaign_recipients → leads → proposals join."""
        from corpmind.workers.tasks.analytics import _compute_tenant_campaign_summaries
        source = inspect.getsource(_compute_tenant_campaign_summaries)
        assert "campaign_recipients" in source
        assert "leads" in source
        assert "proposals" in source

    def test_campaign_summary_queries_avg_days_to_accept(self):
        """avg_days_to_accept must be computed via EXTRACT(EPOCH ...) / 86400 (Amendment 1)."""
        from corpmind.workers.tasks.analytics import _compute_tenant_campaign_summaries
        source = inspect.getsource(_compute_tenant_campaign_summaries)
        assert "avg_days_to_accept" in source
        assert "86400" in source

    def test_campaign_summary_computes_win_rate(self):
        """win_rate = proposals_accepted / proposals_sent per campaign."""
        from corpmind.workers.tasks.analytics import _compute_tenant_campaign_summaries
        source = inspect.getsource(_compute_tenant_campaign_summaries)
        assert "win_rate" in source
        assert "proposals_sent" in source
        assert "proposals_accepted" in source

    def test_trainer_summary_queries_avg_days_to_accept(self):
        """Trainer summary must compute avg_days_to_accept per rollup_date (Amendment 1)."""
        from corpmind.workers.tasks.analytics import _compute_workspace_trainer_summary
        source = inspect.getsource(_compute_workspace_trainer_summary)
        assert "avg_days_to_accept" in source
        assert "86400" in source

    def test_trainer_summary_queries_pipeline_value(self):
        """Trainer summary must compute pipeline_value_inr for open proposals."""
        from corpmind.workers.tasks.analytics import _compute_workspace_trainer_summary
        source = inspect.getsource(_compute_workspace_trainer_summary)
        assert "pipeline_value_inr" in source
        assert "expected_value_inr" in source

    def test_compute_campaign_summary_task_exists(self):
        """compute_campaign_summary Celery task must be registered."""
        from corpmind.workers.tasks.analytics import compute_campaign_summary
        assert callable(compute_campaign_summary)

    def test_compute_trainer_summary_task_exists(self):
        """compute_trainer_summary Celery task must be registered."""
        from corpmind.workers.tasks.analytics import compute_trainer_summary
        assert callable(compute_trainer_summary)


# ── Sprint 19: CampaignROISummary schema ─────────────────────────────────────

class TestCampaignROISummarySchema:
    def test_schema_includes_confidence_metadata(self):
        """sample_size and low_confidence must be present (Amendment 2)."""
        from corpmind.modules.analytics.schemas import CampaignROISummary
        fields = CampaignROISummary.model_fields
        assert "sample_size" in fields
        assert "low_confidence" in fields

    def test_campaign_roi_list_out_has_attribution_model(self):
        """CampaignROIListOut.attribution_model defaults to 'all_touch' (Amendment 3)."""
        from corpmind.modules.analytics.schemas import CampaignROIListOut
        out = CampaignROIListOut(items=[], total=0)
        assert out.attribution_model == "all_touch"

    def test_all_intelligence_schemas_have_confidence_metadata(self):
        """Amendment 2: all 4 intelligence endpoints include sample_size + low_confidence."""
        from corpmind.modules.analytics.schemas import (
            CampaignROIListOut,
            IndustryPerformanceOut,
            PricingCalibrationOut,
            TopicPerformanceOut,
        )
        for cls in (TopicPerformanceOut, IndustryPerformanceOut, PricingCalibrationOut):
            fields = cls.model_fields
            assert "sample_size" in fields, f"{cls.__name__} missing sample_size"
            assert "low_confidence" in fields, f"{cls.__name__} missing low_confidence"
        # CampaignROIListOut: confidence lives on each item row
        item_fields = CampaignROIListOut.model_fields
        assert "items" in item_fields
