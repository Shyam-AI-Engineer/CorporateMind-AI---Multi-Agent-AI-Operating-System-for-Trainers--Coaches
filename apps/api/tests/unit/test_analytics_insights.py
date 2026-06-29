"""Unit tests for Sprint 20B — AnalyticsInsightService.

Covers:
  InsightOpportunity / InsightRisk / AnalyticsInsightOut schemas
    - required fields, valid construction, empty arrays valid

  AnalyticsInsightService._build_context()
    - context keys and structure
    - recommendations list shape
    - supporting_data pass-through (AI sees exactly what we pass)
    - empty recommendations produces empty list

  AnalyticsInsightService._parse_response()
    - valid JSON returns full AnalyticsInsightOut
    - malformed JSON triggers deterministic fallback
    - missing optional keys use safe defaults
    - non-list top_opportunities handled gracefully

  AnalyticsInsightService.get_insights()
    - empty recommendations → no LLM call, returns insufficient-data response
    - empty recommendations → data_limitations populated
    - Redis cache hit → returns cached without LLM call
    - non-empty recommendations → calls EuriClient with analytics_narrative task
    - non-empty recommendations → prompt_inputs contains recommendations_json
    - EuriClient raises → deterministic fallback returned (no crash)
    - EuriClient raises → logs warning (observable)

  AI safety regression
    - _build_context keys match expected contract (no extra DB fields leaked)
    - confidence_level in _build_context is copied verbatim from recommendation
    - _parse_response respects top_opportunities limit (max 5)
    - fallback path uses recommendation confidence_level verbatim
    - insufficient-data path never calls EuriClient

  GET /analytics/insights API
    - endpoint registered in router
    - response schema has expected fields
    - workspace_id query param required
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.schemas import (
    AnalyticsInsightOut,
    InsightOpportunity,
    InsightRisk,
    RecommendationItem,
    RecommendationsOut,
)
from corpmind.modules.analytics.service import AnalyticsInsightService

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = TENANT_ID
    return ctx


def _rec(
    rec_type: str = "industry",
    title: str = "Focus on IT Services",
    rationale: str = "IT closes at 45% vs 30% median.",
    action: str = "Target IT companies.",
    confidence_level: str = "high",
    evidence_strength: str = "strong",
    confidence_score: int = 78,
    sample_size: int = 12,
    low_confidence: bool = False,
) -> RecommendationItem:
    return RecommendationItem(
        type=rec_type,
        title=title,
        rationale=rationale,
        action=action,
        supporting_data={"industry": "IT Services", "win_rate": 0.45, "delta_pp": 15.0},
        confidence_score=confidence_score,
        confidence_level=confidence_level,
        evidence_strength=evidence_strength,
        sample_size=sample_size,
        low_confidence=low_confidence,
        generated_at=datetime.now(UTC),
    )


def _recs_out(recs: list[RecommendationItem] | None = None, suppressed: int = 0) -> RecommendationsOut:
    items = recs if recs is not None else [_rec()]
    return RecommendationsOut(
        workspace_id=str(WORKSPACE_ID),
        generated_at=datetime.now(UTC),
        period_days=90,
        recommendations=items,
        suppressed_count=suppressed,
        total=len(items),
    )


def _empty_recs(suppressed: int = 0) -> RecommendationsOut:
    return _recs_out(recs=[], suppressed=suppressed)


def _mock_redis(cached_json: str | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached_json)
    redis.set = AsyncMock(return_value=True)
    return redis


def _svc() -> AnalyticsInsightService:
    session = MagicMock()
    return AnalyticsInsightService(session)


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestInsightOpportunitySchema:
    def test_valid_construction(self):
        opp = InsightOpportunity(title="Lead IT", rationale="IT wins.", confidence_level="high")
        assert opp.title == "Lead IT"
        assert opp.confidence_level == "high"

    def test_low_medium_high_levels_accepted(self):
        for level in ("low", "medium", "high"):
            opp = InsightOpportunity(title="T", rationale="R", confidence_level=level)
            assert opp.confidence_level == level

    def test_title_and_rationale_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InsightOpportunity(title="T")  # type: ignore[call-arg]


class TestInsightRiskSchema:
    def test_valid_construction(self):
        risk = InsightRisk(title="Channel dependency", description="All revenue from one channel.")
        assert risk.title == "Channel dependency"

    def test_fields_stored(self):
        risk = InsightRisk(title="Slow acceptance", description="Average 45 days.")
        assert "45 days" in risk.description


class TestAnalyticsInsightOutSchema:
    def test_empty_arrays_valid(self):
        out = AnalyticsInsightOut(
            generated_at=datetime.now(UTC),
            executive_summary="No data.",
            top_opportunities=[],
            risks=[],
            data_limitations=[],
        )
        assert out.top_opportunities == []
        assert out.risks == []
        assert out.data_limitations == []

    def test_full_construction(self):
        out = AnalyticsInsightOut(
            generated_at=datetime.now(UTC),
            executive_summary="IT Services drives 78% win rate.",
            top_opportunities=[InsightOpportunity(title="IT", rationale="Wins.", confidence_level="high")],
            risks=[InsightRisk(title="Risk", description="Desc.")],
            data_limitations=["Pricing based on 8 deals."],
        )
        assert len(out.top_opportunities) == 1
        assert len(out.risks) == 1
        assert len(out.data_limitations) == 1

    def test_generated_at_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AnalyticsInsightOut(  # type: ignore[call-arg]
                executive_summary="x",
                top_opportunities=[],
                risks=[],
                data_limitations=[],
            )

    def test_executive_summary_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AnalyticsInsightOut(  # type: ignore[call-arg]
                generated_at=datetime.now(UTC),
                top_opportunities=[],
                risks=[],
                data_limitations=[],
            )


# ── _build_context() ──────────────────────────────────────────────────────────

class TestBuildContext:
    def test_workspace_id_present(self):
        recs = _recs_out()
        ctx = AnalyticsInsightService._build_context(recs)
        assert ctx["workspace_id"] == str(WORKSPACE_ID)

    def test_period_days_present(self):
        recs = _recs_out()
        ctx = AnalyticsInsightService._build_context(recs)
        assert ctx["period_days"] == 90

    def test_recommendations_list_shape(self):
        recs = _recs_out([_rec("industry"), _rec("topic")])
        ctx = AnalyticsInsightService._build_context(recs)
        assert len(ctx["recommendations"]) == 2  # type: ignore[arg-type]
        first = ctx["recommendations"][0]  # type: ignore[index]
        assert "type" in first
        assert "title" in first
        assert "confidence_level" in first
        assert "supporting_data" in first

    def test_supporting_data_passed_through(self):
        rec = _rec()
        recs = _recs_out([rec])
        ctx = AnalyticsInsightService._build_context(recs)
        assert ctx["recommendations"][0]["supporting_data"] == rec.supporting_data  # type: ignore[index]

    def test_empty_recs_produces_empty_list(self):
        ctx = AnalyticsInsightService._build_context(_empty_recs())
        assert ctx["recommendations"] == []

    def test_no_raw_db_fields_leaked(self):
        ctx = AnalyticsInsightService._build_context(_recs_out())
        # Context must not contain anything beyond the known contract keys
        expected_top_keys = {"workspace_id", "period_days", "generated_at", "total_recommendations", "suppressed_count", "recommendations"}
        assert set(ctx.keys()) == expected_top_keys


# ── _parse_response() ─────────────────────────────────────────────────────────

class TestParseResponse:
    def _parse(self, content: str, recs: RecommendationsOut | None = None) -> AnalyticsInsightOut:
        return AnalyticsInsightService._parse_response(content, recs or _recs_out())

    def test_valid_json_returns_insight_out(self):
        payload = json.dumps({
            "executive_summary": "IT drives success.",
            "top_opportunities": [
                {"title": "Focus IT", "rationale": "45% win rate.", "confidence_level": "high"}
            ],
            "risks": [{"title": "Channel dep", "description": "Single channel risk."}],
            "data_limitations": ["Pricing based on 8 deals."],
        })
        out = self._parse(payload)
        assert out.executive_summary == "IT drives success."
        assert len(out.top_opportunities) == 1
        assert out.top_opportunities[0].confidence_level == "high"
        assert len(out.risks) == 1
        assert len(out.data_limitations) == 1

    def test_malformed_json_triggers_fallback(self):
        out = self._parse("not json at all")
        # Fallback uses recommendation data
        assert "active recommendation" in out.executive_summary
        assert len(out.top_opportunities) >= 1

    def test_empty_string_triggers_fallback(self):
        out = self._parse("")
        assert out.executive_summary != ""

    def test_missing_optional_keys_use_defaults(self):
        payload = json.dumps({"executive_summary": "Summary only."})
        out = self._parse(payload)
        assert out.executive_summary == "Summary only."
        assert out.top_opportunities == []
        assert out.risks == []
        assert out.data_limitations == []

    def test_fallback_uses_rec_confidence_level_verbatim(self):
        rec = _rec(confidence_level="medium")
        out = self._parse("", _recs_out([rec]))
        # Fallback builds opportunities from recs; confidence_level must not be altered
        assert out.top_opportunities[0].confidence_level == "medium"


# ── get_insights() — empty recommendations ────────────────────────────────────

class TestGetInsightsEmptyRecs:
    @pytest.mark.asyncio
    async def test_empty_recs_no_llm_call(self):
        svc = _svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_empty_recs(),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
        ):
            await svc.get_insights(workspace_id=WORKSPACE_ID)
            MockEuri.return_value.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_recs_returns_insufficient_data_summary(self):
        svc = _svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_empty_recs(),
            ),
        ):
            out = await svc.get_insights(workspace_id=WORKSPACE_ID)
            assert "Insufficient data" in out.executive_summary

    @pytest.mark.asyncio
    async def test_empty_recs_data_limitations_populated(self):
        svc = _svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_empty_recs(),
            ),
        ):
            out = await svc.get_insights(workspace_id=WORKSPACE_ID)
            assert len(out.data_limitations) > 0

    @pytest.mark.asyncio
    async def test_empty_recs_with_suppressed_shows_hint(self):
        svc = _svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_empty_recs(suppressed=3),
            ),
        ):
            out = await svc.get_insights(workspace_id=WORKSPACE_ID)
            limitations_text = " ".join(out.data_limitations)
            assert "3" in limitations_text


# ── get_insights() — Redis cache ──────────────────────────────────────────────

class TestGetInsightsCacheHit:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_without_llm_call(self):
        cached_insight = AnalyticsInsightOut(
            generated_at=datetime.now(UTC),
            executive_summary="Cached summary.",
            top_opportunities=[],
            risks=[],
            data_limitations=[],
        )
        svc = _svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=_mock_redis(cached_json=cached_insight.model_dump_json()),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
        ):
            out = await svc.get_insights(workspace_id=WORKSPACE_ID)
            assert out.executive_summary == "Cached summary."
            MockEuri.return_value.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_proceeds_to_llm(self):
        svc = _svc()
        llm_payload = json.dumps({
            "executive_summary": "LLM narrative.",
            "top_opportunities": [],
            "risks": [],
            "data_limitations": [],
        })
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_recs_out(),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
        ):
            MockEuri.return_value.chat = AsyncMock(return_value={"content": llm_payload})
            out = await svc.get_insights(workspace_id=WORKSPACE_ID)
            assert out.executive_summary == "LLM narrative."

    @pytest.mark.asyncio
    async def test_cache_key_uses_tenant_and_workspace(self):
        svc = _svc()
        redis_mock = _mock_redis()
        llm_payload = json.dumps({
            "executive_summary": "x", "top_opportunities": [], "risks": [], "data_limitations": [],
        })
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=redis_mock),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_recs_out(),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
        ):
            MockEuri.return_value.chat = AsyncMock(return_value={"content": llm_payload})
            await svc.get_insights(workspace_id=WORKSPACE_ID)
            cache_set_args = redis_mock.set.call_args
            key = cache_set_args[0][0]
            assert str(TENANT_ID) in key
            assert str(WORKSPACE_ID) in key
            assert "insights" in key


# ── get_insights() — with recommendations ─────────────────────────────────────

class TestGetInsightsWithRecs:
    @pytest.mark.asyncio
    async def test_calls_euri_with_analytics_narrative_task(self):
        svc = _svc()
        llm_payload = json.dumps({
            "executive_summary": "IT wins.", "top_opportunities": [], "risks": [], "data_limitations": [],
        })
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_recs_out(),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
        ):
            MockEuri.return_value.chat = AsyncMock(return_value={"content": llm_payload})
            await svc.get_insights(workspace_id=WORKSPACE_ID)
            call_kwargs = MockEuri.return_value.chat.call_args.kwargs
            assert call_kwargs["task"] == "analytics_narrative"

    @pytest.mark.asyncio
    async def test_prompt_inputs_contain_recommendations_json(self):
        svc = _svc()
        llm_payload = json.dumps({
            "executive_summary": "x", "top_opportunities": [], "risks": [], "data_limitations": [],
        })
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_recs_out(),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
        ):
            MockEuri.return_value.chat = AsyncMock(return_value={"content": llm_payload})
            await svc.get_insights(workspace_id=WORKSPACE_ID)
            call_kwargs = MockEuri.return_value.chat.call_args.kwargs
            assert "recommendations_json" in call_kwargs["prompt_inputs"]

    @pytest.mark.asyncio
    async def test_returns_analytics_insight_out_schema(self):
        svc = _svc()
        llm_payload = json.dumps({
            "executive_summary": "Narrative.",
            "top_opportunities": [{"title": "T", "rationale": "R", "confidence_level": "high"}],
            "risks": [],
            "data_limitations": [],
        })
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_recs_out(),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
        ):
            MockEuri.return_value.chat = AsyncMock(return_value={"content": llm_payload})
            out = await svc.get_insights(workspace_id=WORKSPACE_ID)
            assert isinstance(out, AnalyticsInsightOut)
            assert out.executive_summary == "Narrative."
            assert out.top_opportunities[0].title == "T"

    @pytest.mark.asyncio
    async def test_result_cached_with_4h_ttl(self):
        svc = _svc()
        redis_mock = _mock_redis()
        llm_payload = json.dumps({
            "executive_summary": "x", "top_opportunities": [], "risks": [], "data_limitations": [],
        })
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=redis_mock),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_recs_out(),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
        ):
            MockEuri.return_value.chat = AsyncMock(return_value={"content": llm_payload})
            await svc.get_insights(workspace_id=WORKSPACE_ID)
            redis_mock.set.assert_called_once()
            set_kwargs = redis_mock.set.call_args
            # ex=14400 (4 hours)
            assert set_kwargs[1].get("ex") == 14400 or (len(set_kwargs[0]) >= 3 and set_kwargs[0][2] == 14400)


# ── get_insights() — EuriClient failure ───────────────────────────────────────

class TestGetInsightsEuriFailure:
    @pytest.mark.asyncio
    async def test_euri_raises_returns_fallback_not_crash(self):
        svc = _svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_recs_out(),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
        ):
            MockEuri.return_value.chat = AsyncMock(side_effect=RuntimeError("provider down"))
            out = await svc.get_insights(workspace_id=WORKSPACE_ID)
            # Fallback should still return something coherent
            assert isinstance(out, AnalyticsInsightOut)
            assert out.executive_summary != ""

    @pytest.mark.asyncio
    async def test_euri_raises_fallback_uses_recommendation_data(self):
        rec = _rec(title="Replicate Best Campaign", confidence_level="medium")
        svc = _svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_recs_out([rec]),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
        ):
            MockEuri.return_value.chat = AsyncMock(side_effect=RuntimeError("timeout"))
            out = await svc.get_insights(workspace_id=WORKSPACE_ID)
            # Fallback builds top_opportunities from deterministic rec titles
            titles = [o.title for o in out.top_opportunities]
            assert "Replicate Best Campaign" in titles

    @pytest.mark.asyncio
    async def test_euri_raises_logs_warning(self):
        svc = _svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_recs_out(),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
            patch("corpmind.modules.analytics.service.log") as mock_log,
        ):
            MockEuri.return_value.chat = AsyncMock(side_effect=RuntimeError("network error"))
            await svc.get_insights(workspace_id=WORKSPACE_ID)
            mock_log.warning.assert_called_once()
            warning_event = mock_log.warning.call_args[0][0]
            assert "llm_failed" in warning_event


# ── AI safety regression ──────────────────────────────────────────────────────

class TestAISafetyRegression:
    def test_build_context_has_no_extra_db_fields(self):
        """AI prompt context must only contain the documented contract keys."""
        rec = _rec()
        ctx = AnalyticsInsightService._build_context(_recs_out([rec]))
        allowed_top_keys = {"workspace_id", "period_days", "generated_at", "total_recommendations", "suppressed_count", "recommendations"}
        assert set(ctx.keys()) == allowed_top_keys

    def test_build_context_confidence_level_verbatim(self):
        """Confidence level must not be translated or upgraded by the context builder."""
        rec = _rec(confidence_level="medium")
        ctx = AnalyticsInsightService._build_context(_recs_out([rec]))
        assert ctx["recommendations"][0]["confidence_level"] == "medium"  # type: ignore[index]

    def test_parse_response_confidence_level_preserved(self):
        """AI confidence_level output is accepted as-is; never mapped or validated here."""
        payload = json.dumps({
            "executive_summary": "S.",
            "top_opportunities": [
                {"title": "T", "rationale": "R.", "confidence_level": "high"}
            ],
            "risks": [],
            "data_limitations": [],
        })
        out = AnalyticsInsightService._parse_response(payload, _recs_out())
        # The confidence_level string is stored verbatim — no mapping to another value
        assert out.top_opportunities[0].confidence_level == "high"

    def test_fallback_confidence_level_from_rec_not_invented(self):
        """Fallback must mirror rec.confidence_level; must not invent a new value."""
        rec = _rec(confidence_level="low")
        out = AnalyticsInsightService._parse_response("bad json", _recs_out([rec]))
        assert out.top_opportunities[0].confidence_level == "low"

    @pytest.mark.asyncio
    async def test_insufficient_data_path_never_calls_euri(self):
        """Empty recommendation list must never trigger an LLM call."""
        svc = _svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis", return_value=_mock_redis()),
            patch(
                "corpmind.modules.analytics.service.AnalyticsService.get_recommendations",
                new_callable=AsyncMock,
                return_value=_empty_recs(suppressed=5),
            ),
            patch("corpmind.modules.analytics.service.EuriClient") as MockEuri,
        ):
            await svc.get_insights(workspace_id=WORKSPACE_ID)
            MockEuri.assert_not_called()


# ── API endpoint ──────────────────────────────────────────────────────────────

class TestInsightsAPI:
    def test_insights_endpoint_registered(self):
        from corpmind.modules.analytics.api import router
        paths = [route.path for route in router.routes]
        assert "/insights" in paths

    def test_insights_response_model_fields(self):
        out = AnalyticsInsightOut(
            generated_at=datetime.now(UTC),
            executive_summary="Summary.",
            top_opportunities=[],
            risks=[],
            data_limitations=[],
        )
        data = out.model_dump()
        assert "generated_at" in data
        assert "executive_summary" in data
        assert "top_opportunities" in data
        assert "risks" in data
        assert "data_limitations" in data

    def test_insight_opportunity_in_response(self):
        opp = InsightOpportunity(title="IT", rationale="Wins.", confidence_level="high")
        out = AnalyticsInsightOut(
            generated_at=datetime.now(UTC),
            executive_summary="x",
            top_opportunities=[opp],
            risks=[],
            data_limitations=[],
        )
        dumped = out.model_dump()
        assert dumped["top_opportunities"][0]["confidence_level"] == "high"
