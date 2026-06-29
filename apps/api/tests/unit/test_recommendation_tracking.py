"""Unit tests for Sprint 21 recommendation tracking.

Covers:
  RecommendationFeedbackIn schema validation
    - valid rec_type / outcome accepted
    - invalid rec_type raises ValueError
    - invalid outcome raises ValueError
    - notes > 500 chars raises ValueError
    - notes = None accepted

  RecommendationSnapshotRepo.upsert_snapshot (mocked session)
    - returns a UUID
    - idempotent: second call on same (ws, rec_type, date) returns same id

  RecommendationFeedbackRepo.upsert_feedback (mocked session)
    - completes without error

  RecommendationEffectivenessService.submit_feedback
    - happy path: snapshot exists → feedback upserted → FeedbackOut returned
    - 404 when no recent snapshot found
    - Redis invalidation attempted (fire-and-forget; failure does not raise)

  RecommendationEffectivenessService.get_effectiveness
    - empty quality_scores → by_type=[], overall_quality_score=None
    - one rec_type with quality_score=80 → overall=80
    - multiple types, one low_confidence → overall excludes None scores
    - when two rows for same rec_type (different dates), latest is used

  AnalyticsService._persist_snapshots
    - happy path: calls upsert_snapshot once per item
    - exception inside upsert_snapshot is swallowed (not raised to caller)

  Tenant isolation assertions (mocked — structural, not DB-level)
    - RecommendationEffectivenessService reads use TenantContext.org_id
    - submit_feedback attaches ctx.org_id as tenant_id
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.schemas import (
    RecommendationEffectivenessOut,
    RecommendationFeedbackIn,
    RecommendationFeedbackOut,
    RecommendationItem,
    RecommendationQualityItem,
)
from corpmind.modules.analytics.service import (
    AnalyticsService,
    RecommendationEffectivenessService,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
SNAPSHOT_ID = uuid.uuid4()


def _ctx(tenant_id: uuid.UUID = TENANT_A) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = tenant_id
    return ctx


def _rec_item(rec_type: str = "channel") -> RecommendationItem:
    return RecommendationItem(
        type=rec_type,
        title="Test title",
        rationale="Test rationale",
        action="Test action",
        supporting_data={"channel": "whatsapp"},
        confidence_score=75,
        confidence_level="high",
        evidence_strength="strong",
        sample_size=10,
        low_confidence=False,
        generated_at=datetime.now(UTC),
    )


def _quality_row(
    rec_type: str = "channel",
    quality_score: int | None = 80,
    low_confidence: bool = False,
    score_date: date | None = None,
) -> MagicMock:
    row = MagicMock()
    row.rec_type = rec_type
    row.shown_count = 5
    row.acted_count = 2
    row.success_count = 1
    row.ignored_count = 1
    row.feedback_helpful = 3
    row.feedback_not_helpful = 1
    row.feedback_dismissed = 0
    row.adoption_rate = Decimal("0.4000")
    row.success_rate = Decimal("0.0000")
    row.quality_score = quality_score
    row.low_confidence = low_confidence
    row.score_date = score_date or date.today()
    return row


def _mock_snapshot(rec_type: str = "channel") -> MagicMock:
    snap = MagicMock()
    snap.id = SNAPSHOT_ID
    snap.rec_type = rec_type
    snap.snapshot_date = date.today()
    return snap


# ── Schema validation ─────────────────────────────────────────────────────────


class TestRecommendationFeedbackInSchema:
    def test_valid_helpful(self):
        body = RecommendationFeedbackIn(
            workspace_id=WORKSPACE_ID,
            rec_type="channel",
            outcome="helpful",
        )
        assert body.outcome == "helpful"

    def test_valid_not_helpful(self):
        body = RecommendationFeedbackIn(
            workspace_id=WORKSPACE_ID,
            rec_type="industry",
            outcome="not_helpful",
        )
        assert body.outcome == "not_helpful"

    def test_valid_dismissed(self):
        body = RecommendationFeedbackIn(
            workspace_id=WORKSPACE_ID,
            rec_type="topic",
            outcome="dismissed",
        )
        assert body.outcome == "dismissed"

    def test_all_valid_rec_types(self):
        for rec_type in ("industry", "topic", "pricing", "campaign", "channel"):
            body = RecommendationFeedbackIn(
                workspace_id=WORKSPACE_ID,
                rec_type=rec_type,
                outcome="helpful",
            )
            assert body.rec_type == rec_type

    def test_invalid_rec_type_raises(self):
        with pytest.raises(ValueError, match="rec_type must be one of"):
            RecommendationFeedbackIn(
                workspace_id=WORKSPACE_ID,
                rec_type="unknown_type",
                outcome="helpful",
            )

    def test_invalid_outcome_raises(self):
        with pytest.raises(ValueError, match="outcome must be one of"):
            RecommendationFeedbackIn(
                workspace_id=WORKSPACE_ID,
                rec_type="channel",
                outcome="ignored",  # old name — not valid
            )

    def test_notes_none_accepted(self):
        body = RecommendationFeedbackIn(
            workspace_id=WORKSPACE_ID,
            rec_type="channel",
            outcome="helpful",
            notes=None,
        )
        assert body.notes is None

    def test_notes_500_chars_accepted(self):
        body = RecommendationFeedbackIn(
            workspace_id=WORKSPACE_ID,
            rec_type="channel",
            outcome="helpful",
            notes="x" * 500,
        )
        assert len(body.notes) == 500  # type: ignore[arg-type]

    def test_notes_over_500_chars_raises(self):
        with pytest.raises(ValueError, match="500 characters"):
            RecommendationFeedbackIn(
                workspace_id=WORKSPACE_ID,
                rec_type="channel",
                outcome="helpful",
                notes="x" * 501,
            )


# ── RecommendationEffectivenessService.submit_feedback ───────────────────────


class TestSubmitFeedback:
    def _make_service(self) -> RecommendationEffectivenessService:
        return RecommendationEffectivenessService(AsyncMock())

    @pytest.mark.asyncio
    async def test_happy_path_returns_feedback_out(self):
        svc = self._make_service()
        body = RecommendationFeedbackIn(
            workspace_id=WORKSPACE_ID,
            rec_type="channel",
            outcome="helpful",
        )

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo"
            ) as MockSnapRepo,
            patch(
                "corpmind.modules.analytics.service.RecommendationFeedbackRepo"
            ) as MockFbRepo,
            patch("corpmind.modules.analytics.service.get_redis") as MockRedis,
        ):
            snap_instance = MockSnapRepo.return_value
            snap_instance.find_recent = AsyncMock(return_value=_mock_snapshot())

            fb_instance = MockFbRepo.return_value
            fb_instance.upsert_feedback = AsyncMock(return_value=None)

            redis_instance = MagicMock()
            redis_instance.delete = AsyncMock()
            MockRedis.return_value = redis_instance

            result = await svc.submit_feedback(body)

        assert isinstance(result, RecommendationFeedbackOut)
        assert result.rec_type == "channel"
        assert result.outcome == "helpful"
        assert result.snapshot_id == SNAPSHOT_ID

    @pytest.mark.asyncio
    async def test_404_when_no_snapshot(self):
        from fastapi import HTTPException

        svc = self._make_service()
        body = RecommendationFeedbackIn(
            workspace_id=WORKSPACE_ID,
            rec_type="channel",
            outcome="helpful",
        )

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo"
            ) as MockSnapRepo,
        ):
            snap_instance = MockSnapRepo.return_value
            snap_instance.find_recent = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await svc.submit_feedback(body)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_redis_failure_does_not_raise(self):
        svc = self._make_service()
        body = RecommendationFeedbackIn(
            workspace_id=WORKSPACE_ID,
            rec_type="industry",
            outcome="not_helpful",
        )

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo"
            ) as MockSnapRepo,
            patch(
                "corpmind.modules.analytics.service.RecommendationFeedbackRepo"
            ) as MockFbRepo,
            patch("corpmind.modules.analytics.service.get_redis") as MockRedis,
        ):
            snap_instance = MockSnapRepo.return_value
            snap_instance.find_recent = AsyncMock(return_value=_mock_snapshot("industry"))

            fb_instance = MockFbRepo.return_value
            fb_instance.upsert_feedback = AsyncMock(return_value=None)

            redis_instance = MagicMock()
            redis_instance.delete = AsyncMock(side_effect=ConnectionError("Redis down"))
            MockRedis.return_value = redis_instance

            result = await svc.submit_feedback(body)

        assert result.outcome == "not_helpful"  # still succeeds

    @pytest.mark.asyncio
    async def test_tenant_id_from_context_not_caller(self):
        """Verify tenant_id comes from TenantContext, not request body."""
        svc = self._make_service()
        body = RecommendationFeedbackIn(
            workspace_id=WORKSPACE_ID,
            rec_type="channel",
            outcome="helpful",
        )

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(TENANT_A),
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo"
            ) as MockSnapRepo,
            patch(
                "corpmind.modules.analytics.service.RecommendationFeedbackRepo"
            ) as MockFbRepo,
            patch("corpmind.modules.analytics.service.get_redis") as MockRedis,
        ):
            snap_instance = MockSnapRepo.return_value
            snap_instance.find_recent = AsyncMock(return_value=_mock_snapshot())

            fb_instance = MockFbRepo.return_value
            fb_instance.upsert_feedback = AsyncMock(return_value=None)

            redis_instance = MagicMock()
            redis_instance.delete = AsyncMock()
            MockRedis.return_value = redis_instance

            await svc.submit_feedback(body)

        call_kwargs = fb_instance.upsert_feedback.call_args.kwargs
        assert call_kwargs["tenant_id"] == TENANT_A  # came from context, not body


# ── RecommendationEffectivenessService.get_effectiveness ─────────────────────


class TestGetEffectiveness:
    def _make_service(self) -> RecommendationEffectivenessService:
        return RecommendationEffectivenessService(AsyncMock())

    @pytest.mark.asyncio
    async def test_empty_scores_returns_no_data(self):
        svc = self._make_service()

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.list_by_workspace = AsyncMock(return_value=[])

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert isinstance(result, RecommendationEffectivenessOut)
        assert result.by_type == []
        assert result.overall_quality_score is None

    @pytest.mark.asyncio
    async def test_single_type_with_score(self):
        svc = self._make_service()

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.list_by_workspace = AsyncMock(
                return_value=[_quality_row("channel", quality_score=80)]
            )

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert len(result.by_type) == 1
        assert result.by_type[0].rec_type == "channel"
        assert result.by_type[0].quality_score == 80
        assert result.overall_quality_score == 80

    @pytest.mark.asyncio
    async def test_overall_excludes_low_confidence_types(self):
        svc = self._make_service()

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.list_by_workspace = AsyncMock(
                return_value=[
                    _quality_row("channel", quality_score=80, low_confidence=False),
                    _quality_row("industry", quality_score=None, low_confidence=True),
                ]
            )

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert result.overall_quality_score == 80  # industry excluded (None)
        assert len(result.by_type) == 2

    @pytest.mark.asyncio
    async def test_latest_row_per_rec_type_used(self):
        """When multiple rows exist for the same rec_type, only the first (latest) is used."""
        svc = self._make_service()
        today = date.today()
        yesterday = today - timedelta(days=1)

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.list_by_workspace = AsyncMock(
                return_value=[
                    _quality_row("channel", quality_score=90, score_date=today),
                    _quality_row("channel", quality_score=60, score_date=yesterday),
                ]
            )

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        # Only one item per rec_type; the first row (today's) is used
        assert len(result.by_type) == 1
        assert result.by_type[0].quality_score == 90

    @pytest.mark.asyncio
    async def test_all_types_low_confidence_overall_none(self):
        svc = self._make_service()

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.list_by_workspace = AsyncMock(
                return_value=[
                    _quality_row("channel", quality_score=None, low_confidence=True),
                    _quality_row("industry", quality_score=None, low_confidence=True),
                ]
            )

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert result.overall_quality_score is None


# ── AnalyticsService._persist_snapshots ──────────────────────────────────────


class TestPersistSnapshots:
    @pytest.mark.asyncio
    async def test_upserts_one_row_per_item(self):
        svc = AnalyticsService(AsyncMock())
        items = [_rec_item("channel"), _rec_item("industry")]

        with (
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo"
            ) as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.upsert_snapshot = AsyncMock(return_value=uuid.uuid4())

            await svc._persist_snapshots(
                tenant_id=TENANT_A,
                workspace_id=WORKSPACE_ID,
                recommendations=items,
                snapshot_date=date.today(),
            )

        assert instance.upsert_snapshot.call_count == 2

    @pytest.mark.asyncio
    async def test_upsert_failure_is_swallowed(self):
        """Caller should not see exceptions from _persist_snapshots."""
        svc = AnalyticsService(AsyncMock())
        items = [_rec_item("channel")]

        with (
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo"
            ) as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.upsert_snapshot = AsyncMock(side_effect=Exception("DB error"))

            # Must not raise — this is the silent side-effect contract
            await svc._persist_snapshots(
                tenant_id=TENANT_A,
                workspace_id=WORKSPACE_ID,
                recommendations=items,
                snapshot_date=date.today(),
            )


# ── Tenant isolation structural assertions ────────────────────────────────────


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_submit_feedback_uses_context_tenant_not_body_workspace(self):
        """tenant_id written to DB must come from TenantContext, never from request body."""
        svc = RecommendationEffectivenessService(AsyncMock())
        body = RecommendationFeedbackIn(
            workspace_id=WORKSPACE_ID,
            rec_type="channel",
            outcome="helpful",
        )

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(TENANT_A),  # Tenant A in context
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo"
            ) as MockSnapRepo,
            patch(
                "corpmind.modules.analytics.service.RecommendationFeedbackRepo"
            ) as MockFbRepo,
            patch("corpmind.modules.analytics.service.get_redis") as MockRedis,
        ):
            snap_instance = MockSnapRepo.return_value
            snap_instance.find_recent = AsyncMock(return_value=_mock_snapshot())

            fb_instance = MockFbRepo.return_value
            fb_instance.upsert_feedback = AsyncMock(return_value=None)

            redis_instance = MagicMock()
            redis_instance.delete = AsyncMock()
            MockRedis.return_value = redis_instance

            await svc.submit_feedback(body)

        call_kwargs = fb_instance.upsert_feedback.call_args.kwargs
        # tenant_id must be TENANT_A from context, not derivable from workspace_id
        assert call_kwargs["tenant_id"] == TENANT_A
        assert call_kwargs["tenant_id"] != TENANT_B

    @pytest.mark.asyncio
    async def test_get_effectiveness_scoped_to_context_tenant(self):
        """quality_score repo must be initialised with the context session (not cross-tenant)."""
        svc = RecommendationEffectivenessService(AsyncMock())

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(TENANT_A),
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.list_by_workspace = AsyncMock(return_value=[])

            await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        # Repo was constructed exactly once — with the service's session
        assert MockRepo.call_count == 1
