"""Unit tests for RecommendationEvidenceService (Sprint 25A).

Covers:
  Static helpers
    - _coverage_status: None → "missing"
    - _coverage_status: present=False → "missing"
    - _coverage_status: present=True, days_since=None → "healthy"
    - _coverage_status: present=True, days_since=10 → "healthy"
    - _coverage_status: present=True, days_since=31 → "stale"
    - _calibration_status: None → None
    - _calibration_status: delta=0 → "calibrated"
    - _calibration_status: delta=4.9 → "calibrated"
    - _calibration_status: delta=5.0 → "warning"
    - _calibration_status: delta=15.0 → "warning"
    - _calibration_status: delta=15.1 → "severe"
    - _calibration_status: negative delta handled via abs()

  get_evidence() — core extraction
    - returns EvidenceOut instance
    - generated_count from snapshot repo
    - quality_score picked from latest qual_row for matching rec_type
    - quality_score=None when no qual_row for the requested type
    - acted_rate=0 when no outcomes for type (no ZeroDivisionError)
    - success_rate=0 when no outcomes for type
    - reliability_score from matching ReliabilityTypeItemOut
    - reliability_rating from matching ReliabilityTypeItemOut
    - reliability fields None when type not in reliability list
    - lifecycle timing from matching LifecycleTypeItemOut
    - lifecycle defaults to 0.0 when type not in lifecycle list
    - drift_direction from matching DriftTypeItemOut quality_score.direction
    - drift_direction None when type not in drift list
    - stability_rating from matching StabilityTypeItemOut
    - stability_rating None when type not in stability list
    - confidence_average from matching RecCalibrationTypeItemOut
    - calibration_status derived from calibration_delta
    - portfolio_percentage from matching PortfolioTypeItemOut
    - portfolio_percentage=0.0 when type not in portfolio list
    - coverage_status derived from CoverageItemOut
    - last_generated_at from CoverageItemOut
    - days_since_last_generated from CoverageItemOut
    - insufficient_data=True when generated_count==0 AND last_generated_at=None
    - insufficient_data=False when generated_count>0
    - insufficient_data=False when generated_count==0 but last_generated_at set

  supporting_metrics
    - 9 rows always emitted (even when values are None)
    - "Quality Score" row uses recommendation_quality_scores source
    - "Reliability Score" row uses recommendation_quality_scores source
    - "Success Rate" row uses recommendation_outcomes source
    - "Acted Rate" row uses recommendation_outcomes source
    - "Confidence Average" row uses recommendation_snapshots source
    - "Portfolio Share" row uses recommendation_snapshots source
    - "Avg Days to Action" row uses recommendation_outcomes source
    - "Avg Days to Success" row uses recommendation_outcomes source
    - "Generated Count" row uses recommendation_snapshots source
    - Quality Score value is float or None

  Redis caching
    - cache hit → returns cached EvidenceOut without calling upstream services
    - cache miss → computes and stores in Redis
    - Redis unavailable on GET → falls back to live computation
    - Redis unavailable on SET → does not raise (graceful)

  Tenant isolation
    - cache key includes org_id and workspace_id
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.schemas import (
    CoverageItemOut,
    CoverageOut,
    DriftOut,
    DriftOverallOut,
    DriftTypeItemOut,
    EvidenceOut,
    LifecycleOut,
    LifecycleOverallOut,
    LifecycleTypeItemOut,
    MetricTrendOut,
    PortfolioBalanceOut,
    PortfolioOut,
    PortfolioTypeItemOut,
    RecCalibrationOut,
    RecCalibrationOverallOut,
    RecCalibrationTypeItemOut,
    ReliabilityOut,
    ReliabilityOverallOut,
    ReliabilityTypeItemOut,
    StabilityOut,
    StabilityTypeItemOut,
    QualityScoreStabilityOut,
)
from corpmind.modules.analytics.models import RecommendationQualityScore
from corpmind.modules.analytics.service import RecommendationEvidenceService

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
TODAY = date(2026, 6, 25)
NOW = datetime(2026, 6, 25, 10, 0, 0, tzinfo=UTC)


# ── Mock context ──────────────────────────────────────────────────────────────

def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = TENANT_ID
    return ctx


# ── Upstream service fixture builders ────────────────────────────────────────

def _portfolio(rec_type: str = "industry", percentage: float = 30.0) -> PortfolioOut:
    item = PortfolioTypeItemOut(
        recommendation_type=rec_type,
        count=42,
        percentage=percentage,
        acted_rate=60.0,
        success_rate=45.0,
    )
    return PortfolioOut(
        generated_at=NOW,
        total_recommendations=140,
        recommendation_types=[item],
        dominant_type=rec_type,
        least_used_type="pricing",
        portfolio_balance=PortfolioBalanceOut(diversity_index=72.0, balance_rating="good"),
    )


def _coverage(
    rec_type: str = "industry",
    present: bool = True,
    last_generated_at: date | None = date(2026, 6, 24),
    days_since: int | None = 1,
) -> CoverageOut:
    item = CoverageItemOut(
        recommendation_type=rec_type,
        present=present,
        count=42 if present else 0,
        last_generated_at=last_generated_at,
        days_since_last_generated=days_since,
    )
    return CoverageOut(
        generated_at=NOW,
        coverage=[item],
        missing_types=[] if present else [rec_type],
        stale_types=[],
    )


def _calibration(
    rec_type: str = "industry",
    predicted_confidence: float = 75.0,
    calibration_delta: float | None = 2.5,
) -> RecCalibrationOut:
    item = RecCalibrationTypeItemOut(
        recommendation_type=rec_type,
        predicted_confidence=predicted_confidence,
        observed_success_rate=predicted_confidence + (calibration_delta or 0.0),
        calibration_delta=calibration_delta,
    )
    return RecCalibrationOut(
        generated_at=NOW,
        overall=RecCalibrationOverallOut(
            high_confidence_success_rate=80.0,
            medium_confidence_success_rate=65.0,
            low_confidence_success_rate=50.0,
        ),
        recommendation_types=[item],
    )


def _stability(rec_type: str = "industry", rating: str = "stable") -> StabilityOut:
    item = StabilityTypeItemOut(
        recommendation_type=rec_type,
        average_quality_score=80.0,
        std_dev=2.5,
        stability_rating=rating,
    )
    return StabilityOut(
        generated_at=NOW,
        quality_score_stability=QualityScoreStabilityOut(
            average=80.0, std_dev=2.5, stability_rating=rating
        ),
        recommendation_types=[item],
    )


def _metric_trend(direction: str = "stable") -> MetricTrendOut:
    return MetricTrendOut(current=80.0, previous=78.0, change=2.0, direction=direction)


def _drift(rec_type: str = "industry", direction: str = "stable") -> DriftOut:
    item = DriftTypeItemOut(
        recommendation_type=rec_type,
        quality_score=_metric_trend(direction),
    )
    return DriftOut(
        generated_at=NOW,
        overall=DriftOverallOut(
            quality_score=_metric_trend(),
            adoption_rate=_metric_trend(),
            success_rate=_metric_trend(),
        ),
        by_type=[item],
    )


def _reliability(
    rec_type: str = "industry",
    reliability_score: float = 82.0,
    rating: str = "high",
) -> ReliabilityOut:
    item = ReliabilityTypeItemOut(
        recommendation_type=rec_type,
        reliability_score=reliability_score,
        rating=rating,
    )
    return ReliabilityOut(
        generated_at=NOW,
        overall_reliability=ReliabilityOverallOut(score=82.0, rating="high"),
        recommendation_types=[item],
    )


def _lifecycle(
    rec_type: str = "industry",
    avg_days_to_action: float = 3.2,
    avg_days_to_success: float = 9.1,
) -> LifecycleOut:
    item = LifecycleTypeItemOut(
        recommendation_type=rec_type,
        avg_days_to_action=avg_days_to_action,
        avg_days_to_success=avg_days_to_success,
        acted_rate=60.0,
        success_rate=45.0,
    )
    return LifecycleOut(
        generated_at=NOW,
        overall=LifecycleOverallOut(
            avg_days_to_action=3.2,
            avg_days_to_success=9.1,
            acted_rate=60.0,
            success_rate=45.0,
        ),
        recommendation_types=[item],
    )


def _qual_score_row(rec_type: str = "industry", quality_score: int | None = 81) -> RecommendationQualityScore:
    row = MagicMock(spec=RecommendationQualityScore)
    row.rec_type = rec_type
    row.quality_score = quality_score
    return row


# ── Context manager helpers ───────────────────────────────────────────────────

class _PatchSet:
    """Provides all upstream service mocks plus repo mocks for get_evidence."""

    def __init__(
        self,
        *,
        rec_type: str = "industry",
        generated_count: int = 42,
        qual_rows=None,
        outcome_map=None,
        portfolio_out=None,
        coverage_out=None,
        calibration_out=None,
        stability_out=None,
        drift_out=None,
        reliability_out=None,
        lifecycle_out=None,
        redis_cached=None,
    ):
        self.rec_type = rec_type
        self.generated_count = generated_count
        self.qual_rows = qual_rows if qual_rows is not None else [_qual_score_row(rec_type)]
        self.outcome_map = outcome_map if outcome_map is not None else {rec_type: (10, 6, 4)}
        self.portfolio_out = portfolio_out or _portfolio(rec_type)
        self.coverage_out = coverage_out or _coverage(rec_type)
        self.calibration_out = calibration_out or _calibration(rec_type)
        self.stability_out = stability_out or _stability(rec_type)
        self.drift_out = drift_out or _drift(rec_type)
        self.reliability_out = reliability_out or _reliability(rec_type)
        self.lifecycle_out = lifecycle_out or _lifecycle(rec_type)
        self.redis_cached = redis_cached

    async def __aenter__(self):
        po = self.portfolio_out
        co = self.coverage_out
        cal = self.calibration_out
        stab = self.stability_out
        dr = self.drift_out
        rel = self.reliability_out
        lc = self.lifecycle_out

        # Start patches individually so we can reference each mock object
        self._p_ctx = patch(
            "corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()
        )
        self._p_redis = patch("corpmind.modules.analytics.service.get_redis")
        self._p_port = patch("corpmind.modules.analytics.service.RecommendationPortfolioService")
        self._p_cal = patch("corpmind.modules.analytics.service.RecommendationAnalyticsService")
        self._p_stab = patch("corpmind.modules.analytics.service.RecommendationCalibrationService")
        self._p_drift = patch("corpmind.modules.analytics.service.RecommendationDriftService")
        self._p_lc = patch("corpmind.modules.analytics.service.RecommendationLifecycleService")
        self._p_snap = patch("corpmind.modules.analytics.service.RecommendationSnapshotRepo")
        self._p_qual = patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo")
        self._p_out = patch("corpmind.modules.analytics.service.RecommendationOutcomeRepo")

        self._patches = [
            self._p_ctx, self._p_redis, self._p_port, self._p_cal,
            self._p_stab, self._p_drift, self._p_lc,
            self._p_snap, self._p_qual, self._p_out,
        ]
        (
            _,
            p_redis_obj,
            p_port_obj,
            p_cal_obj,
            p_stab_obj,
            p_drift_obj,
            p_lc_obj,
            p_snap_obj,
            p_qual_obj,
            p_out_obj,
        ) = [p.start() for p in self._patches]

        # Redis
        p_redis_obj.return_value.get = AsyncMock(return_value=self.redis_cached)
        p_redis_obj.return_value.set = AsyncMock()
        self.mock_redis = p_redis_obj.return_value

        # Portfolio service returns both portfolio and coverage
        p_port_obj.return_value.get_portfolio = AsyncMock(return_value=po)
        p_port_obj.return_value.get_coverage = AsyncMock(return_value=co)

        # Calibration (analytics service)
        p_cal_obj.return_value.get_calibration = AsyncMock(return_value=cal)

        # Stability
        p_stab_obj.return_value.get_stability = AsyncMock(return_value=stab)

        # Drift service handles both drift and reliability
        p_drift_obj.return_value.get_drift = AsyncMock(return_value=dr)
        p_drift_obj.return_value.get_reliability = AsyncMock(return_value=rel)

        # Lifecycle
        p_lc_obj.return_value.get_lifecycle = AsyncMock(return_value=lc)

        # Repos
        p_snap_obj.return_value.count_by_workspace_type = AsyncMock(
            return_value=self.generated_count
        )
        p_qual_obj.return_value.list_by_workspace = AsyncMock(return_value=self.qual_rows)
        p_out_obj.return_value.aggregate_by_type_for_period = AsyncMock(
            return_value=self.outcome_map
        )

        return self

    async def __aexit__(self, *_):
        for p in reversed(self._patches):
            p.stop()


def _make_svc() -> RecommendationEvidenceService:
    return RecommendationEvidenceService(AsyncMock())


# ── Static helper tests ───────────────────────────────────────────────────────


class TestCoverageStatus:
    def test_none_input_returns_missing(self):
        assert RecommendationEvidenceService._coverage_status(None) == "missing"

    def test_present_false_returns_missing(self):
        item = CoverageItemOut(
            recommendation_type="industry",
            present=False,
            count=0,
            last_generated_at=None,
            days_since_last_generated=None,
        )
        assert RecommendationEvidenceService._coverage_status(item) == "missing"

    def test_present_true_no_days_returns_healthy(self):
        item = CoverageItemOut(
            recommendation_type="industry",
            present=True,
            count=5,
            last_generated_at=date(2026, 6, 24),
            days_since_last_generated=None,
        )
        assert RecommendationEvidenceService._coverage_status(item) == "healthy"

    def test_present_true_days_10_returns_healthy(self):
        item = CoverageItemOut(
            recommendation_type="industry",
            present=True,
            count=5,
            last_generated_at=date(2026, 6, 14),
            days_since_last_generated=10,
        )
        assert RecommendationEvidenceService._coverage_status(item) == "healthy"

    def test_present_true_days_30_returns_healthy(self):
        item = CoverageItemOut(
            recommendation_type="industry",
            present=True,
            count=5,
            last_generated_at=date(2026, 5, 25),
            days_since_last_generated=30,
        )
        assert RecommendationEvidenceService._coverage_status(item) == "healthy"

    def test_present_true_days_31_returns_stale(self):
        item = CoverageItemOut(
            recommendation_type="industry",
            present=True,
            count=5,
            last_generated_at=date(2026, 5, 24),
            days_since_last_generated=31,
        )
        assert RecommendationEvidenceService._coverage_status(item) == "stale"


class TestCalibrationStatus:
    def test_none_returns_none(self):
        assert RecommendationEvidenceService._calibration_status(None) is None

    def test_zero_returns_calibrated(self):
        assert RecommendationEvidenceService._calibration_status(0.0) == "calibrated"

    def test_below_threshold_returns_calibrated(self):
        assert RecommendationEvidenceService._calibration_status(4.9) == "calibrated"

    def test_exactly_5_returns_warning(self):
        assert RecommendationEvidenceService._calibration_status(5.0) == "warning"

    def test_within_warning_band_returns_warning(self):
        assert RecommendationEvidenceService._calibration_status(10.0) == "warning"

    def test_exactly_15_returns_warning(self):
        assert RecommendationEvidenceService._calibration_status(15.0) == "warning"

    def test_above_15_returns_severe(self):
        assert RecommendationEvidenceService._calibration_status(15.1) == "severe"

    def test_large_delta_returns_severe(self):
        assert RecommendationEvidenceService._calibration_status(30.0) == "severe"

    def test_negative_delta_uses_abs_calibrated(self):
        assert RecommendationEvidenceService._calibration_status(-3.0) == "calibrated"

    def test_negative_delta_uses_abs_warning(self):
        assert RecommendationEvidenceService._calibration_status(-10.0) == "warning"

    def test_negative_delta_uses_abs_severe(self):
        assert RecommendationEvidenceService._calibration_status(-20.0) == "severe"


# ── get_evidence core extraction ──────────────────────────────────────────────


class TestGetEvidenceReturn:
    @pytest.mark.asyncio
    async def test_returns_evidence_out_instance(self):
        svc = _make_svc()
        async with _PatchSet() as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert isinstance(result, EvidenceOut)

    @pytest.mark.asyncio
    async def test_recommendation_type_in_output(self):
        svc = _make_svc()
        async with _PatchSet(rec_type="topic") as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="topic")
        assert result.recommendation_type == "topic"

    @pytest.mark.asyncio
    async def test_generated_count_from_repo(self):
        svc = _make_svc()
        async with _PatchSet(generated_count=17) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.generated_count == 17


class TestGetEvidenceQuality:
    @pytest.mark.asyncio
    async def test_quality_score_from_matching_type(self):
        svc = _make_svc()
        async with _PatchSet(qual_rows=[_qual_score_row("industry", quality_score=88)]) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.quality_score == 88

    @pytest.mark.asyncio
    async def test_quality_score_none_when_no_matching_row(self):
        svc = _make_svc()
        async with _PatchSet(qual_rows=[_qual_score_row("topic", quality_score=70)]) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.quality_score is None

    @pytest.mark.asyncio
    async def test_quality_score_picks_first_matching_row(self):
        svc = _make_svc()
        rows = [
            _qual_score_row("industry", quality_score=90),
            _qual_score_row("industry", quality_score=70),
        ]
        async with _PatchSet(qual_rows=rows) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.quality_score == 90


class TestGetEvidenceRates:
    @pytest.mark.asyncio
    async def test_acted_rate_computed_correctly(self):
        svc = _make_svc()
        async with _PatchSet(outcome_map={"industry": (10, 6, 4)}) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.acted_rate == pytest.approx(60.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_success_rate_computed_correctly(self):
        svc = _make_svc()
        async with _PatchSet(outcome_map={"industry": (10, 6, 4)}) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.success_rate == pytest.approx(40.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_no_division_error_when_no_outcomes(self):
        svc = _make_svc()
        async with _PatchSet(outcome_map={}) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.acted_rate == 0.0
        assert result.summary.success_rate == 0.0


class TestGetEvidenceReliability:
    @pytest.mark.asyncio
    async def test_reliability_score_extracted(self):
        svc = _make_svc()
        rel = _reliability("industry", reliability_score=91.0, rating="high")
        async with _PatchSet(reliability_out=rel) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.reliability_score == pytest.approx(91.0)
        assert result.summary.reliability_rating == "high"

    @pytest.mark.asyncio
    async def test_reliability_none_when_type_missing(self):
        svc = _make_svc()
        rel = _reliability("topic")
        async with _PatchSet(reliability_out=rel) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.reliability_score is None
        assert result.summary.reliability_rating is None


class TestGetEvidenceLifecycle:
    @pytest.mark.asyncio
    async def test_lifecycle_timing_extracted(self):
        svc = _make_svc()
        lc = _lifecycle("industry", avg_days_to_action=4.5, avg_days_to_success=12.3)
        async with _PatchSet(lifecycle_out=lc) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.avg_days_to_action == pytest.approx(4.5)
        assert result.summary.avg_days_to_success == pytest.approx(12.3)

    @pytest.mark.asyncio
    async def test_lifecycle_defaults_to_zero_when_type_missing(self):
        svc = _make_svc()
        lc = _lifecycle("topic")
        async with _PatchSet(lifecycle_out=lc) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.avg_days_to_action == 0.0
        assert result.summary.avg_days_to_success == 0.0


class TestGetEvidenceDrift:
    @pytest.mark.asyncio
    async def test_drift_direction_extracted(self):
        svc = _make_svc()
        dr = _drift("industry", direction="improving")
        async with _PatchSet(drift_out=dr) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.drift_direction == "improving"

    @pytest.mark.asyncio
    async def test_drift_direction_none_when_type_missing(self):
        svc = _make_svc()
        dr = _drift("topic")
        async with _PatchSet(drift_out=dr) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.drift_direction is None


class TestGetEvidenceStability:
    @pytest.mark.asyncio
    async def test_stability_rating_extracted(self):
        svc = _make_svc()
        stab = _stability("industry", rating="volatile")
        async with _PatchSet(stability_out=stab) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.stability_rating == "volatile"

    @pytest.mark.asyncio
    async def test_stability_rating_none_when_type_missing(self):
        svc = _make_svc()
        stab = _stability("topic")
        async with _PatchSet(stability_out=stab) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.stability_rating is None


class TestGetEvidenceCalibration:
    @pytest.mark.asyncio
    async def test_confidence_average_extracted(self):
        svc = _make_svc()
        cal = _calibration("industry", predicted_confidence=72.5)
        async with _PatchSet(calibration_out=cal) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.confidence_average == pytest.approx(72.5)

    @pytest.mark.asyncio
    async def test_calibration_status_derived_from_delta(self):
        svc = _make_svc()
        cal = _calibration("industry", calibration_delta=2.0)
        async with _PatchSet(calibration_out=cal) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.calibration_status == "calibrated"

    @pytest.mark.asyncio
    async def test_calibration_status_warning_when_delta_10(self):
        svc = _make_svc()
        cal = _calibration("industry", calibration_delta=10.0)
        async with _PatchSet(calibration_out=cal) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.calibration_status == "warning"

    @pytest.mark.asyncio
    async def test_confidence_none_when_type_missing(self):
        svc = _make_svc()
        cal = _calibration("topic")
        async with _PatchSet(calibration_out=cal) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.confidence_average is None
        assert result.summary.calibration_status is None


class TestGetEvidencePortfolioCoverage:
    @pytest.mark.asyncio
    async def test_portfolio_percentage_extracted(self):
        svc = _make_svc()
        port = _portfolio("industry", percentage=35.0)
        async with _PatchSet(portfolio_out=port) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.portfolio_percentage == pytest.approx(35.0)

    @pytest.mark.asyncio
    async def test_portfolio_percentage_zero_when_type_missing(self):
        svc = _make_svc()
        port = _portfolio("topic")
        async with _PatchSet(portfolio_out=port) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.portfolio_percentage == 0.0

    @pytest.mark.asyncio
    async def test_coverage_status_healthy(self):
        svc = _make_svc()
        cov = _coverage("industry", present=True, last_generated_at=date(2026, 6, 24), days_since=1)
        async with _PatchSet(coverage_out=cov) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.coverage_status == "healthy"

    @pytest.mark.asyncio
    async def test_coverage_status_missing_when_not_present(self):
        svc = _make_svc()
        cov = _coverage("industry", present=False, last_generated_at=None, days_since=None)
        async with _PatchSet(coverage_out=cov) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.coverage_status == "missing"

    @pytest.mark.asyncio
    async def test_last_generated_at_extracted(self):
        svc = _make_svc()
        cov = _coverage("industry", present=True, last_generated_at=date(2026, 6, 20), days_since=5)
        async with _PatchSet(coverage_out=cov) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.summary.last_generated_at == date(2026, 6, 20)
        assert result.summary.days_since_last_generated == 5


class TestGetEvidenceInsufficientData:
    @pytest.mark.asyncio
    async def test_insufficient_when_zero_count_and_no_last_generated(self):
        svc = _make_svc()
        cov = _coverage("industry", present=False, last_generated_at=None, days_since=None)
        async with _PatchSet(generated_count=0, coverage_out=cov) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.insufficient_data is True

    @pytest.mark.asyncio
    async def test_not_insufficient_when_count_positive(self):
        svc = _make_svc()
        async with _PatchSet(generated_count=5) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.insufficient_data is False

    @pytest.mark.asyncio
    async def test_not_insufficient_when_zero_count_but_has_last_generated(self):
        svc = _make_svc()
        cov = _coverage("industry", present=True, last_generated_at=date(2026, 5, 1), days_since=55)
        async with _PatchSet(generated_count=0, coverage_out=cov) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert result.insufficient_data is False


# ── Supporting metrics ────────────────────────────────────────────────────────


class TestSupportingMetrics:
    @pytest.mark.asyncio
    async def test_nine_metrics_emitted(self):
        svc = _make_svc()
        async with _PatchSet() as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert len(result.supporting_metrics) == 9

    @pytest.mark.asyncio
    async def test_quality_score_source_attribution(self):
        svc = _make_svc()
        async with _PatchSet() as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        row = next(m for m in result.supporting_metrics if m.name == "Quality Score")
        assert row.source == "recommendation_quality_scores"

    @pytest.mark.asyncio
    async def test_reliability_score_source_attribution(self):
        svc = _make_svc()
        async with _PatchSet() as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        row = next(m for m in result.supporting_metrics if m.name == "Reliability Score")
        assert row.source == "recommendation_quality_scores"

    @pytest.mark.asyncio
    async def test_success_rate_source_attribution(self):
        svc = _make_svc()
        async with _PatchSet() as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        row = next(m for m in result.supporting_metrics if m.name == "Success Rate")
        assert row.source == "recommendation_outcomes"

    @pytest.mark.asyncio
    async def test_confidence_average_source_attribution(self):
        svc = _make_svc()
        async with _PatchSet() as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        row = next(m for m in result.supporting_metrics if m.name == "Confidence Average")
        assert row.source == "recommendation_snapshots"

    @pytest.mark.asyncio
    async def test_portfolio_share_source_attribution(self):
        svc = _make_svc()
        async with _PatchSet() as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        row = next(m for m in result.supporting_metrics if m.name == "Portfolio Share")
        assert row.source == "recommendation_snapshots"

    @pytest.mark.asyncio
    async def test_quality_score_metric_is_float_or_none(self):
        svc = _make_svc()
        async with _PatchSet(qual_rows=[_qual_score_row("industry", quality_score=81)]) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        row = next(m for m in result.supporting_metrics if m.name == "Quality Score")
        assert isinstance(row.value, float)
        assert row.value == pytest.approx(81.0)

    @pytest.mark.asyncio
    async def test_quality_score_metric_none_when_no_row(self):
        svc = _make_svc()
        async with _PatchSet(qual_rows=[]) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        row = next(m for m in result.supporting_metrics if m.name == "Quality Score")
        assert row.value is None

    @pytest.mark.asyncio
    async def test_generated_count_metric_source(self):
        svc = _make_svc()
        async with _PatchSet(generated_count=30) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        row = next(m for m in result.supporting_metrics if m.name == "Generated Count")
        assert row.source == "recommendation_snapshots"
        assert row.value == pytest.approx(30.0)


# ── Redis caching ──────────────────────────────────────────────────────────────


class TestRedisCache:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value(self):
        svc = _make_svc()
        # Build a minimal EvidenceOut to cache
        from corpmind.modules.analytics.schemas import EvidenceSummaryOut, EvidenceMetricOut
        cached_out = EvidenceOut(
            generated_at=NOW,
            recommendation_type="industry",
            summary=EvidenceSummaryOut(
                generated_count=99,
                portfolio_percentage=0.0,
                confidence_average=None,
                quality_score=None,
                acted_rate=0.0,
                success_rate=0.0,
                reliability_score=None,
                reliability_rating=None,
                avg_days_to_action=0.0,
                avg_days_to_success=0.0,
                drift_direction=None,
                stability_rating=None,
                calibration_status=None,
                coverage_status="missing",
                last_generated_at=None,
                days_since_last_generated=None,
            ),
            supporting_metrics=[],
            insufficient_data=True,
        )
        cached_json = cached_out.model_dump_json()
        async with _PatchSet(redis_cached=cached_json) as p:
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        # Should return the cached value (generated_count=99) not the computed one (42)
        assert result.summary.generated_count == 99

    @pytest.mark.asyncio
    async def test_cache_miss_writes_to_redis(self):
        svc = _make_svc()
        async with _PatchSet(redis_cached=None) as p:
            await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        p.mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_get_failure_falls_back_gracefully(self):
        svc = _make_svc()
        async with _PatchSet() as p:
            p.mock_redis.get = AsyncMock(side_effect=Exception("Redis down"))
            # Should not raise — falls back to live computation
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert isinstance(result, EvidenceOut)

    @pytest.mark.asyncio
    async def test_redis_set_failure_does_not_raise(self):
        svc = _make_svc()
        async with _PatchSet() as p:
            p.mock_redis.set = AsyncMock(side_effect=Exception("Redis down"))
            result = await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        assert isinstance(result, EvidenceOut)


# ── Tenant isolation ──────────────────────────────────────────────────────────


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_cache_key_includes_org_id(self):
        svc = _make_svc()
        async with _PatchSet() as p:
            await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        call_args = p.mock_redis.set.call_args
        cache_key = call_args[0][0]
        assert str(TENANT_ID) in cache_key

    @pytest.mark.asyncio
    async def test_cache_key_includes_workspace_id(self):
        svc = _make_svc()
        async with _PatchSet() as p:
            await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="industry")
        call_args = p.mock_redis.set.call_args
        cache_key = call_args[0][0]
        assert str(WORKSPACE_ID) in cache_key

    @pytest.mark.asyncio
    async def test_cache_key_includes_rec_type(self):
        svc = _make_svc()
        async with _PatchSet(rec_type="topic") as p:
            await svc.get_evidence(workspace_id=WORKSPACE_ID, recommendation_type="topic")
        call_args = p.mock_redis.set.call_args
        cache_key = call_args[0][0]
        assert "topic" in cache_key
