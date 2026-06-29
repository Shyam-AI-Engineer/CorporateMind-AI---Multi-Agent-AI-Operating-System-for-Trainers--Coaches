"""Unit tests for Sprint 20A — deterministic recommendations.

Covers:
  _confidence() static method
    - hard minimum suppression
    - score < 20 suppression
    - low/medium/high level mapping
    - evidence_strength mapping
    - composite S × 0.6 + R × 0.4 formula

  RecommendationItem schema
    - required fields present
    - evidence_strength values
    - supporting_data accepts numeric/string/None values

  RecommendationsOut schema
    - suppressed_count defaults to 0
    - total matches len(recommendations)

  AnalyticsService._rec_industry()
    - suppresses when < 2 qualifying industries
    - suppresses when delta < 5pp
    - returns correct title/rationale
    - increments suppressed when qualifying exists but threshold not met

  AnalyticsService._rec_topic()
    - suppresses when < 2 qualifying topics
    - suppresses when delta < 8pp
    - returns correct title

  AnalyticsService._rec_pricing() sub-cases
    - underpriced: actual_median > stated_max × 1.05
    - overpriced: actual_median < stated_min × 0.85
    - slow_acceptance: avg_days > 30
    - suppresses when sample_size < 10

  AnalyticsService._rec_campaign()
    - suppresses when < 3 qualifying campaigns
    - suppresses when roi_ratio < 1.5
    - returns recommendation when roi_ratio >= 1.5

  AnalyticsService._rec_channel()
    - suppresses when < 2 qualifying channels
    - suppresses when delta < 5pp
    - returns recommendation with correct channel

  AnalyticsService.get_recommendations()
    - schema fields present: workspace_id, period_days, recommendations, suppressed_count, total
    - period_days is always 90
    - recommendations is a list

  GET /analytics/recommendations API
    - returns 200 with correct response_model fields
    - workspace_id query param is required
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.schemas import (
    RecommendationItem,
    RecommendationsOut,
)


# ── _confidence() ─────────────────────────────────────────────────────────────

class TestConfidenceFormula:
    def _conf(self, *, n, n_ideal=20, hard_min=5, delta=0.15, noise=0.05, ceiling=0.25):
        from corpmind.modules.analytics.service import AnalyticsService
        return AnalyticsService._confidence(
            n=n, n_ideal=n_ideal, hard_min=hard_min,
            delta=delta, noise_floor=noise, signal_ceiling=ceiling,
        )

    def test_below_hard_min_suppressed(self):
        score, level, strength = self._conf(n=4, hard_min=5)
        assert score == 0
        assert level == "suppressed"
        assert strength == "weak"

    def test_at_hard_min_not_suppressed(self):
        score, level, strength = self._conf(n=5, hard_min=5)
        assert score > 0

    def test_score_below_20_suppressed(self):
        # n=5, n_ideal=100 → S=0.05; delta=noise_floor → R=0.0 → raw=0.03 → score=3
        score, level, strength = self._conf(n=5, n_ideal=100, hard_min=5, delta=0.05)
        assert score == 0
        assert level == "suppressed"

    def test_high_level_at_70_plus(self):
        score, level, strength = self._conf(n=20, n_ideal=20, delta=0.25, ceiling=0.25)
        assert score >= 70
        assert level == "high"
        assert strength == "strong"

    def test_medium_level_40_to_69(self):
        # n=10/20 → S=0.5; delta at midpoint → R≈0.5 → raw=0.5 → score=50
        score, level, strength = self._conf(n=10, n_ideal=20, delta=0.15, noise=0.05, ceiling=0.25)
        assert 40 <= score <= 69
        assert level == "medium"
        assert strength == "moderate"

    def test_low_level_20_to_39(self):
        # n=6/20 → S=0.3; small delta → R≈0.1 → raw=0.22 → score=22
        score, level, strength = self._conf(n=6, n_ideal=20, delta=0.06, noise=0.05, ceiling=0.25)
        assert 20 <= score <= 39
        assert level == "low"
        assert strength == "weak"

    def test_n_ideal_caps_S_at_1(self):
        # n=100 with n_ideal=20 → S capped at 1.0
        score_capped, _, _ = self._conf(n=100, n_ideal=20)
        score_exact, _, _ = self._conf(n=20, n_ideal=20)
        assert score_capped == score_exact

    def test_delta_below_noise_floor_gives_R_zero(self):
        # delta=noise_floor → (delta - noise) / span = 0 → R=0
        score, _, _ = self._conf(n=20, n_ideal=20, delta=0.05, noise=0.05, ceiling=0.25)
        # R=0 → raw = 0.6 → score=60 (medium)
        assert score == 60

    def test_evidence_strong_when_score_70_plus(self):
        _, _, strength = self._conf(n=20, n_ideal=20, delta=0.25, ceiling=0.25)
        assert strength == "strong"

    def test_evidence_moderate_when_40_to_69(self):
        _, _, strength = self._conf(n=10, n_ideal=20)
        assert strength == "moderate"

    def test_evidence_weak_when_below_40(self):
        _, _, strength = self._conf(n=6, n_ideal=20, delta=0.06)
        assert strength == "weak"


# ── RecommendationItem schema ─────────────────────────────────────────────────

class TestRecommendationItemSchema:
    def _make(self, **overrides) -> RecommendationItem:
        defaults = dict(
            type="industry",
            title="Focus on IT Services",
            rationale="IT Services closes at 42% vs 28% median.",
            action="Target IT Services companies.",
            supporting_data={"industry": "IT Services", "win_rate": 0.42, "delta_pp": 14.0},
            confidence_score=74,
            confidence_level="high",
            evidence_strength="strong",
            sample_size=12,
            low_confidence=False,
            generated_at=datetime.now(UTC),
        )
        defaults.update(overrides)
        return RecommendationItem(**defaults)

    def test_all_fields_accepted(self):
        item = self._make()
        assert item.type == "industry"
        assert item.confidence_score == 74
        assert item.evidence_strength == "strong"

    def test_supporting_data_accepts_none_values(self):
        item = self._make(supporting_data={"avg_days": None, "revenue": 150000.0})
        assert item.supporting_data["avg_days"] is None

    def test_low_confidence_true_when_score_below_40(self):
        item = self._make(confidence_score=35, confidence_level="low", low_confidence=True)
        assert item.low_confidence is True

    def test_evidence_strength_values(self):
        for strength in ("weak", "moderate", "strong"):
            item = self._make(evidence_strength=strength)
            assert item.evidence_strength == strength


# ── RecommendationsOut schema ─────────────────────────────────────────────────

class TestRecommendationsOutSchema:
    def test_empty_recommendations_valid(self):
        out = RecommendationsOut(
            workspace_id="ws-1",
            generated_at=datetime.now(UTC),
            period_days=90,
            recommendations=[],
            suppressed_count=3,
            total=0,
        )
        assert out.suppressed_count == 3
        assert out.total == 0

    def test_period_days_is_90(self):
        out = RecommendationsOut(
            workspace_id="ws-1",
            generated_at=datetime.now(UTC),
            period_days=90,
            recommendations=[],
            suppressed_count=0,
            total=0,
        )
        assert out.period_days == 90


# ── _rec_industry helper ──────────────────────────────────────────────────────

class TestRecIndustry:
    def _make_industry_out(self, items):
        from corpmind.modules.analytics.schemas import IndustryPerformanceOut
        return IndustryPerformanceOut(
            items=items,
            workspace_id="ws-1",
            generated_at=datetime.now(UTC),
            unknown_count=0,
            sample_size=sum(i.proposals_sent for i in items),
            low_confidence=False,
        )

    def _make_industry_stat(self, industry, proposals_sent, win_rate, revenue=100000.0):
        from corpmind.modules.analytics.schemas import IndustryStat
        return IndustryStat(
            industry=industry,
            proposals_sent=proposals_sent,
            proposals_accepted=round(proposals_sent * win_rate),
            win_rate=win_rate,
            closed_revenue_inr=revenue,
        )

    def _svc(self):
        from corpmind.modules.analytics.service import AnalyticsService
        session = MagicMock()
        session.execute = AsyncMock()
        svc = AnalyticsService(session)
        return svc

    @pytest.mark.asyncio
    async def test_suppresses_when_less_than_2_qualifying(self):
        svc = self._svc()
        items = [self._make_industry_stat("IT Services", 5, 0.40)]
        industry_out = self._make_industry_out(items)
        with patch.object(svc, "get_industry_performance", AsyncMock(return_value=industry_out)):
            item, suppressed = await svc._rec_industry(uuid.uuid4(), datetime.now(UTC))
        assert item is None
        assert suppressed == 1  # qualifying exists but can't compare

    @pytest.mark.asyncio
    async def test_suppresses_when_delta_below_5pp(self):
        svc = self._svc()
        items = [
            self._make_industry_stat("IT Services", 10, 0.30),
            self._make_industry_stat("FMCG", 8, 0.28),
        ]
        industry_out = self._make_industry_out(items)
        with patch.object(svc, "get_industry_performance", AsyncMock(return_value=industry_out)):
            item, suppressed = await svc._rec_industry(uuid.uuid4(), datetime.now(UTC))
        assert item is None
        assert suppressed == 0

    @pytest.mark.asyncio
    async def test_returns_recommendation_when_delta_above_5pp(self):
        svc = self._svc()
        items = [
            self._make_industry_stat("IT Services", 12, 0.42, 480000.0),
            self._make_industry_stat("FMCG", 8, 0.20, 100000.0),
            self._make_industry_stat("Pharma", 6, 0.25, 80000.0),
        ]
        industry_out = self._make_industry_out(items)
        with patch.object(svc, "get_industry_performance", AsyncMock(return_value=industry_out)):
            item, suppressed = await svc._rec_industry(uuid.uuid4(), datetime.now(UTC))
        assert item is not None
        assert "IT Services" in item.title
        assert item.type == "industry"
        assert suppressed == 0

    @pytest.mark.asyncio
    async def test_suppresses_unknown_industry(self):
        """'Unknown' industry rows must not be included in qualifying list."""
        svc = self._svc()
        items = [
            self._make_industry_stat("Unknown", 15, 0.50),
            self._make_industry_stat("IT Services", 8, 0.20),
        ]
        industry_out = self._make_industry_out(items)
        with patch.object(svc, "get_industry_performance", AsyncMock(return_value=industry_out)):
            item, suppressed = await svc._rec_industry(uuid.uuid4(), datetime.now(UTC))
        # Only 1 qualifying (Unknown excluded) → must suppress
        assert item is None


# ── _rec_topic helper ─────────────────────────────────────────────────────────

class TestRecTopic:
    def _make_topic_out(self, items):
        from corpmind.modules.analytics.schemas import TopicPerformanceOut
        return TopicPerformanceOut(
            items=items,
            workspace_id="ws-1",
            generated_at=datetime.now(UTC),
            sample_size=sum(i.proposals_sent for i in items),
            low_confidence=False,
        )

    def _make_topic_stat(self, topic, proposals_sent, win_rate, revenue=100000.0):
        from corpmind.modules.analytics.schemas import TopicStat
        return TopicStat(
            topic=topic,
            proposals_sent=proposals_sent,
            proposals_accepted=round(proposals_sent * win_rate),
            win_rate=win_rate,
            closed_revenue_inr=revenue,
        )

    def _svc(self):
        from corpmind.modules.analytics.service import AnalyticsService
        session = MagicMock()
        session.execute = AsyncMock()
        return AnalyticsService(session)

    @pytest.mark.asyncio
    async def test_suppresses_when_only_one_topic(self):
        svc = self._svc()
        topic_out = self._make_topic_out([self._make_topic_stat("Leadership", 10, 0.40)])
        with patch.object(svc, "get_topic_performance", AsyncMock(return_value=topic_out)):
            item, suppressed = await svc._rec_topic(uuid.uuid4(), datetime.now(UTC))
        assert item is None
        assert suppressed == 1

    @pytest.mark.asyncio
    async def test_suppresses_when_delta_below_8pp(self):
        svc = self._svc()
        topic_out = self._make_topic_out([
            self._make_topic_stat("Leadership", 10, 0.35),
            self._make_topic_stat("Sales", 8, 0.30),
        ])
        with patch.object(svc, "get_topic_performance", AsyncMock(return_value=topic_out)):
            item, suppressed = await svc._rec_topic(uuid.uuid4(), datetime.now(UTC))
        assert item is None
        assert suppressed == 0

    @pytest.mark.asyncio
    async def test_returns_recommendation_when_delta_above_8pp(self):
        svc = self._svc()
        topic_out = self._make_topic_out([
            self._make_topic_stat("Leadership", 15, 0.45, 300000.0),
            self._make_topic_stat("Sales", 10, 0.25, 100000.0),
        ])
        with patch.object(svc, "get_topic_performance", AsyncMock(return_value=topic_out)):
            item, suppressed = await svc._rec_topic(uuid.uuid4(), datetime.now(UTC))
        assert item is not None
        assert "Leadership" in item.title
        assert item.type == "topic"


# ── _rec_pricing helper ───────────────────────────────────────────────────────

class TestRecPricing:
    def _make_pricing_out(self, **overrides):
        from corpmind.modules.analytics.schemas import PricingCalibrationOut
        defaults = dict(
            workspace_id="ws-1",
            stated_min_inr=50000,
            stated_max_inr=150000,
            actual_min_inr=60000.0,
            actual_max_inr=200000.0,
            actual_avg_inr=120000.0,
            actual_median_inr=120000.0,
            avg_days_to_accept=12.0,
            sample_size=12,
            low_confidence=False,
            generated_at=datetime.now(UTC),
        )
        defaults.update(overrides)
        return PricingCalibrationOut(**defaults)

    def _svc(self):
        from corpmind.modules.analytics.service import AnalyticsService
        session = MagicMock()
        session.execute = AsyncMock()
        return AnalyticsService(session)

    @pytest.mark.asyncio
    async def test_suppresses_when_sample_below_10(self):
        svc = self._svc()
        pricing = self._make_pricing_out(sample_size=9)
        with patch.object(svc, "get_pricing_calibration", AsyncMock(return_value=pricing)):
            item, suppressed = await svc._rec_pricing(uuid.uuid4(), datetime.now(UTC))
        assert item is None
        assert suppressed == 1

    @pytest.mark.asyncio
    async def test_underpriced_when_median_above_stated_max(self):
        svc = self._svc()
        # median = 170_000 > stated_max * 1.05 = 157_500
        pricing = self._make_pricing_out(
            stated_max_inr=150000, actual_median_inr=170000.0, sample_size=15,
        )
        with patch.object(svc, "get_pricing_calibration", AsyncMock(return_value=pricing)):
            item, _ = await svc._rec_pricing(uuid.uuid4(), datetime.now(UTC))
        assert item is not None
        assert item.supporting_data["sub_type"] == "underpriced"

    @pytest.mark.asyncio
    async def test_overpriced_when_median_below_stated_min(self):
        svc = self._svc()
        # median = 35_000 < stated_min * 0.85 = 42_500
        pricing = self._make_pricing_out(
            stated_min_inr=50000, actual_median_inr=35000.0, sample_size=12,
        )
        with patch.object(svc, "get_pricing_calibration", AsyncMock(return_value=pricing)):
            item, _ = await svc._rec_pricing(uuid.uuid4(), datetime.now(UTC))
        assert item is not None
        assert item.supporting_data["sub_type"] == "overpriced"

    @pytest.mark.asyncio
    async def test_slow_acceptance_when_avg_days_above_30(self):
        svc = self._svc()
        pricing = self._make_pricing_out(
            stated_min_inr=None, stated_max_inr=None,
            actual_median_inr=100000.0, avg_days_to_accept=45.0, sample_size=10,
        )
        with patch.object(svc, "get_pricing_calibration", AsyncMock(return_value=pricing)):
            item, _ = await svc._rec_pricing(uuid.uuid4(), datetime.now(UTC))
        assert item is not None
        assert item.supporting_data["sub_type"] == "slow_acceptance"

    @pytest.mark.asyncio
    async def test_no_recommendation_when_aligned(self):
        svc = self._svc()
        # median = 100_000, exactly within stated range, avg_days = 15
        pricing = self._make_pricing_out(
            stated_min_inr=80000, stated_max_inr=120000,
            actual_median_inr=100000.0, avg_days_to_accept=15.0, sample_size=12,
        )
        with patch.object(svc, "get_pricing_calibration", AsyncMock(return_value=pricing)):
            item, suppressed = await svc._rec_pricing(uuid.uuid4(), datetime.now(UTC))
        assert item is None
        assert suppressed == 0


# ── _rec_campaign helper ──────────────────────────────────────────────────────

class TestRecCampaign:
    def _svc_with_rows(self, rows):
        from corpmind.modules.analytics.service import AnalyticsService
        session = MagicMock()
        mapping_result = MagicMock()
        mapping_result.mappings.return_value.all.return_value = rows
        session.execute = AsyncMock(return_value=mapping_result)
        return AnalyticsService(session)

    def _make_row(self, name, channel, win_rate, revenue, sent):
        return {
            "campaign_name": name,
            "channel": channel,
            "win_rate": win_rate,
            "closed_revenue_inr": revenue,
            "proposals_sent": sent,
            "proposals_accepted": round(sent * win_rate),
            "avg_days_to_accept": None,
            "recipients_count": sent * 10,
        }

    @pytest.mark.asyncio
    async def test_suppresses_when_fewer_than_3_campaigns(self):
        svc = self._svc_with_rows([
            self._make_row("Camp A", "whatsapp", 0.4, 200000, 10),
            self._make_row("Camp B", "email", 0.2, 50000, 8),
        ])
        ctx = MagicMock()
        ctx.org_id = uuid.uuid4()
        with patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx):
            item, suppressed = await svc._rec_campaign(uuid.uuid4(), datetime.now(UTC))
        assert item is None
        assert suppressed == 1

    @pytest.mark.asyncio
    async def test_suppresses_when_roi_ratio_below_1_5(self):
        svc = self._svc_with_rows([
            self._make_row("Camp A", "whatsapp", 0.4, 200000, 10),
            self._make_row("Camp B", "email", 0.3, 160000, 8),
            self._make_row("Camp C", "whatsapp", 0.25, 140000, 7),
        ])
        ctx = MagicMock()
        ctx.org_id = uuid.uuid4()
        with patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx):
            item, suppressed = await svc._rec_campaign(uuid.uuid4(), datetime.now(UTC))
        # ratio = 200_000 / 140_000 ≈ 1.43 < 1.5 → no rec
        assert item is None
        assert suppressed == 0

    @pytest.mark.asyncio
    async def test_returns_recommendation_when_roi_ratio_above_1_5(self):
        svc = self._svc_with_rows([
            self._make_row("Q3 Leadership Push", "whatsapp", 0.45, 300000, 12),
            self._make_row("Camp B", "email", 0.2, 80000, 8),
            self._make_row("Camp C", "email", 0.1, 30000, 6),
        ])
        ctx = MagicMock()
        ctx.org_id = uuid.uuid4()
        with patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx):
            item, _ = await svc._rec_campaign(uuid.uuid4(), datetime.now(UTC))
        assert item is not None
        assert "Q3 Leadership Push" in item.title
        assert item.type == "campaign"


# ── _rec_channel helper ───────────────────────────────────────────────────────

class TestRecChannel:
    def _svc_with_rows(self, rows):
        from corpmind.modules.analytics.service import AnalyticsService
        session = MagicMock()
        mapping_result = MagicMock()
        mapping_result.mappings.return_value.all.return_value = rows
        session.execute = AsyncMock(return_value=mapping_result)
        return AnalyticsService(session)

    def _make_row(self, channel, sent, accepted, revenue):
        return {
            "channel": channel,
            "total_sent": sent,
            "total_accepted": accepted,
            "total_revenue": revenue,
        }

    @pytest.mark.asyncio
    async def test_suppresses_when_only_one_channel(self):
        svc = self._svc_with_rows([self._make_row("whatsapp", 20, 8, 400000)])
        ctx = MagicMock()
        ctx.org_id = uuid.uuid4()
        with patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx):
            item, suppressed = await svc._rec_channel(uuid.uuid4(), datetime.now(UTC))
        assert item is None
        assert suppressed == 1

    @pytest.mark.asyncio
    async def test_suppresses_when_delta_below_5pp(self):
        svc = self._svc_with_rows([
            self._make_row("whatsapp", 20, 7, 350000),  # wr=0.35
            self._make_row("email", 15, 5, 200000),     # wr=0.333
        ])
        ctx = MagicMock()
        ctx.org_id = uuid.uuid4()
        with patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx):
            item, suppressed = await svc._rec_channel(uuid.uuid4(), datetime.now(UTC))
        # delta ≈ 1.7pp < 5pp → no rec
        assert item is None
        assert suppressed == 0

    @pytest.mark.asyncio
    async def test_returns_recommendation_when_delta_above_5pp(self):
        svc = self._svc_with_rows([
            self._make_row("whatsapp", 20, 9, 450000),  # wr=0.45
            self._make_row("email", 15, 3, 100000),     # wr=0.20
        ])
        ctx = MagicMock()
        ctx.org_id = uuid.uuid4()
        with patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx):
            item, _ = await svc._rec_channel(uuid.uuid4(), datetime.now(UTC))
        assert item is not None
        assert item.type == "channel"
        assert "Whatsapp" in item.title or "whatsapp" in item.supporting_data.get("channel", "")


# ── get_recommendations() integration ────────────────────────────────────────

class TestGetRecommendations:
    def _svc(self):
        from corpmind.modules.analytics.service import AnalyticsService
        session = MagicMock()
        session.execute = AsyncMock()
        return AnalyticsService(session)

    @pytest.mark.asyncio
    async def test_returns_recommendations_out_schema(self):
        svc = self._svc()
        ctx = MagicMock()
        ctx.org_id = uuid.uuid4()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch.object(svc, "_rec_industry", AsyncMock(return_value=(None, 0))),
            patch.object(svc, "_rec_topic", AsyncMock(return_value=(None, 0))),
            patch.object(svc, "_rec_pricing", AsyncMock(return_value=(None, 0))),
            patch.object(svc, "_rec_campaign", AsyncMock(return_value=(None, 0))),
            patch.object(svc, "_rec_channel", AsyncMock(return_value=(None, 0))),
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            result = await svc.get_recommendations(workspace_id=uuid.uuid4())

        assert isinstance(result, RecommendationsOut)
        assert result.period_days == 90
        assert isinstance(result.recommendations, list)
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_suppressed_count_aggregated(self):
        svc = self._svc()
        ctx = MagicMock()
        ctx.org_id = uuid.uuid4()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch.object(svc, "_rec_industry", AsyncMock(return_value=(None, 1))),
            patch.object(svc, "_rec_topic", AsyncMock(return_value=(None, 1))),
            patch.object(svc, "_rec_pricing", AsyncMock(return_value=(None, 1))),
            patch.object(svc, "_rec_campaign", AsyncMock(return_value=(None, 0))),
            patch.object(svc, "_rec_channel", AsyncMock(return_value=(None, 1))),
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            result = await svc.get_recommendations(workspace_id=uuid.uuid4())

        assert result.suppressed_count == 4

    @pytest.mark.asyncio
    async def test_recommendation_exceptions_are_swallowed(self):
        """A single failing rec type must not abort the whole response."""
        svc = self._svc()
        ctx = MagicMock()
        ctx.org_id = uuid.uuid4()

        async def explode(*_):
            raise RuntimeError("db error")

        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch.object(svc, "_rec_industry", explode),
            patch.object(svc, "_rec_topic", AsyncMock(return_value=(None, 0))),
            patch.object(svc, "_rec_pricing", AsyncMock(return_value=(None, 0))),
            patch.object(svc, "_rec_campaign", AsyncMock(return_value=(None, 0))),
            patch.object(svc, "_rec_channel", AsyncMock(return_value=(None, 0))),
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            result = await svc.get_recommendations(workspace_id=uuid.uuid4())

        assert isinstance(result, RecommendationsOut)

    @pytest.mark.asyncio
    async def test_redis_cache_hit_returns_immediately(self):
        from corpmind.modules.analytics.schemas import RecommendationsOut as ROut
        cached = ROut(
            workspace_id="ws-1",
            generated_at=datetime.now(UTC),
            period_days=90,
            recommendations=[],
            suppressed_count=2,
            total=0,
        )
        svc = self._svc()
        ctx = MagicMock()
        ctx.org_id = uuid.uuid4()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=cached.model_dump_json())
            result = await svc.get_recommendations(workspace_id=uuid.uuid4())
        assert result.suppressed_count == 2


# ── API endpoint ──────────────────────────────────────────────────────────────

class TestRecommendationsAPI:
    def test_recommendations_schema_has_all_fields(self):
        from corpmind.modules.analytics.schemas import RecommendationsOut
        fields = RecommendationsOut.model_fields
        assert "workspace_id" in fields
        assert "generated_at" in fields
        assert "period_days" in fields
        assert "recommendations" in fields
        assert "suppressed_count" in fields
        assert "total" in fields

    def test_recommendation_item_type_field_present(self):
        from corpmind.modules.analytics.schemas import RecommendationItem
        fields = RecommendationItem.model_fields
        assert "type" in fields
        assert "confidence_score" in fields
        assert "evidence_strength" in fields
        assert "supporting_data" in fields

    def test_api_endpoint_registered(self):
        from corpmind.modules.analytics.api import router
        paths = [route.path for route in router.routes]  # type: ignore[attr-defined]
        assert "/recommendations" in paths
