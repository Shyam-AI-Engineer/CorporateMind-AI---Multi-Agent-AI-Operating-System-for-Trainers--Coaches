"""Unit tests for LeadPipelineAnalyticsService — Sprint 40.

All DB interactions are mocked via AsyncMock; tests verify:
- summary counts and derived metrics
- stage analysis funnel math
- source and industry aggregation via raw SQL rows
- conversion funnel ratios
- Redis cache read/write/fallback
- tenant isolation (TenantContext respected)
- empty-state handling
- data integrity warning flag
- boundary / edge conditions
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.crm.service import (
    LeadPipelineAnalyticsService,
    _PIPELINE_TTL,
    _pipeline_conversion_key,
    _pipeline_industries_key,
    _pipeline_sources_key,
    _pipeline_stages_key,
    _pipeline_summary_key,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────

_ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_WS = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
_CTX = SimpleNamespace(org_id=_ORG)


def _row(**kwargs):
    """Build a lightweight row-like object from keyword args."""
    return SimpleNamespace(**kwargs)


def _svc(session=None):
    if session is None:
        session = AsyncMock()
    return LeadPipelineAnalyticsService(session)


@contextmanager
def _ctx_and_redis(redis_get=None, redis_set=None):
    """Patch TenantContext and Redis together."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=redis_get)
    mock_redis.set = AsyncMock(return_value=redis_set)
    with (
        patch("corpmind.modules.crm.service.get_tenant_context", return_value=_CTX),
        patch("corpmind.core.redis.get_redis", return_value=mock_redis),
    ):
        yield mock_redis


# ── Cache key helpers ──────────────────────────────────────────────────────────

class TestCacheKeys:
    def test_summary_key_format(self):
        k = _pipeline_summary_key(_ORG, _WS)
        assert f"t:{_ORG}:{_WS}:lead_pipeline_summary" == k

    def test_stages_key_format(self):
        k = _pipeline_stages_key(_ORG, _WS)
        assert f"t:{_ORG}:{_WS}:lead_pipeline_stages" == k

    def test_sources_key_format(self):
        k = _pipeline_sources_key(_ORG, _WS)
        assert f"t:{_ORG}:{_WS}:lead_pipeline_sources" == k

    def test_industries_key_format(self):
        k = _pipeline_industries_key(_ORG, _WS)
        assert f"t:{_ORG}:{_WS}:lead_pipeline_industries" == k

    def test_conversion_key_format(self):
        k = _pipeline_conversion_key(_ORG, _WS)
        assert f"t:{_ORG}:{_WS}:lead_pipeline_conversion" == k

    def test_different_workspaces_produce_different_keys(self):
        ws2 = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
        assert _pipeline_summary_key(_ORG, _WS) != _pipeline_summary_key(_ORG, ws2)

    def test_different_orgs_produce_different_keys(self):
        org2 = uuid.UUID("dddddddd-0000-0000-0000-000000000004")
        assert _pipeline_summary_key(_ORG, _WS) != _pipeline_summary_key(org2, _WS)

    def test_ttl_value(self):
        assert _PIPELINE_TTL == 900


# ── Summary ────────────────────────────────────────────────────────────────────

class TestSummary:
    def _stage_rows(self, stage_map: dict, bad_ts: int = 0):
        """Build mock rows for the stage-counts SQL query."""
        return [
            _row(stage=s, cnt=c, bad_ts=bad_ts if i == 0 else 0)
            for i, (s, c) in enumerate(stage_map.items())
        ]

    async def _run(self, session, stage_map, proposal_count=0):
        stage_rows = self._stage_rows(stage_map)
        proposal_row = _row(cnt=proposal_count)
        execute_mock = AsyncMock()
        execute_mock.fetchall = MagicMock(return_value=stage_rows)
        execute_mock.fetchone = MagicMock(return_value=proposal_row)
        call_count = 0

        async def fake_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            m = AsyncMock()
            if call_count == 1:
                m.fetchall = MagicMock(return_value=stage_rows)
            else:
                m.fetchone = MagicMock(return_value=proposal_row)
            return m

        session.execute = fake_execute
        with _ctx_and_redis():
            return await _svc(session).get_summary(_WS)

    @pytest.mark.asyncio
    async def test_total_leads_sums_all_stages(self):
        session = AsyncMock()
        r = await self._run(session, {"discovered": 5, "engaged": 3, "booked": 2, "lost": 1})
        assert r.total_leads == 11

    @pytest.mark.asyncio
    async def test_won_leads_is_booked_count(self):
        session = AsyncMock()
        r = await self._run(session, {"booked": 4, "discovered": 2})
        assert r.won_leads == 4

    @pytest.mark.asyncio
    async def test_lost_leads_is_lost_count(self):
        session = AsyncMock()
        r = await self._run(session, {"lost": 3, "discovered": 5})
        assert r.lost_leads == 3

    @pytest.mark.asyncio
    async def test_active_leads_excludes_booked_and_lost(self):
        session = AsyncMock()
        r = await self._run(
            session, {"discovered": 5, "engaged": 3, "booked": 2, "lost": 1}
        )
        assert r.active_leads == 8  # 5+3

    @pytest.mark.asyncio
    async def test_qualified_leads_is_meeting_completed(self):
        session = AsyncMock()
        r = await self._run(session, {"meeting_completed": 4, "booked": 2, "discovered": 1})
        assert r.qualified_leads == 4

    @pytest.mark.asyncio
    async def test_proposal_leads_from_join(self):
        session = AsyncMock()
        r = await self._run(session, {"discovered": 10}, proposal_count=3)
        assert r.proposal_leads == 3

    @pytest.mark.asyncio
    async def test_overall_conversion_rate_formula(self):
        session = AsyncMock()
        r = await self._run(session, {"discovered": 8, "booked": 2})  # 2/10 = 20%
        assert r.overall_conversion_rate == 20.0

    @pytest.mark.asyncio
    async def test_conversion_rate_zero_when_no_leads(self):
        session = AsyncMock()
        r = await self._run(session, {})
        assert r.overall_conversion_rate == 0.0

    @pytest.mark.asyncio
    async def test_pipeline_health_score_formula(self):
        # health = (won + qualified) / total * 100
        # 2 booked + 3 meeting_completed = 5 out of 10 → 50.0
        session = AsyncMock()
        r = await self._run(
            session, {"discovered": 5, "meeting_completed": 3, "booked": 2}
        )
        assert r.pipeline_health_score == 50.0

    @pytest.mark.asyncio
    async def test_pipeline_health_score_zero_when_no_leads(self):
        session = AsyncMock()
        r = await self._run(session, {})
        assert r.pipeline_health_score == 0.0

    @pytest.mark.asyncio
    async def test_data_integrity_warning_false_by_default(self):
        session = AsyncMock()
        r = await self._run(session, {"discovered": 5})
        assert r.data_integrity_warning is False

    @pytest.mark.asyncio
    async def test_data_integrity_warning_true_when_bad_timestamps(self):
        stage_rows = [_row(stage="discovered", cnt=3, bad_ts=1)]
        proposal_row = _row(cnt=0)

        async def fake_execute(stmt, params=None):
            m = AsyncMock()
            if not hasattr(fake_execute, "called"):
                fake_execute.called = True
                m.fetchall = MagicMock(return_value=stage_rows)
            else:
                m.fetchone = MagicMock(return_value=proposal_row)
            return m

        session = AsyncMock()
        session.execute = fake_execute
        with _ctx_and_redis():
            r = await _svc(session).get_summary(_WS)
        assert r.data_integrity_warning is True

    @pytest.mark.asyncio
    async def test_summary_returns_correct_schema_type(self):
        from corpmind.modules.crm.schemas import LeadPipelineSummaryOut

        session = AsyncMock()
        r = await self._run(session, {"discovered": 1})
        assert isinstance(r, LeadPipelineSummaryOut)

    @pytest.mark.asyncio
    async def test_summary_cache_hit_skips_db(self):
        from corpmind.modules.crm.schemas import LeadPipelineSummaryOut

        cached = LeadPipelineSummaryOut(
            total_leads=5,
            active_leads=3,
            qualified_leads=1,
            proposal_leads=0,
            won_leads=1,
            lost_leads=1,
            overall_conversion_rate=20.0,
            pipeline_health_score=40.0,
            data_integrity_warning=False,
        )
        session = AsyncMock()
        with _ctx_and_redis(redis_get=cached.model_dump_json()):
            r = await _svc(session).get_summary(_WS)
        session.execute.assert_not_called()
        assert r.total_leads == 5

    @pytest.mark.asyncio
    async def test_summary_written_to_cache(self):
        session = AsyncMock()

        async def fake_execute(stmt, params=None):
            m = AsyncMock()
            if not hasattr(fake_execute, "called"):
                fake_execute.called = True
                m.fetchall = MagicMock(return_value=[_row(stage="discovered", cnt=1, bad_ts=0)])
            else:
                m.fetchone = MagicMock(return_value=_row(cnt=0))
            return m

        session.execute = fake_execute
        with _ctx_and_redis() as redis:
            await _svc(session).get_summary(_WS)
        redis.set.assert_called_once()
        args = redis.set.call_args
        assert args[1]["ex"] == _PIPELINE_TTL

    @pytest.mark.asyncio
    async def test_redis_failure_does_not_raise(self):
        session = AsyncMock()

        async def fail_execute(stmt, params=None):
            m = AsyncMock()
            if not hasattr(fail_execute, "called"):
                fail_execute.called = True
                m.fetchall = MagicMock(return_value=[])
            else:
                m.fetchone = MagicMock(return_value=_row(cnt=0))
            return m

        session.execute = fail_execute
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("redis down"))
        mock_redis.set = AsyncMock(side_effect=Exception("redis down"))
        with (
            patch("corpmind.modules.crm.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.core.redis.get_redis", return_value=mock_redis),
        ):
            r = await _svc(session).get_summary(_WS)
        assert r.total_leads == 0


# ── Stage Analysis ─────────────────────────────────────────────────────────────

class TestStageAnalysis:
    def _make_session(self, stage_map: dict[str, int]):
        rows = [_row(stage=s, cnt=c, avg_days=float(c)) for s, c in stage_map.items()]
        session = AsyncMock()

        async def fake_execute(stmt, params=None):
            m = AsyncMock()
            m.fetchall = MagicMock(return_value=rows)
            return m

        session.execute = fake_execute
        return session

    @pytest.mark.asyncio
    async def test_returns_all_stages_including_lost(self):
        session = self._make_session({"discovered": 5, "lost": 2})
        with _ctx_and_redis():
            r = await _svc(session).get_stage_analysis(_WS)
        stages = [i.stage for i in r.items]
        assert "discovered" in stages
        assert "lost" in stages

    @pytest.mark.asyncio
    async def test_stage_order_follows_pipeline(self):
        session = self._make_session(
            {"booked": 1, "discovered": 3, "engaged": 2, "lost": 1}
        )
        with _ctx_and_redis():
            r = await _svc(session).get_stage_analysis(_WS)
        non_lost = [i.stage for i in r.items if i.stage != "lost"]
        assert non_lost[0] == "discovered"

    @pytest.mark.asyncio
    async def test_count_per_stage_correct(self):
        session = self._make_session({"discovered": 7, "engaged": 3, "lost": 2})
        with _ctx_and_redis():
            r = await _svc(session).get_stage_analysis(_WS)
        disc = next(i for i in r.items if i.stage == "discovered")
        assert disc.count == 7

    @pytest.mark.asyncio
    async def test_lost_count_included(self):
        session = self._make_session({"discovered": 5, "lost": 3})
        with _ctx_and_redis():
            r = await _svc(session).get_stage_analysis(_WS)
        lost = next(i for i in r.items if i.stage == "lost")
        assert lost.count == 3

    @pytest.mark.asyncio
    async def test_zero_count_stage_included_with_zero(self):
        session = self._make_session({"discovered": 5})
        with _ctx_and_redis():
            r = await _svc(session).get_stage_analysis(_WS)
        booked = next(i for i in r.items if i.stage == "booked")
        assert booked.count == 0

    @pytest.mark.asyncio
    async def test_conversion_rate_100_at_discovered(self):
        session = self._make_session({"discovered": 5, "engaged": 5})
        with _ctx_and_redis():
            r = await _svc(session).get_stage_analysis(_WS)
        disc = next(i for i in r.items if i.stage == "discovered")
        assert disc.conversion_rate == 100.0

    @pytest.mark.asyncio
    async def test_conversion_rate_decreases_along_funnel(self):
        session = self._make_session({"discovered": 10, "engaged": 5, "booked": 2})
        with _ctx_and_redis():
            r = await _svc(session).get_stage_analysis(_WS)
        disc = next(i for i in r.items if i.stage == "discovered")
        eng = next(i for i in r.items if i.stage == "engaged")
        assert disc.conversion_rate >= eng.conversion_rate

    @pytest.mark.asyncio
    async def test_drop_off_rate_100_for_booked_terminal(self):
        session = self._make_session({"booked": 3})
        with _ctx_and_redis():
            r = await _svc(session).get_stage_analysis(_WS)
        booked = next(i for i in r.items if i.stage == "booked")
        assert booked.drop_off_rate == 100.0

    @pytest.mark.asyncio
    async def test_lost_conversion_rate_always_zero(self):
        session = self._make_session({"discovered": 3, "lost": 2})
        with _ctx_and_redis():
            r = await _svc(session).get_stage_analysis(_WS)
        lost = next(i for i in r.items if i.stage == "lost")
        assert lost.conversion_rate == 0.0

    @pytest.mark.asyncio
    async def test_empty_data_returns_all_stages_zero(self):
        session = self._make_session({})
        with _ctx_and_redis():
            r = await _svc(session).get_stage_analysis(_WS)
        assert all(i.count == 0 for i in r.items)

    @pytest.mark.asyncio
    async def test_stage_analysis_cache_hit_skips_db(self):
        from corpmind.modules.crm.schemas import StageAnalysisOut

        cached = StageAnalysisOut(items=[])
        session = AsyncMock()
        with _ctx_and_redis(redis_get=cached.model_dump_json()):
            await _svc(session).get_stage_analysis(_WS)
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_stage_analysis_written_to_cache(self):
        session = self._make_session({"discovered": 2})
        with _ctx_and_redis() as redis:
            await _svc(session).get_stage_analysis(_WS)
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_average_days_non_negative(self):
        session = self._make_session({"discovered": 5, "engaged": 2})
        with _ctx_and_redis():
            r = await _svc(session).get_stage_analysis(_WS)
        for item in r.items:
            assert item.average_days >= 0.0


# ── Source Analysis ────────────────────────────────────────────────────────────

class TestSourceAnalysis:
    def _make_session(self, source_rows):
        session = AsyncMock()

        async def fake_execute(stmt, params=None):
            m = AsyncMock()
            m.fetchall = MagicMock(return_value=source_rows)
            return m

        session.execute = fake_execute
        return session

    @pytest.mark.asyncio
    async def test_source_items_returned(self):
        rows = [_row(source="webinar", lead_count=10, qualified=4, won=2)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_source_analysis(_WS)
        assert len(r.items) == 1
        assert r.items[0].source == "webinar"

    @pytest.mark.asyncio
    async def test_conversion_rate_formula(self):
        rows = [_row(source="cold_email", lead_count=20, qualified=8, won=4)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_source_analysis(_WS)
        assert r.items[0].conversion_rate == 20.0  # 4/20*100

    @pytest.mark.asyncio
    async def test_conversion_rate_zero_when_no_won(self):
        rows = [_row(source="referral", lead_count=5, qualified=2, won=0)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_source_analysis(_WS)
        assert r.items[0].conversion_rate == 0.0

    @pytest.mark.asyncio
    async def test_multiple_sources_returned(self):
        rows = [
            _row(source="webinar", lead_count=10, qualified=4, won=2),
            _row(source="referral", lead_count=5, qualified=3, won=3),
        ]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_source_analysis(_WS)
        assert len(r.items) == 2

    @pytest.mark.asyncio
    async def test_qualified_count_preserved(self):
        rows = [_row(source="event", lead_count=8, qualified=6, won=2)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_source_analysis(_WS)
        assert r.items[0].qualified == 6

    @pytest.mark.asyncio
    async def test_empty_source_returns_empty_list(self):
        session = self._make_session([])
        with _ctx_and_redis():
            r = await _svc(session).get_source_analysis(_WS)
        assert r.items == []

    @pytest.mark.asyncio
    async def test_unknown_source_coalesced(self):
        rows = [_row(source="unknown", lead_count=3, qualified=1, won=0)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_source_analysis(_WS)
        assert r.items[0].source == "unknown"

    @pytest.mark.asyncio
    async def test_source_cache_hit_skips_db(self):
        from corpmind.modules.crm.schemas import SourceAnalysisOut

        cached = SourceAnalysisOut(items=[])
        session = AsyncMock()
        with _ctx_and_redis(redis_get=cached.model_dump_json()):
            await _svc(session).get_source_analysis(_WS)
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_source_analysis_written_to_cache(self):
        session = self._make_session([_row(source="direct", lead_count=3, qualified=1, won=1)])
        with _ctx_and_redis() as redis:
            await _svc(session).get_source_analysis(_WS)
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_conversion_rate_rounded_to_2dp(self):
        rows = [_row(source="x", lead_count=3, qualified=1, won=1)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_source_analysis(_WS)
        assert r.items[0].conversion_rate == round(1 / 3 * 100, 2)


# ── Industry Analysis ──────────────────────────────────────────────────────────

class TestIndustryAnalysis:
    def _make_session(self, industry_rows):
        session = AsyncMock()

        async def fake_execute(stmt, params=None):
            m = AsyncMock()
            m.fetchall = MagicMock(return_value=industry_rows)
            return m

        session.execute = fake_execute
        return session

    @pytest.mark.asyncio
    async def test_industry_items_returned(self):
        rows = [_row(industry="SaaS", lead_count=8, won=3, avg_pipeline_days=12.5)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_industry_analysis(_WS)
        assert len(r.items) == 1
        assert r.items[0].industry == "SaaS"

    @pytest.mark.asyncio
    async def test_conversion_rate_per_industry(self):
        rows = [_row(industry="Finance", lead_count=10, won=5, avg_pipeline_days=8.0)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_industry_analysis(_WS)
        assert r.items[0].conversion_rate == 50.0

    @pytest.mark.asyncio
    async def test_average_pipeline_days_preserved(self):
        rows = [_row(industry="Retail", lead_count=4, won=1, avg_pipeline_days=21.7)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_industry_analysis(_WS)
        assert r.items[0].average_pipeline_days == 21.7

    @pytest.mark.asyncio
    async def test_null_avg_pipeline_days_defaults_to_zero(self):
        rows = [_row(industry="HR", lead_count=2, won=0, avg_pipeline_days=None)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_industry_analysis(_WS)
        assert r.items[0].average_pipeline_days == 0.0

    @pytest.mark.asyncio
    async def test_multiple_industries(self):
        rows = [
            _row(industry="SaaS", lead_count=8, won=3, avg_pipeline_days=12.5),
            _row(industry="Finance", lead_count=5, won=2, avg_pipeline_days=9.0),
        ]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_industry_analysis(_WS)
        assert len(r.items) == 2

    @pytest.mark.asyncio
    async def test_unknown_industry_coalesced(self):
        rows = [_row(industry="unknown", lead_count=3, won=0, avg_pipeline_days=5.0)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_industry_analysis(_WS)
        assert r.items[0].industry == "unknown"

    @pytest.mark.asyncio
    async def test_empty_returns_empty_list(self):
        session = self._make_session([])
        with _ctx_and_redis():
            r = await _svc(session).get_industry_analysis(_WS)
        assert r.items == []

    @pytest.mark.asyncio
    async def test_industry_cache_hit_skips_db(self):
        from corpmind.modules.crm.schemas import IndustryAnalysisOut

        cached = IndustryAnalysisOut(items=[])
        session = AsyncMock()
        with _ctx_and_redis(redis_get=cached.model_dump_json()):
            await _svc(session).get_industry_analysis(_WS)
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_industry_analysis_written_to_cache(self):
        session = self._make_session(
            [_row(industry="Tech", lead_count=4, won=2, avg_pipeline_days=7.0)]
        )
        with _ctx_and_redis() as redis:
            await _svc(session).get_industry_analysis(_WS)
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_conversion_rate_zero_when_no_won(self):
        rows = [_row(industry="NGO", lead_count=5, won=0, avg_pipeline_days=3.0)]
        session = self._make_session(rows)
        with _ctx_and_redis():
            r = await _svc(session).get_industry_analysis(_WS)
        assert r.items[0].conversion_rate == 0.0


# ── Conversion ─────────────────────────────────────────────────────────────────

class TestConversion:
    def _make_session(
        self,
        qualified=0,
        won=0,
        total=0,
        avg_days=0.0,
        proposal_leads=0,
        won_with_proposal=0,
    ):
        stage_row = _row(
            qualified_count=qualified,
            won_count=won,
            total_count=total,
            avg_days_to_win=avg_days,
        )
        proposal_row = _row(
            proposal_leads=proposal_leads, won_with_proposal=won_with_proposal
        )
        session = AsyncMock()
        call_n = 0

        async def fake_execute(stmt, params=None):
            nonlocal call_n
            call_n += 1
            m = AsyncMock()
            if call_n == 1:
                m.fetchone = MagicMock(return_value=stage_row)
            else:
                m.fetchone = MagicMock(return_value=proposal_row)
            return m

        session.execute = fake_execute
        return session

    @pytest.mark.asyncio
    async def test_overall_win_rate_formula(self):
        session = self._make_session(won=2, total=10)
        with _ctx_and_redis():
            r = await _svc(session).get_conversion(_WS)
        assert r.overall_win_rate == 20.0

    @pytest.mark.asyncio
    async def test_overall_win_rate_zero_when_no_total(self):
        session = self._make_session()
        with _ctx_and_redis():
            r = await _svc(session).get_conversion(_WS)
        assert r.overall_win_rate == 0.0

    @pytest.mark.asyncio
    async def test_qualified_to_proposal_formula(self):
        # 3 proposal_leads out of 6 qualified → 50%
        session = self._make_session(qualified=6, total=10, proposal_leads=3)
        with _ctx_and_redis():
            r = await _svc(session).get_conversion(_WS)
        assert r.qualified_to_proposal == 50.0

    @pytest.mark.asyncio
    async def test_qualified_to_proposal_zero_when_no_qualified(self):
        session = self._make_session(total=5)
        with _ctx_and_redis():
            r = await _svc(session).get_conversion(_WS)
        assert r.qualified_to_proposal == 0.0

    @pytest.mark.asyncio
    async def test_proposal_to_win_formula(self):
        # 2 won_with_proposal out of 4 proposal_leads → 50%
        session = self._make_session(
            qualified=4, total=10, proposal_leads=4, won_with_proposal=2
        )
        with _ctx_and_redis():
            r = await _svc(session).get_conversion(_WS)
        assert r.proposal_to_win == 50.0

    @pytest.mark.asyncio
    async def test_proposal_to_win_zero_when_no_proposals(self):
        session = self._make_session(total=5, qualified=2)
        with _ctx_and_redis():
            r = await _svc(session).get_conversion(_WS)
        assert r.proposal_to_win == 0.0

    @pytest.mark.asyncio
    async def test_average_days_to_win_preserved(self):
        session = self._make_session(won=3, total=10, avg_days=14.5)
        with _ctx_and_redis():
            r = await _svc(session).get_conversion(_WS)
        assert r.average_days_to_win == 14.5

    @pytest.mark.asyncio
    async def test_null_avg_days_defaults_to_zero(self):
        session = self._make_session(won=0, total=5)
        with _ctx_and_redis():
            r = await _svc(session).get_conversion(_WS)
        assert r.average_days_to_win == 0.0

    @pytest.mark.asyncio
    async def test_conversion_cache_hit_skips_db(self):
        from corpmind.modules.crm.schemas import LeadConversionOut

        cached = LeadConversionOut(
            qualified_to_proposal=50.0,
            proposal_to_win=25.0,
            overall_win_rate=10.0,
            average_days_to_win=12.0,
        )
        session = AsyncMock()
        with _ctx_and_redis(redis_get=cached.model_dump_json()):
            r = await _svc(session).get_conversion(_WS)
        session.execute.assert_not_called()
        assert r.qualified_to_proposal == 50.0

    @pytest.mark.asyncio
    async def test_conversion_written_to_cache(self):
        session = self._make_session(won=1, total=5, qualified=2)
        with _ctx_and_redis() as redis:
            await _svc(session).get_conversion(_WS)
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_rates_zero_when_empty(self):
        session = self._make_session()
        with _ctx_and_redis():
            r = await _svc(session).get_conversion(_WS)
        assert r.overall_win_rate == 0.0
        assert r.qualified_to_proposal == 0.0
        assert r.proposal_to_win == 0.0
        assert r.average_days_to_win == 0.0


# ── Tenant Isolation ───────────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_summary_uses_tenant_context_org_id(self):
        org_b = uuid.UUID("eeeeeeee-0000-0000-0000-000000000005")
        ctx_b = SimpleNamespace(org_id=org_b)

        captured_params = {}
        session = AsyncMock()
        call_n = 0

        async def fake_execute(stmt, params=None):
            nonlocal call_n
            call_n += 1
            if call_n == 1:
                captured_params.update(params or {})
            m = AsyncMock()
            if call_n == 1:
                m.fetchall = MagicMock(return_value=[])
            else:
                m.fetchone = MagicMock(return_value=_row(cnt=0))
            return m

        session.execute = fake_execute
        with (
            patch("corpmind.modules.crm.service.get_tenant_context", return_value=ctx_b),
            patch("corpmind.core.redis.get_redis", return_value=AsyncMock(
                get=AsyncMock(return_value=None),
                set=AsyncMock(),
            )),
        ):
            await _svc(session).get_summary(_WS)
        assert captured_params.get("tenant_id") == org_b

    @pytest.mark.asyncio
    async def test_stage_analysis_uses_tenant_context(self):
        org_b = uuid.UUID("eeeeeeee-0000-0000-0000-000000000006")
        ctx_b = SimpleNamespace(org_id=org_b)
        captured = {}
        session = AsyncMock()

        async def fake_execute(stmt, params=None):
            captured.update(params or {})
            m = AsyncMock()
            m.fetchall = MagicMock(return_value=[])
            return m

        session.execute = fake_execute
        with (
            patch("corpmind.modules.crm.service.get_tenant_context", return_value=ctx_b),
            patch("corpmind.core.redis.get_redis", return_value=AsyncMock(
                get=AsyncMock(return_value=None), set=AsyncMock(),
            )),
        ):
            await _svc(session).get_stage_analysis(_WS)
        assert captured.get("tenant_id") == org_b

    @pytest.mark.asyncio
    async def test_cache_keys_scoped_to_tenant(self):
        org_a = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
        org_b = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
        ws = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
        assert _pipeline_summary_key(org_a, ws) != _pipeline_summary_key(org_b, ws)

    @pytest.mark.asyncio
    async def test_source_analysis_uses_tenant_context(self):
        org_b = uuid.UUID("ffffffff-0000-0000-0000-000000000007")
        ctx_b = SimpleNamespace(org_id=org_b)
        captured = {}
        session = AsyncMock()

        async def fake_execute(stmt, params=None):
            captured.update(params or {})
            m = AsyncMock()
            m.fetchall = MagicMock(return_value=[])
            return m

        session.execute = fake_execute
        with (
            patch("corpmind.modules.crm.service.get_tenant_context", return_value=ctx_b),
            patch("corpmind.core.redis.get_redis", return_value=AsyncMock(
                get=AsyncMock(return_value=None), set=AsyncMock(),
            )),
        ):
            await _svc(session).get_source_analysis(_WS)
        assert captured.get("tenant_id") == org_b


# ── Edge conditions ────────────────────────────────────────────────────────────

class TestEdgeConditions:
    @pytest.mark.asyncio
    async def test_100_percent_win_rate(self):
        stage_rows = [_row(stage="booked", cnt=10, bad_ts=0)]
        proposal_row = _row(cnt=5)
        session = AsyncMock()
        call_n = 0

        async def fake_execute(stmt, params=None):
            nonlocal call_n
            call_n += 1
            m = AsyncMock()
            if call_n == 1:
                m.fetchall = MagicMock(return_value=stage_rows)
            else:
                m.fetchone = MagicMock(return_value=proposal_row)
            return m

        session.execute = fake_execute
        with _ctx_and_redis():
            r = await _svc(session).get_summary(_WS)
        assert r.overall_conversion_rate == 100.0

    @pytest.mark.asyncio
    async def test_100_percent_lost(self):
        stage_rows = [_row(stage="lost", cnt=5, bad_ts=0)]
        proposal_row = _row(cnt=0)
        session = AsyncMock()
        call_n = 0

        async def fake_execute(stmt, params=None):
            nonlocal call_n
            call_n += 1
            m = AsyncMock()
            if call_n == 1:
                m.fetchall = MagicMock(return_value=stage_rows)
            else:
                m.fetchone = MagicMock(return_value=proposal_row)
            return m

        session.execute = fake_execute
        with _ctx_and_redis():
            r = await _svc(session).get_summary(_WS)
        assert r.won_leads == 0
        assert r.lost_leads == 5
        assert r.overall_conversion_rate == 0.0

    @pytest.mark.asyncio
    async def test_single_lead_booked(self):
        stage_rows = [_row(stage="booked", cnt=1, bad_ts=0)]
        proposal_row = _row(cnt=0)
        session = AsyncMock()
        call_n = 0

        async def fake_execute(stmt, params=None):
            nonlocal call_n
            call_n += 1
            m = AsyncMock()
            if call_n == 1:
                m.fetchall = MagicMock(return_value=stage_rows)
            else:
                m.fetchone = MagicMock(return_value=proposal_row)
            return m

        session.execute = fake_execute
        with _ctx_and_redis():
            r = await _svc(session).get_summary(_WS)
        assert r.won_leads == 1
        assert r.total_leads == 1
        assert r.overall_conversion_rate == 100.0

    @pytest.mark.asyncio
    async def test_pipeline_health_score_capped_at_100(self):
        # won + qualified = total → 100.0
        stage_rows = [
            _row(stage="booked", cnt=5, bad_ts=0),
            _row(stage="meeting_completed", cnt=5, bad_ts=0),
        ]
        proposal_row = _row(cnt=0)
        session = AsyncMock()
        call_n = 0

        async def fake_execute(stmt, params=None):
            nonlocal call_n
            call_n += 1
            m = AsyncMock()
            if call_n == 1:
                m.fetchall = MagicMock(return_value=stage_rows)
            else:
                m.fetchone = MagicMock(return_value=proposal_row)
            return m

        session.execute = fake_execute
        with _ctx_and_redis():
            r = await _svc(session).get_summary(_WS)
        assert r.pipeline_health_score <= 100.0

    @pytest.mark.asyncio
    async def test_conversion_rate_rounded_to_2dp(self):
        session = AsyncMock()
        call_n = 0

        async def fake_execute(stmt, params=None):
            nonlocal call_n
            call_n += 1
            m = AsyncMock()
            if call_n == 1:
                m.fetchone = MagicMock(return_value=_row(
                    qualified_count=3, won_count=1, total_count=3, avg_days_to_win=None
                ))
            else:
                m.fetchone = MagicMock(return_value=_row(
                    proposal_leads=0, won_with_proposal=0
                ))
            return m

        session.execute = fake_execute
        with _ctx_and_redis():
            r = await _svc(session).get_conversion(_WS)
        assert r.overall_win_rate == round(1 / 3 * 100, 2)

    @pytest.mark.asyncio
    async def test_multiple_integrity_violations_still_true(self):
        stage_rows = [
            _row(stage="discovered", cnt=3, bad_ts=2),
            _row(stage="engaged", cnt=2, bad_ts=1),
        ]
        proposal_row = _row(cnt=0)
        session = AsyncMock()
        call_n = 0

        async def fake_execute(stmt, params=None):
            nonlocal call_n
            call_n += 1
            m = AsyncMock()
            if call_n == 1:
                m.fetchall = MagicMock(return_value=stage_rows)
            else:
                m.fetchone = MagicMock(return_value=proposal_row)
            return m

        session.execute = fake_execute
        with _ctx_and_redis():
            r = await _svc(session).get_summary(_WS)
        assert r.data_integrity_warning is True


# ── Schema correctness ────────────────────────────────────────────────────────

class TestSchemas:
    def test_summary_all_fields(self):
        from corpmind.modules.crm.schemas import LeadPipelineSummaryOut
        s = LeadPipelineSummaryOut(
            total_leads=10, active_leads=6, qualified_leads=2,
            proposal_leads=1, won_leads=2, lost_leads=2,
            overall_conversion_rate=20.0, pipeline_health_score=40.0,
            data_integrity_warning=False,
        )
        assert s.total_leads == 10

    def test_stage_item_fields(self):
        from corpmind.modules.crm.schemas import StageAnalysisItem
        item = StageAnalysisItem(stage="engaged", count=5, average_days=3.2,
                                 conversion_rate=75.0, drop_off_rate=25.0)
        assert item.stage == "engaged" and item.drop_off_rate == 25.0

    def test_source_item_fields(self):
        from corpmind.modules.crm.schemas import SourceAnalysisItem
        item = SourceAnalysisItem(source="webinar", lead_count=10, qualified=5,
                                  won=2, conversion_rate=20.0)
        assert item.qualified == 5 and item.won == 2

    def test_industry_item_avg_days(self):
        from corpmind.modules.crm.schemas import IndustryAnalysisItem
        item = IndustryAnalysisItem(industry="SaaS", lead_count=8, won=3,
                                    conversion_rate=37.5, average_pipeline_days=12.5)
        assert item.average_pipeline_days == 12.5

    def test_conversion_fields(self):
        from corpmind.modules.crm.schemas import LeadConversionOut
        c = LeadConversionOut(qualified_to_proposal=50.0, proposal_to_win=40.0,
                              overall_win_rate=20.0, average_days_to_win=14.0)
        assert c.qualified_to_proposal == 50.0 and c.average_days_to_win == 14.0

    def test_stage_analysis_out_empty(self):
        from corpmind.modules.crm.schemas import StageAnalysisOut
        assert StageAnalysisOut(items=[]).items == []

    def test_source_analysis_out_empty(self):
        from corpmind.modules.crm.schemas import SourceAnalysisOut
        assert SourceAnalysisOut(items=[]).items == []

    def test_industry_analysis_out_empty(self):
        from corpmind.modules.crm.schemas import IndustryAnalysisOut
        assert IndustryAnalysisOut(items=[]).items == []

    def test_summary_integrity_true(self):
        from corpmind.modules.crm.schemas import LeadPipelineSummaryOut
        s = LeadPipelineSummaryOut(
            total_leads=0, active_leads=0, qualified_leads=0,
            proposal_leads=0, won_leads=0, lost_leads=0,
            overall_conversion_rate=0.0, pipeline_health_score=0.0,
            data_integrity_warning=True,
        )
        assert s.data_integrity_warning is True

    def test_conversion_proposal_to_win(self):
        from corpmind.modules.crm.schemas import LeadConversionOut
        c = LeadConversionOut(qualified_to_proposal=30.0, proposal_to_win=66.67,
                              overall_win_rate=20.0, average_days_to_win=10.0)
        assert c.proposal_to_win == 66.67


# ── Stage extra ───────────────────────────────────────────────────────────────

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from types import SimpleNamespace

_ORG2 = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_WS2 = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
_CTX2 = SimpleNamespace(org_id=_ORG2)


def _row2(**kw):
    return SimpleNamespace(**kw)


from contextlib import contextmanager

@contextmanager
def _ctx2(redis_get=None):
    r = AsyncMock()
    r.get = AsyncMock(return_value=redis_get)
    r.set = AsyncMock()
    with (
        patch("corpmind.modules.crm.service.get_tenant_context", return_value=_CTX2),
        patch("corpmind.core.redis.get_redis", return_value=r),
    ):
        yield r


from corpmind.modules.crm.service import LeadPipelineAnalyticsService as _Svc2


def _svc2(session=None):
    return _Svc2(session or AsyncMock())


class TestStageExtra:
    def _sess(self, stage_map):
        rows = [_row2(stage=s, cnt=c, avg_days=float(c)) for s, c in stage_map.items()]
        session = AsyncMock()
        async def fe(stmt, params=None):
            m = AsyncMock()
            m.fetchall = MagicMock(return_value=rows)
            return m
        session.execute = fe
        return session

    @pytest.mark.asyncio
    async def test_always_6_items(self):
        with _ctx2():
            r = await _svc2(self._sess({"discovered": 3})).get_stage_analysis(_WS2)
        assert len(r.items) == 6

    @pytest.mark.asyncio
    async def test_lost_drop_off_100_when_present(self):
        with _ctx2():
            r = await _svc2(self._sess({"lost": 5})).get_stage_analysis(_WS2)
        assert next(i for i in r.items if i.stage == "lost").drop_off_rate == 100.0

    @pytest.mark.asyncio
    async def test_lost_drop_off_0_when_absent(self):
        with _ctx2():
            r = await _svc2(self._sess({"discovered": 3})).get_stage_analysis(_WS2)
        assert next(i for i in r.items if i.stage == "lost").drop_off_rate == 0.0

    @pytest.mark.asyncio
    async def test_meeting_scheduled_included(self):
        with _ctx2():
            r = await _svc2(self._sess({"meeting_scheduled": 2})).get_stage_analysis(_WS2)
        assert any(i.stage == "meeting_scheduled" for i in r.items)

    @pytest.mark.asyncio
    async def test_avg_days_preserved(self):
        rows = [_row2(stage="engaged", cnt=4, avg_days=7.5)]
        session = AsyncMock()
        async def fe(stmt, params=None):
            m = AsyncMock()
            m.fetchall = MagicMock(return_value=rows)
            return m
        session.execute = fe
        with _ctx2():
            r = await _svc2(session).get_stage_analysis(_WS2)
        assert next(i for i in r.items if i.stage == "engaged").average_days == 7.5

    @pytest.mark.asyncio
    async def test_redis_down_still_works(self):
        rows = [_row2(stage="discovered", cnt=2, avg_days=1.0)]
        session = AsyncMock()
        async def fe(stmt, params=None):
            m = AsyncMock()
            m.fetchall = MagicMock(return_value=rows)
            return m
        session.execute = fe
        bad_redis = AsyncMock()
        bad_redis.get = AsyncMock(side_effect=Exception("down"))
        bad_redis.set = AsyncMock(side_effect=Exception("down"))
        with (
            patch("corpmind.modules.crm.service.get_tenant_context", return_value=_CTX2),
            patch("corpmind.core.redis.get_redis", return_value=bad_redis),
        ):
            r = await _svc2(session).get_stage_analysis(_WS2)
        assert next(i for i in r.items if i.stage == "discovered").count == 2


# ── Summary extra ─────────────────────────────────────────────────────────────

class TestSummaryExtra:
    def _exec(self, stage_rows, cnt=0):
        pr = _row2(cnt=cnt)
        session = AsyncMock()
        n = 0
        async def fe(stmt, params=None):
            nonlocal n
            n += 1
            m = AsyncMock()
            if n == 1:
                m.fetchall = MagicMock(return_value=stage_rows)
            else:
                m.fetchone = MagicMock(return_value=pr)
            return m
        session.execute = fe
        return session

    @pytest.mark.asyncio
    async def test_active_zero_all_terminal(self):
        session = self._exec([
            _row2(stage="booked", cnt=3, bad_ts=0),
            _row2(stage="lost", cnt=2, bad_ts=0),
        ])
        with _ctx2():
            assert (await _svc2(session).get_summary(_WS2)).active_leads == 0

    @pytest.mark.asyncio
    async def test_qualified_zero_without_meeting_completed(self):
        session = self._exec([_row2(stage="engaged", cnt=4, bad_ts=0)])
        with _ctx2():
            assert (await _svc2(session).get_summary(_WS2)).qualified_leads == 0

    @pytest.mark.asyncio
    async def test_large_pipeline_total(self):
        session = self._exec([
            _row2(stage="discovered", cnt=100, bad_ts=0),
            _row2(stage="engaged", cnt=60, bad_ts=0),
            _row2(stage="meeting_completed", cnt=15, bad_ts=0),
            _row2(stage="booked", cnt=8, bad_ts=0),
            _row2(stage="lost", cnt=20, bad_ts=0),
        ], cnt=12)
        with _ctx2():
            r = await _svc2(session).get_summary(_WS2)
        assert r.total_leads == 203 and r.won_leads == 8

    @pytest.mark.asyncio
    async def test_conversion_rate_1_in_3(self):
        session = self._exec([
            _row2(stage="discovered", cnt=2, bad_ts=0),
            _row2(stage="booked", cnt=1, bad_ts=0),
        ])
        with _ctx2():
            r = await _svc2(session).get_summary(_WS2)
        assert r.overall_conversion_rate == round(1 / 3 * 100, 2)

    @pytest.mark.asyncio
    async def test_proposal_leads_propagated(self):
        session = self._exec([_row2(stage="discovered", cnt=5, bad_ts=0)], cnt=3)
        with _ctx2():
            assert (await _svc2(session).get_summary(_WS2)).proposal_leads == 3
