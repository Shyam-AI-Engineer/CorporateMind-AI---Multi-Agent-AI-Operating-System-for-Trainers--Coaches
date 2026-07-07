"""Unit tests for ExecutiveDashboardService — Sprint 50.

All tests mock ExecutiveDashboardRepo so no DB or Redis required.
Covers: cache keys, health score computation, KPI building, alert building,
get_kpis, get_summary, get_alerts, get_trends, get_dashboard, tenant isolation,
schema validation, graceful Redis degradation.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.executive_dashboard.repo import RawAlertData, RawKPIData, RawTrendPoint
from corpmind.modules.executive_dashboard.schemas import (
    ExecutiveAlertOut,
    ExecutiveDashboardOut,
    ExecutiveKPIsOut,
    ExecutiveSummaryOut,
    ExecutiveTrendOut,
)
from corpmind.modules.executive_dashboard.service import (
    ExecutiveDashboardService,
    _alerts_key,
    _dashboard_key,
    _kpis_key,
    _trends_key,
    build_alerts,
    build_kpis,
    compute_health_score,
)

_PATCH_CTX = "corpmind.modules.executive_dashboard.service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.executive_dashboard.service.get_redis"

_ORG = uuid.uuid4()
_WID = uuid.uuid4()
_ORG2 = uuid.uuid4()
_WID2 = uuid.uuid4()


# ── Test fixtures ──────────────────────────────────────────────────────────────


def _ctx(org_id: uuid.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id or _ORG
    return ctx


def _redis(cached: str | None = None) -> MagicMock:
    r = MagicMock()
    r.get = AsyncMock(return_value=cached)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    return r


@contextmanager
def _patch(
    ctx: MagicMock | None = None, redis: MagicMock | None = None
) -> Generator[None, None, None]:
    with patch(_PATCH_CTX, return_value=ctx or _ctx()):
        with patch(_PATCH_REDIS, return_value=redis or _redis()):
            yield


def _make_svc() -> tuple[ExecutiveDashboardService, MagicMock]:
    db = MagicMock()
    svc = ExecutiveDashboardService(db)
    svc._repo = MagicMock()
    return svc, db


def _raw_kpi(**kw: object) -> RawKPIData:
    defaults: dict[str, object] = {
        "total_leads": 10,
        "active_customers": 5,
        "renewals_due": 2,
        "customer_health_distribution": {"healthy": 3, "at_risk": 1, "watch": 1},
        "total_training_engagements": 4,
        "completed_training_engagements": 3,
        "total_certificate_eligible": 10,
        "total_certificates_issued": 8,
        "avg_feedback_rating": 4.2,
        "total_workflow_runs": 6,
        "completed_workflow_runs": 4,
        "open_operations_tasks": 3,
    }
    defaults.update(kw)
    return RawKPIData(**defaults)  # type: ignore[arg-type]


def _raw_alert(**kw: object) -> RawAlertData:
    defaults: dict[str, object] = {
        "renewals_overdue": [],
        "customers_at_risk_ids": [],
        "training_overdue_ids": [],
        "workflow_backlog_ids": [],
        "operations_backlog_ids": [],
        "low_feedback_session_ids": [],
    }
    defaults.update(kw)
    return RawAlertData(**defaults)  # type: ignore[arg-type]


def _raw_trend(date: str = "2026-07-07") -> RawTrendPoint:
    return RawTrendPoint(
        date=date,
        leads_created=2,
        customers_created=1,
        training_completions=3,
        renewals_processed=0,
    )


# ══════════════════════════════════════════════════════════════════════════════
# TestCacheKeys
# ══════════════════════════════════════════════════════════════════════════════


class TestCacheKeys:
    def test_dashboard_key_format(self) -> None:
        k = _dashboard_key(_ORG, _WID)
        assert k == f"exec_dashboard:{_ORG}:{_WID}"

    def test_kpis_key_format(self) -> None:
        k = _kpis_key(_ORG, _WID)
        assert k == f"exec_kpis:{_ORG}:{_WID}"

    def test_alerts_key_format(self) -> None:
        k = _alerts_key(_ORG, _WID)
        assert k == f"exec_alerts:{_ORG}:{_WID}"

    def test_trends_key_includes_days(self) -> None:
        k30 = _trends_key(_ORG, _WID, 30)
        k90 = _trends_key(_ORG, _WID, 90)
        k365 = _trends_key(_ORG, _WID, 365)
        assert "30" in k30
        assert "90" in k90
        assert "365" in k365

    def test_different_orgs_produce_different_keys(self) -> None:
        k1 = _kpis_key(_ORG, _WID)
        k2 = _kpis_key(_ORG2, _WID)
        assert k1 != k2

    def test_different_workspaces_produce_different_keys(self) -> None:
        k1 = _kpis_key(_ORG, _WID)
        k2 = _kpis_key(_ORG, _WID2)
        assert k1 != k2

    def test_alerts_and_kpis_keys_differ(self) -> None:
        assert _alerts_key(_ORG, _WID) != _kpis_key(_ORG, _WID)

    def test_dashboard_and_kpis_keys_differ(self) -> None:
        assert _dashboard_key(_ORG, _WID) != _kpis_key(_ORG, _WID)


# ══════════════════════════════════════════════════════════════════════════════
# TestComputeHealthScore
# ══════════════════════════════════════════════════════════════════════════════


class TestComputeHealthScore:
    def test_zero_data_returns_fifty(self) -> None:
        raw = RawKPIData()
        assert compute_health_score(raw) == 50

    def test_full_training_completion_adds_twenty(self) -> None:
        raw = RawKPIData(
            total_training_engagements=4,
            completed_training_engagements=4,
        )
        score = compute_health_score(raw)
        assert score == 70  # 50 + 20

    def test_partial_training_adds_proportional_points(self) -> None:
        raw = RawKPIData(
            total_training_engagements=4,
            completed_training_engagements=2,
        )
        score = compute_health_score(raw)
        assert score == 60  # 50 + 10

    def test_perfect_feedback_adds_twenty(self) -> None:
        raw = RawKPIData(avg_feedback_rating=5.0)
        assert compute_health_score(raw) == 70  # 50 + 20

    def test_zero_feedback_adds_nothing(self) -> None:
        raw = RawKPIData(avg_feedback_rating=0.0)
        assert compute_health_score(raw) == 50

    def test_none_feedback_adds_nothing(self) -> None:
        raw = RawKPIData(avg_feedback_rating=None)
        assert compute_health_score(raw) == 50

    def test_all_customers_at_risk_penalises_twenty(self) -> None:
        raw = RawKPIData(customer_health_distribution={"at_risk": 5})
        score = compute_health_score(raw)
        assert score == 30  # 50 - 20

    def test_no_at_risk_customers_no_penalty(self) -> None:
        raw = RawKPIData(customer_health_distribution={"healthy": 10})
        assert compute_health_score(raw) == 50

    def test_full_workflow_completion_adds_ten(self) -> None:
        raw = RawKPIData(total_workflow_runs=5, completed_workflow_runs=5)
        assert compute_health_score(raw) == 60

    def test_score_clamped_to_100(self) -> None:
        raw = RawKPIData(
            total_training_engagements=1,
            completed_training_engagements=1,
            avg_feedback_rating=5.0,
            total_workflow_runs=1,
            completed_workflow_runs=1,
        )
        assert compute_health_score(raw) == 100

    def test_score_clamped_to_zero(self) -> None:
        raw = RawKPIData(
            avg_feedback_rating=0.0,
            customer_health_distribution={"at_risk": 100},
        )
        score = compute_health_score(raw)
        assert score >= 0

    def test_score_is_integer(self) -> None:
        raw = _raw_kpi()
        assert isinstance(compute_health_score(raw), int)

    def test_mixed_health_distribution_partial_penalty(self) -> None:
        raw = RawKPIData(
            customer_health_distribution={"healthy": 5, "at_risk": 5}
        )
        score = compute_health_score(raw)
        assert score == 40  # 50 - 10 (50% at risk)


# ══════════════════════════════════════════════════════════════════════════════
# TestBuildKPIs
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildKPIs:
    def test_returns_executive_kpis_out(self) -> None:
        raw = _raw_kpi()
        result = build_kpis(raw)
        assert isinstance(result, ExecutiveKPIsOut)

    def test_total_leads_propagated(self) -> None:
        raw = _raw_kpi(total_leads=42)
        assert build_kpis(raw).total_leads == 42

    def test_active_customers_propagated(self) -> None:
        raw = _raw_kpi(active_customers=17)
        assert build_kpis(raw).active_customers == 17

    def test_renewals_due_propagated(self) -> None:
        raw = _raw_kpi(renewals_due=3)
        assert build_kpis(raw).renewals_due == 3

    def test_training_completion_rate_zero_when_no_engagements(self) -> None:
        raw = _raw_kpi(total_training_engagements=0, completed_training_engagements=0)
        assert build_kpis(raw).training_completion_rate == 0.0

    def test_training_completion_rate_calculated(self) -> None:
        raw = _raw_kpi(total_training_engagements=4, completed_training_engagements=3)
        assert build_kpis(raw).training_completion_rate == 0.75

    def test_cert_rate_zero_when_no_eligible(self) -> None:
        raw = _raw_kpi(total_certificate_eligible=0, total_certificates_issued=0)
        assert build_kpis(raw).certificate_issuance_rate == 0.0

    def test_cert_rate_calculated(self) -> None:
        raw = _raw_kpi(total_certificate_eligible=10, total_certificates_issued=8)
        assert build_kpis(raw).certificate_issuance_rate == 0.8

    def test_avg_feedback_none_when_no_feedback(self) -> None:
        raw = _raw_kpi(avg_feedback_rating=None)
        assert build_kpis(raw).avg_feedback_rating is None

    def test_avg_feedback_rounded(self) -> None:
        raw = _raw_kpi(avg_feedback_rating=4.1666)
        assert build_kpis(raw).avg_feedback_rating == 4.17

    def test_health_distribution_propagated(self) -> None:
        dist = {"healthy": 5, "at_risk": 2}
        raw = _raw_kpi(customer_health_distribution=dist)
        assert build_kpis(raw).customer_health_distribution == dist

    def test_workflow_rate_zero_when_no_runs(self) -> None:
        raw = _raw_kpi(total_workflow_runs=0, completed_workflow_runs=0)
        assert build_kpis(raw).workflow_completion_rate == 0.0

    def test_workflow_rate_calculated(self) -> None:
        raw = _raw_kpi(total_workflow_runs=10, completed_workflow_runs=7)
        assert build_kpis(raw).workflow_completion_rate == 0.7

    def test_open_tasks_propagated(self) -> None:
        raw = _raw_kpi(open_operations_tasks=12)
        assert build_kpis(raw).open_operations_tasks == 12

    def test_health_score_included(self) -> None:
        raw = _raw_kpi()
        kpis = build_kpis(raw)
        assert 0 <= kpis.business_health_score <= 100

    def test_rates_have_4_decimal_places_max(self) -> None:
        raw = _raw_kpi(total_training_engagements=3, completed_training_engagements=1)
        kpis = build_kpis(raw)
        assert len(str(kpis.training_completion_rate).rstrip("0").split(".")[-1]) <= 4

    def test_empty_raw_produces_zero_kpis(self) -> None:
        raw = RawKPIData()
        kpis = build_kpis(raw)
        assert kpis.total_leads == 0
        assert kpis.active_customers == 0
        assert kpis.training_completion_rate == 0.0

    def test_full_completion_rates_are_one(self) -> None:
        raw = _raw_kpi(
            total_training_engagements=5,
            completed_training_engagements=5,
            total_certificate_eligible=5,
            total_certificates_issued=5,
            total_workflow_runs=5,
            completed_workflow_runs=5,
        )
        kpis = build_kpis(raw)
        assert kpis.training_completion_rate == 1.0
        assert kpis.certificate_issuance_rate == 1.0
        assert kpis.workflow_completion_rate == 1.0


# ══════════════════════════════════════════════════════════════════════════════
# TestBuildAlerts
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildAlerts:
    def test_empty_raw_returns_empty_list(self) -> None:
        assert build_alerts(_raw_alert()) == []

    def test_renewals_overdue_produces_critical_alert(self) -> None:
        raw = _raw_alert(renewals_overdue=["id1", "id2"])
        alerts = build_alerts(raw)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "renewals_overdue"
        assert alerts[0].severity == "critical"

    def test_renewals_overdue_count_matches(self) -> None:
        raw = _raw_alert(renewals_overdue=["id1", "id2", "id3"])
        alerts = build_alerts(raw)
        assert alerts[0].count == 3

    def test_customers_at_risk_produces_critical_alert(self) -> None:
        raw = _raw_alert(customers_at_risk_ids=["cid1"])
        alerts = build_alerts(raw)
        assert alerts[0].severity == "critical"
        assert alerts[0].alert_type == "customers_at_risk"

    def test_training_overdue_produces_warning_alert(self) -> None:
        raw = _raw_alert(training_overdue_ids=["tid1"])
        alerts = build_alerts(raw)
        assert alerts[0].severity == "warning"
        assert alerts[0].alert_type == "training_overdue"

    def test_workflow_backlog_produces_warning_alert(self) -> None:
        raw = _raw_alert(workflow_backlog_ids=["wid1", "wid2"])
        alerts = build_alerts(raw)
        assert alerts[0].severity == "warning"
        assert alerts[0].alert_type == "workflow_backlog"

    def test_operations_backlog_produces_warning_alert(self) -> None:
        raw = _raw_alert(operations_backlog_ids=["oid1"])
        alerts = build_alerts(raw)
        assert alerts[0].severity == "warning"
        assert alerts[0].alert_type == "operations_backlog"

    def test_low_feedback_produces_info_alert(self) -> None:
        raw = _raw_alert(low_feedback_session_ids=["sid1"])
        alerts = build_alerts(raw)
        assert alerts[0].severity == "info"
        assert alerts[0].alert_type == "low_feedback_scores"

    def test_all_alerts_present_when_all_populated(self) -> None:
        raw = _raw_alert(
            renewals_overdue=["r1"],
            customers_at_risk_ids=["c1"],
            training_overdue_ids=["t1"],
            workflow_backlog_ids=["w1"],
            operations_backlog_ids=["o1"],
            low_feedback_session_ids=["s1"],
        )
        alerts = build_alerts(raw)
        assert len(alerts) == 6

    def test_affected_ids_capped_at_20(self) -> None:
        ids = [str(i) for i in range(30)]
        raw = _raw_alert(renewals_overdue=ids)
        alerts = build_alerts(raw)
        assert len(alerts[0].affected_ids) == 20

    def test_alert_has_non_empty_title(self) -> None:
        raw = _raw_alert(renewals_overdue=["r1"])
        alerts = build_alerts(raw)
        assert len(alerts[0].title) > 0

    def test_alert_has_non_empty_description(self) -> None:
        raw = _raw_alert(renewals_overdue=["r1"])
        alerts = build_alerts(raw)
        assert "1" in alerts[0].description

    def test_alert_description_includes_count(self) -> None:
        ids = ["id1", "id2", "id3"]
        raw = _raw_alert(renewals_overdue=ids)
        alerts = build_alerts(raw)
        assert "3" in alerts[0].description

    def test_two_critical_alerts_ordering(self) -> None:
        raw = _raw_alert(renewals_overdue=["r1"], customers_at_risk_ids=["c1"])
        alerts = build_alerts(raw)
        assert alerts[0].alert_type == "renewals_overdue"
        assert alerts[1].alert_type == "customers_at_risk"

    def test_alert_affected_ids_match_input(self) -> None:
        raw = _raw_alert(customers_at_risk_ids=["cid-1", "cid-2"])
        alerts = build_alerts(raw)
        assert "cid-1" in alerts[0].affected_ids
        assert "cid-2" in alerts[0].affected_ids

    def test_zero_count_empty_list_no_alert(self) -> None:
        raw = _raw_alert(renewals_overdue=[])
        assert build_alerts(raw) == []

    def test_each_alert_type_in_list(self) -> None:
        raw = _raw_alert(
            renewals_overdue=["r1"],
            customers_at_risk_ids=["c1"],
            training_overdue_ids=["t1"],
            workflow_backlog_ids=["w1"],
            operations_backlog_ids=["o1"],
            low_feedback_session_ids=["s1"],
        )
        types = {a.alert_type for a in build_alerts(raw)}
        assert "renewals_overdue" in types
        assert "customers_at_risk" in types
        assert "training_overdue" in types
        assert "workflow_backlog" in types
        assert "operations_backlog" in types
        assert "low_feedback_scores" in types

    def test_all_alerts_are_executive_alert_out_instances(self) -> None:
        raw = _raw_alert(renewals_overdue=["r1"], customers_at_risk_ids=["c1"])
        for alert in build_alerts(raw):
            assert isinstance(alert, ExecutiveAlertOut)


# ══════════════════════════════════════════════════════════════════════════════
# TestGetKPIs
# ══════════════════════════════════════════════════════════════════════════════


class TestGetKPIs:
    @pytest.mark.asyncio
    async def test_cache_miss_fetches_repo(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        with _patch():
            result = await svc.get_kpis(_WID)
        assert isinstance(result, ExecutiveKPIsOut)
        svc._repo.fetch_kpis.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_repo(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        cached_kpis = build_kpis(_raw_kpi())
        redis = _redis(cached=cached_kpis.model_dump_json())
        with _patch(redis=redis):
            result = await svc.get_kpis(_WID)
        svc._repo.fetch_kpis.assert_not_awaited()
        assert result.total_leads == cached_kpis.total_leads

    @pytest.mark.asyncio
    async def test_cache_writes_after_repo_fetch(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        redis = _redis()
        with _patch(redis=redis):
            await svc.get_kpis(_WID)
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redis_get_failure_falls_through_to_repo(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("Redis down"))
        redis.set = AsyncMock()
        with _patch(redis=redis):
            result = await svc.get_kpis(_WID)
        assert isinstance(result, ExecutiveKPIsOut)

    @pytest.mark.asyncio
    async def test_redis_set_failure_does_not_raise(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        redis = _redis()
        redis.set = AsyncMock(side_effect=Exception("Redis down"))
        with _patch(redis=redis):
            result = await svc.get_kpis(_WID)
        assert isinstance(result, ExecutiveKPIsOut)

    @pytest.mark.asyncio
    async def test_zero_leads_returns_zero(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi(total_leads=0))
        with _patch():
            result = await svc.get_kpis(_WID)
        assert result.total_leads == 0

    @pytest.mark.asyncio
    async def test_kpis_business_health_score_in_range(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        with _patch():
            result = await svc.get_kpis(_WID)
        assert 0 <= result.business_health_score <= 100

    @pytest.mark.asyncio
    async def test_different_workspace_ids_produce_different_cache_keys(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        redis = _redis()
        with _patch(redis=redis):
            await svc.get_kpis(_WID)
            await svc.get_kpis(_WID2)
        assert redis.get.await_count == 2
        calls = [str(c) for c in redis.get.await_args_list]
        assert calls[0] != calls[1]

    @pytest.mark.asyncio
    async def test_tenant_context_org_id_used_in_cache_key(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        redis = _redis()
        ctx = _ctx(org_id=_ORG2)
        with _patch(ctx=ctx, redis=redis):
            await svc.get_kpis(_WID)
        key_used = redis.get.await_args[0][0]
        assert str(_ORG2) in key_used

    @pytest.mark.asyncio
    async def test_cache_key_contains_workspace_id(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        redis = _redis()
        with _patch(redis=redis):
            await svc.get_kpis(_WID)
        key_used = redis.get.await_args[0][0]
        assert str(_WID) in key_used

    @pytest.mark.asyncio
    async def test_returns_executive_kpis_out_type(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        with _patch():
            result = await svc.get_kpis(_WID)
        assert isinstance(result, ExecutiveKPIsOut)


# ══════════════════════════════════════════════════════════════════════════════
# TestGetSummary
# ══════════════════════════════════════════════════════════════════════════════


class TestGetSummary:
    @pytest.mark.asyncio
    async def test_returns_executive_summary_out(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        with _patch():
            result = await svc.get_summary(_WID)
        assert isinstance(result, ExecutiveSummaryOut)

    @pytest.mark.asyncio
    async def test_summary_total_leads_matches_kpis(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi(total_leads=99))
        with _patch():
            result = await svc.get_summary(_WID)
        assert result.total_leads == 99

    @pytest.mark.asyncio
    async def test_summary_active_customers_matches_kpis(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi(active_customers=7))
        with _patch():
            result = await svc.get_summary(_WID)
        assert result.active_customers == 7

    @pytest.mark.asyncio
    async def test_summary_renewals_due_matches_kpis(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi(renewals_due=4))
        with _patch():
            result = await svc.get_summary(_WID)
        assert result.renewals_due == 4

    @pytest.mark.asyncio
    async def test_summary_open_tasks_matches_kpis(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi(open_operations_tasks=11))
        with _patch():
            result = await svc.get_summary(_WID)
        assert result.open_operations_tasks == 11

    @pytest.mark.asyncio
    async def test_summary_health_score_in_range(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        with _patch():
            result = await svc.get_summary(_WID)
        assert 0 <= result.business_health_score <= 100

    @pytest.mark.asyncio
    async def test_summary_zero_everything(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=RawKPIData())
        with _patch():
            result = await svc.get_summary(_WID)
        assert result.total_leads == 0
        assert result.active_customers == 0

    @pytest.mark.asyncio
    async def test_summary_calls_get_kpis_internally(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        with _patch():
            await svc.get_summary(_WID)
        svc._repo.fetch_kpis.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# TestGetAlerts
# ══════════════════════════════════════════════════════════════════════════════


class TestGetAlerts:
    @pytest.mark.asyncio
    async def test_cache_miss_fetches_repo(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        with _patch():
            result = await svc.get_alerts(_WID)
        assert isinstance(result, list)
        svc._repo.fetch_alerts.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_alerts_on_clean_data(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        with _patch():
            result = await svc.get_alerts(_WID)
        assert result == []

    @pytest.mark.asyncio
    async def test_cache_hit_returns_alerts(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        cached_alerts = build_alerts(_raw_alert(renewals_overdue=["r1"]))
        redis = _redis(cached=json.dumps([a.model_dump() for a in cached_alerts]))
        with _patch(redis=redis):
            result = await svc.get_alerts(_WID)
        svc._repo.fetch_alerts.assert_not_awaited()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_cache_written_after_repo_fetch(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert(renewals_overdue=["r1"]))
        redis = _redis()
        with _patch(redis=redis):
            await svc.get_alerts(_WID)
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redis_failure_falls_through(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=RuntimeError("fail"))
        redis.set = AsyncMock()
        with _patch(redis=redis):
            result = await svc.get_alerts(_WID)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_all_alert_types_returned(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_alerts = AsyncMock(
            return_value=_raw_alert(
                renewals_overdue=["r1"],
                customers_at_risk_ids=["c1"],
                training_overdue_ids=["t1"],
                workflow_backlog_ids=["w1"],
                operations_backlog_ids=["o1"],
                low_feedback_session_ids=["s1"],
            )
        )
        with _patch():
            result = await svc.get_alerts(_WID)
        assert len(result) == 6

    @pytest.mark.asyncio
    async def test_alerts_are_executive_alert_out_instances(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_alerts = AsyncMock(
            return_value=_raw_alert(renewals_overdue=["r1"])
        )
        with _patch():
            result = await svc.get_alerts(_WID)
        assert all(isinstance(a, ExecutiveAlertOut) for a in result)

    @pytest.mark.asyncio
    async def test_cache_key_contains_workspace(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        redis = _redis()
        with _patch(redis=redis):
            await svc.get_alerts(_WID)
        key = redis.get.await_args[0][0]
        assert str(_WID) in key

    @pytest.mark.asyncio
    async def test_redis_set_failure_does_not_raise(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        redis = _redis()
        redis.set = AsyncMock(side_effect=Exception("boom"))
        with _patch(redis=redis):
            result = await svc.get_alerts(_WID)
        assert isinstance(result, list)


# ══════════════════════════════════════════════════════════════════════════════
# TestGetTrends
# ══════════════════════════════════════════════════════════════════════════════


class TestGetTrends:
    @pytest.mark.asyncio
    async def test_cache_miss_fetches_repo(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[_raw_trend()])
        with _patch():
            result = await svc.get_trends(_WID, days=30)
        assert len(result) == 1
        svc._repo.fetch_trends.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_list_of_executive_trend_out(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[_raw_trend(), _raw_trend("2026-07-06")])
        with _patch():
            result = await svc.get_trends(_WID, days=30)
        assert all(isinstance(t, ExecutiveTrendOut) for t in result)

    @pytest.mark.asyncio
    async def test_default_days_is_30(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            await svc.get_trends(_WID)
        call_args = svc._repo.fetch_trends.await_args[0]
        assert 30 in call_args

    @pytest.mark.asyncio
    async def test_invalid_days_defaults_to_30(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            await svc.get_trends(_WID, days=999)
        call_args = svc._repo.fetch_trends.await_args[0]
        assert 30 in call_args

    @pytest.mark.asyncio
    async def test_days_90_valid(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            await svc.get_trends(_WID, days=90)
        call_args = svc._repo.fetch_trends.await_args[0]
        assert 90 in call_args

    @pytest.mark.asyncio
    async def test_days_365_valid(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            await svc.get_trends(_WID, days=365)
        call_args = svc._repo.fetch_trends.await_args[0]
        assert 365 in call_args

    @pytest.mark.asyncio
    async def test_cache_hit_skips_repo(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[_raw_trend()])
        cached = [ExecutiveTrendOut(date="2026-07-07", leads_created=5)]
        redis = _redis(cached=json.dumps([t.model_dump() for t in cached]))
        with _patch(redis=redis):
            result = await svc.get_trends(_WID, days=30)
        svc._repo.fetch_trends.assert_not_awaited()
        assert result[0].leads_created == 5

    @pytest.mark.asyncio
    async def test_cache_written_after_repo_fetch(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[_raw_trend()])
        redis = _redis()
        with _patch(redis=redis):
            await svc.get_trends(_WID, days=30)
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_key_contains_days(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        redis = _redis()
        with _patch(redis=redis):
            await svc.get_trends(_WID, days=90)
        key = redis.get.await_args[0][0]
        assert "90" in key

    @pytest.mark.asyncio
    async def test_trend_fields_mapped_correctly(self) -> None:
        svc, _ = _make_svc()
        pt = RawTrendPoint(
            date="2026-07-01",
            leads_created=3,
            customers_created=1,
            training_completions=5,
            renewals_processed=2,
        )
        svc._repo.fetch_trends = AsyncMock(return_value=[pt])
        with _patch():
            result = await svc.get_trends(_WID, days=30)
        assert result[0].date == "2026-07-01"
        assert result[0].leads_created == 3
        assert result[0].customers_created == 1
        assert result[0].training_completions == 5
        assert result[0].renewals_processed == 2

    @pytest.mark.asyncio
    async def test_redis_failure_falls_through(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[_raw_trend()])
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("err"))
        redis.set = AsyncMock()
        with _patch(redis=redis):
            result = await svc.get_trends(_WID, days=30)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_trends_when_repo_returns_empty(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            result = await svc.get_trends(_WID, days=30)
        assert result == []

    @pytest.mark.asyncio
    async def test_different_days_use_different_cache_keys(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        redis = _redis()
        with _patch(redis=redis):
            await svc.get_trends(_WID, days=30)
            await svc.get_trends(_WID, days=90)
        keys = [str(c) for c in redis.get.await_args_list]
        assert keys[0] != keys[1]


# ══════════════════════════════════════════════════════════════════════════════
# TestGetDashboard
# ══════════════════════════════════════════════════════════════════════════════


class TestGetDashboard:
    @pytest.mark.asyncio
    async def test_returns_executive_dashboard_out(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[_raw_trend()])
        with _patch():
            result = await svc.get_dashboard(_WID)
        assert isinstance(result, ExecutiveDashboardOut)

    @pytest.mark.asyncio
    async def test_all_three_repo_methods_called(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            await svc.get_dashboard(_WID)
        svc._repo.fetch_kpis.assert_awaited_once()
        svc._repo.fetch_alerts.assert_awaited_once()
        svc._repo.fetch_trends.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_repo(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        cached_dashboard = ExecutiveDashboardOut(
            summary=ExecutiveSummaryOut(),
            kpis=ExecutiveKPIsOut(),
            alerts=[],
            trends_30d=[],
            workspace_id=str(_WID),
            generated_at="2026-07-07T00:00:00+00:00",
        )
        redis = _redis(cached=cached_dashboard.model_dump_json())
        with _patch(redis=redis):
            result = await svc.get_dashboard(_WID)
        svc._repo.fetch_kpis.assert_not_awaited()
        assert isinstance(result, ExecutiveDashboardOut)

    @pytest.mark.asyncio
    async def test_cache_written_after_gather(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        redis = _redis()
        with _patch(redis=redis):
            await svc.get_dashboard(_WID)
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dashboard_summary_populated(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi(total_leads=55))
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            result = await svc.get_dashboard(_WID)
        assert result.summary.total_leads == 55

    @pytest.mark.asyncio
    async def test_dashboard_kpis_populated(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi(active_customers=20))
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            result = await svc.get_dashboard(_WID)
        assert result.kpis.active_customers == 20

    @pytest.mark.asyncio
    async def test_dashboard_alerts_populated(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(
            return_value=_raw_alert(renewals_overdue=["r1"])
        )
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            result = await svc.get_dashboard(_WID)
        assert len(result.alerts) == 1

    @pytest.mark.asyncio
    async def test_dashboard_trends_30d_populated(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[_raw_trend()])
        with _patch():
            result = await svc.get_dashboard(_WID)
        assert len(result.trends_30d) == 1

    @pytest.mark.asyncio
    async def test_dashboard_workspace_id_in_response(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            result = await svc.get_dashboard(_WID)
        assert result.workspace_id == str(_WID)

    @pytest.mark.asyncio
    async def test_dashboard_generated_at_is_iso_string(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            result = await svc.get_dashboard(_WID)
        # Must be parseable ISO timestamp
        assert "T" in result.generated_at

    @pytest.mark.asyncio
    async def test_redis_failure_falls_through_to_gather(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("Redis down"))
        redis.set = AsyncMock()
        with _patch(redis=redis):
            result = await svc.get_dashboard(_WID)
        assert isinstance(result, ExecutiveDashboardOut)
        svc._repo.fetch_kpis.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_trends_always_fetched_with_30_days(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            await svc.get_dashboard(_WID)
        call_args = svc._repo.fetch_trends.await_args[0]
        assert 30 in call_args

    @pytest.mark.asyncio
    async def test_redis_set_failure_does_not_raise(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        redis = _redis()
        redis.set = AsyncMock(side_effect=Exception("boom"))
        with _patch(redis=redis):
            result = await svc.get_dashboard(_WID)
        assert isinstance(result, ExecutiveDashboardOut)

    @pytest.mark.asyncio
    async def test_dashboard_trends_30d_is_list(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        with _patch():
            result = await svc.get_dashboard(_WID)
        assert isinstance(result.trends_30d, list)

    @pytest.mark.asyncio
    async def test_dashboard_cache_key_contains_workspace(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        svc._repo.fetch_trends = AsyncMock(return_value=[])
        redis = _redis()
        with _patch(redis=redis):
            await svc.get_dashboard(_WID)
        key = redis.get.await_args[0][0]
        assert str(_WID) in key


# ══════════════════════════════════════════════════════════════════════════════
# TestTenantIsolation
# ══════════════════════════════════════════════════════════════════════════════


class TestTenantIsolation:
    def test_kpis_key_different_for_different_orgs(self) -> None:
        k1 = _kpis_key(_ORG, _WID)
        k2 = _kpis_key(_ORG2, _WID)
        assert k1 != k2

    def test_alerts_key_different_for_different_orgs(self) -> None:
        k1 = _alerts_key(_ORG, _WID)
        k2 = _alerts_key(_ORG2, _WID)
        assert k1 != k2

    def test_trends_key_different_for_different_orgs(self) -> None:
        k1 = _trends_key(_ORG, _WID, 30)
        k2 = _trends_key(_ORG2, _WID, 30)
        assert k1 != k2

    def test_dashboard_key_different_for_different_orgs(self) -> None:
        k1 = _dashboard_key(_ORG, _WID)
        k2 = _dashboard_key(_ORG2, _WID)
        assert k1 != k2

    @pytest.mark.asyncio
    async def test_different_orgs_different_cache_keys_for_kpis(self) -> None:
        svc1, _ = _make_svc()
        svc1._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        svc2, _ = _make_svc()
        svc2._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        redis1 = _redis()
        redis2 = _redis()
        with _patch(ctx=_ctx(_ORG), redis=redis1):
            await svc1.get_kpis(_WID)
        with _patch(ctx=_ctx(_ORG2), redis=redis2):
            await svc2.get_kpis(_WID)
        key1 = redis1.get.await_args[0][0]
        key2 = redis2.get.await_args[0][0]
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_different_orgs_fetch_repo_independently(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        ctx1 = _ctx(_ORG)
        ctx2 = _ctx(_ORG2)
        with _patch(ctx=ctx1):
            r1 = await svc.get_kpis(_WID)
        with _patch(ctx=ctx2):
            r2 = await svc.get_kpis(_WID)
        assert svc._repo.fetch_kpis.await_count == 2

    def test_all_four_key_prefixes_distinct(self) -> None:
        prefixes = {
            _kpis_key(_ORG, _WID).split(":")[0],
            _alerts_key(_ORG, _WID).split(":")[0],
            _trends_key(_ORG, _WID, 30).split(":")[0],
            _dashboard_key(_ORG, _WID).split(":")[0],
        }
        assert len(prefixes) == 4

    @pytest.mark.asyncio
    async def test_org_id_propagated_to_repo_for_kpis(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=_raw_kpi())
        ctx = _ctx(_ORG2)
        with _patch(ctx=ctx):
            await svc.get_kpis(_WID)
        call_args = svc._repo.fetch_kpis.await_args[0]
        assert _ORG2 in call_args

    @pytest.mark.asyncio
    async def test_org_id_propagated_to_repo_for_alerts(self) -> None:
        svc, _ = _make_svc()
        svc._repo.fetch_alerts = AsyncMock(return_value=_raw_alert())
        ctx = _ctx(_ORG2)
        with _patch(ctx=ctx):
            await svc.get_alerts(_WID)
        call_args = svc._repo.fetch_alerts.await_args[0]
        assert _ORG2 in call_args


# ══════════════════════════════════════════════════════════════════════════════
# TestSchemas
# ══════════════════════════════════════════════════════════════════════════════


class TestSchemas:
    def test_executive_kpis_default_fields(self) -> None:
        kpis = ExecutiveKPIsOut()
        assert kpis.total_leads == 0
        assert kpis.avg_feedback_rating is None
        assert kpis.customer_health_distribution == {}

    def test_executive_summary_default_fields(self) -> None:
        s = ExecutiveSummaryOut()
        assert s.total_leads == 0
        assert s.business_health_score == 0

    def test_executive_alert_required_fields(self) -> None:
        a = ExecutiveAlertOut(
            alert_type="renewals_overdue",
            severity="critical",
            title="Test",
            description="Desc",
            count=1,
        )
        assert a.affected_ids == []

    def test_executive_trend_default_counts_zero(self) -> None:
        t = ExecutiveTrendOut(date="2026-07-07")
        assert t.leads_created == 0
        assert t.renewals_processed == 0

    def test_executive_dashboard_out_has_all_sections(self) -> None:
        d = ExecutiveDashboardOut(
            summary=ExecutiveSummaryOut(),
            kpis=ExecutiveKPIsOut(),
            alerts=[],
            trends_30d=[],
            workspace_id=str(_WID),
            generated_at="2026-07-07T00:00:00+00:00",
        )
        assert hasattr(d, "summary")
        assert hasattr(d, "kpis")
        assert hasattr(d, "alerts")
        assert hasattr(d, "trends_30d")

    def test_kpis_serializes_to_json(self) -> None:
        kpis = build_kpis(_raw_kpi())
        json_str = kpis.model_dump_json()
        assert "total_leads" in json_str

    def test_alert_serializes_to_dict(self) -> None:
        alert = ExecutiveAlertOut(
            alert_type="test",
            severity="info",
            title="T",
            description="D",
            count=0,
        )
        d = alert.model_dump()
        assert d["alert_type"] == "test"

    def test_trend_date_field_is_string(self) -> None:
        t = ExecutiveTrendOut(date="2026-07-01")
        assert isinstance(t.date, str)

    def test_kpis_health_distribution_is_dict(self) -> None:
        kpis = build_kpis(_raw_kpi(customer_health_distribution={"healthy": 3}))
        assert isinstance(kpis.customer_health_distribution, dict)

    def test_dashboard_out_model_dump_json(self) -> None:
        d = ExecutiveDashboardOut(
            summary=ExecutiveSummaryOut(),
            kpis=ExecutiveKPIsOut(),
            alerts=[],
            trends_30d=[],
            workspace_id=str(_WID),
            generated_at="2026-07-07T00:00:00+00:00",
        )
        json_str = d.model_dump_json()
        assert "workspace_id" in json_str

    def test_kpis_roundtrip_json(self) -> None:
        kpis = build_kpis(_raw_kpi())
        roundtripped = ExecutiveKPIsOut.model_validate_json(kpis.model_dump_json())
        assert roundtripped.total_leads == kpis.total_leads
        assert roundtripped.business_health_score == kpis.business_health_score

    def test_alerts_roundtrip_json(self) -> None:
        alerts = build_alerts(_raw_alert(renewals_overdue=["r1"]))
        serialized = json.dumps([a.model_dump() for a in alerts])
        roundtripped = [ExecutiveAlertOut.model_validate(a) for a in json.loads(serialized)]
        assert roundtripped[0].alert_type == "renewals_overdue"
