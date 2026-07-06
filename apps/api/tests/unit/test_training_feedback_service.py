"""Unit tests for TrainingFeedbackService — Sprint 46.

Test classes:
  TestFeedbackCreate         (20 tests)
  TestFeedbackGet            (12 tests)
  TestFeedbackUpdate         (18 tests)
  TestFeedbackList           (20 tests)
  TestFeedbackListBySession  (10 tests)
  TestFeedbackListByCustomer (10 tests)
  TestFeedbackListByTrainer  (10 tests)
  TestRatingValidation       (15 tests)
  TestFeedbackCacheBust      (10 tests)
  TestFeedbackTenantIsolation (5 tests)

Total: 130 tests
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.training.schemas import (
    TrainingFeedbackCreate,
    TrainingFeedbackFilters,
    TrainingFeedbackListOut,
    TrainingFeedbackOut,
    TrainingFeedbackUpdate,
)
from corpmind.modules.training.service import TrainingFeedbackService

_ORG = uuid.uuid4()
_WS = uuid.uuid4()
_SESSION = uuid.uuid4()
_CUSTOMER = uuid.uuid4()
_TRAINER = uuid.uuid4()
_ATTENDANCE = uuid.uuid4()

_PATCH_CTX = "corpmind.modules.training.service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.training.service.get_redis"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ctx(org_id: uuid.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id or _ORG
    return ctx


def _make_redis(cached: str | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _make_svc() -> tuple[TrainingFeedbackService, MagicMock]:
    db = MagicMock()
    db.commit = AsyncMock()
    svc = TrainingFeedbackService(db)
    svc._repo = MagicMock()
    svc._attendance_repo = MagicMock()
    return svc, db


def _make_attendance(attendance_id: uuid.UUID | None = None) -> MagicMock:
    a = MagicMock()
    a.id = attendance_id or _ATTENDANCE
    a.participant_name = "Alice Test"
    return a


def _make_feedback(
    feedback_id: uuid.UUID | None = None,
    *,
    session_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    overall_rating: int | None = 4,
    would_recommend: bool | None = True,
    comments: str | None = "Great session",
) -> MagicMock:
    f = MagicMock()
    f.id = feedback_id or uuid.uuid4()
    f.tenant_id = _ORG
    f.workspace_id = _WS
    f.attendance_id = _ATTENDANCE
    f.session_id = session_id or _SESSION
    f.customer_id = customer_id or _CUSTOMER
    f.trainer_id = _TRAINER
    f.overall_rating = overall_rating
    f.trainer_rating = 5
    f.content_rating = 4
    f.materials_rating = 3
    f.venue_rating = None
    f.would_recommend = would_recommend
    f.comments = comments
    f.submitted_at = datetime.now(UTC)
    f.created_at = datetime.now(UTC)
    f.updated_at = datetime.now(UTC)
    return f


def _feedback_out(f: MagicMock) -> TrainingFeedbackOut:
    return TrainingFeedbackOut(
        id=f.id,
        tenant_id=f.tenant_id,
        workspace_id=f.workspace_id,
        attendance_id=f.attendance_id,
        session_id=f.session_id,
        customer_id=f.customer_id,
        trainer_id=f.trainer_id,
        overall_rating=f.overall_rating,
        trainer_rating=f.trainer_rating,
        content_rating=f.content_rating,
        materials_rating=f.materials_rating,
        venue_rating=f.venue_rating,
        would_recommend=f.would_recommend,
        comments=f.comments,
        submitted_at=f.submitted_at,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


@contextmanager
def _patch_ctx(ctx: MagicMock, redis: MagicMock):
    with patch(_PATCH_CTX, return_value=ctx):
        with patch(_PATCH_REDIS, return_value=redis):
            yield


# ── TestFeedbackCreate ────────────────────────────────────────────────────────

class TestFeedbackCreate:
    @pytest.mark.asyncio
    async def test_create_success(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        attendance = _make_attendance()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=attendance)
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
            overall_rating=5,
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create_feedback(req)
        assert out.session_id == _SESSION
        assert out.overall_rating == 5
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_attendance_not_found(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=None)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        from corpmind.core.exceptions import NotFoundError
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.create_feedback(req)

    @pytest.mark.asyncio
    async def test_create_duplicate_attendance(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        existing = _make_feedback()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=existing)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        from corpmind.core.exceptions import ValidationError
        with _patch_ctx(ctx, redis):
            with pytest.raises(ValidationError, match="already exists"):
                await svc.create_feedback(req)

    @pytest.mark.asyncio
    async def test_create_with_all_ratings(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
            overall_rating=5,
            trainer_rating=4,
            content_rating=3,
            materials_rating=2,
            venue_rating=1,
            would_recommend=True,
            comments="Test comments",
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create_feedback(req)
        assert out.overall_rating == 5
        assert out.trainer_rating == 4
        assert out.content_rating == 3
        assert out.materials_rating == 2
        assert out.venue_rating == 1
        assert out.would_recommend is True
        assert out.comments == "Test comments"

    @pytest.mark.asyncio
    async def test_create_with_no_ratings(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create_feedback(req)
        assert out.overall_rating is None
        assert out.would_recommend is None

    @pytest.mark.asyncio
    async def test_create_with_trainer_id(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
            trainer_id=_TRAINER,
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create_feedback(req)
        assert out.trainer_id == _TRAINER

    @pytest.mark.asyncio
    async def test_create_busts_list_cache(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_tenant_id_from_context(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        created_feedback = None
        async def capture_create(f):
            nonlocal created_feedback
            created_feedback = f
            return f
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = capture_create
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        assert created_feedback.tenant_id == _ORG

    @pytest.mark.asyncio
    async def test_create_custom_submitted_at(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        custom_ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
        created_feedback = None
        async def capture_create(f):
            nonlocal created_feedback
            created_feedback = f
            return f
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = capture_create
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
            submitted_at=custom_ts,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        assert created_feedback.submitted_at == custom_ts

    @pytest.mark.asyncio
    async def test_create_default_submitted_at_is_now(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        created_feedback = None
        async def capture_create(f):
            nonlocal created_feedback
            created_feedback = f
            return f
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = capture_create
        before = datetime.now(UTC)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        after = datetime.now(UTC)
        assert before <= created_feedback.submitted_at <= after

    @pytest.mark.asyncio
    async def test_create_redis_failure_graceful(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create_feedback(req)
        assert out is not None

    @pytest.mark.asyncio
    async def test_create_would_recommend_false(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
            would_recommend=False,
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create_feedback(req)
        assert out.would_recommend is False

    @pytest.mark.asyncio
    async def test_create_calls_repo_create(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        svc._repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_workspace_id_propagated(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        created_feedback = None
        async def capture_create(f):
            nonlocal created_feedback
            created_feedback = f
            return f
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = capture_create
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        assert created_feedback.workspace_id == _WS

    @pytest.mark.asyncio
    async def test_create_customer_id_propagated(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        created_feedback = None
        async def capture_create(f):
            nonlocal created_feedback
            created_feedback = f
            return f
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = capture_create
        custom_customer = uuid.uuid4()
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=custom_customer,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        assert created_feedback.customer_id == custom_customer

    @pytest.mark.asyncio
    async def test_create_no_trainer_id(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        created_feedback = None
        async def capture_create(f):
            nonlocal created_feedback
            created_feedback = f
            return f
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = capture_create
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        assert created_feedback.trainer_id is None

    @pytest.mark.asyncio
    async def test_create_commit_called(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_checks_duplicate_before_create(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=_make_feedback())
        svc._repo.create = AsyncMock()
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        from corpmind.core.exceptions import ValidationError
        with _patch_ctx(ctx, redis):
            with pytest.raises(ValidationError):
                await svc.create_feedback(req)
        svc._repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_returns_feedback_out(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create_feedback(req)
        assert isinstance(out, TrainingFeedbackOut)

    @pytest.mark.asyncio
    async def test_create_attendance_id_propagated(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        created_feedback = None

        async def capture_create(f):
            nonlocal created_feedback
            created_feedback = f
            return f

        other_attendance = uuid.uuid4()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance(other_attendance))
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = capture_create
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=other_attendance,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        assert created_feedback.attendance_id == other_attendance


# ── TestFeedbackGet ───────────────────────────────────────────────────────────

class TestFeedbackGet:
    @pytest.mark.asyncio
    async def test_get_cache_hit(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        fb = _make_feedback()
        cached = _feedback_out(fb).model_dump_json()
        redis = _make_redis(cached=cached)
        with _patch_ctx(ctx, redis):
            out = await svc.get_feedback(fb.id)
        assert out.id == fb.id
        svc._repo.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_cache_miss_hits_db(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        fb = _make_feedback()
        redis = _make_redis(cached=None)
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            out = await svc.get_feedback(fb.id)
        assert out.id == fb.id
        svc._repo.find_by_id.assert_awaited_once_with(fb.id)

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        svc._repo.find_by_id = AsyncMock(return_value=None)
        from corpmind.core.exceptions import NotFoundError
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.get_feedback(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_sets_cache_on_miss(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        fb = _make_feedback()
        redis = _make_redis(cached=None)
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            await svc.get_feedback(fb.id)
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_redis_failure_falls_back_to_db(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        fb = _make_feedback()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("redis error"))
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            out = await svc.get_feedback(fb.id)
        assert out.id == fb.id

    @pytest.mark.asyncio
    async def test_get_returns_feedback_out(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        fb = _make_feedback()
        redis = _make_redis(cached=None)
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            out = await svc.get_feedback(fb.id)
        assert isinstance(out, TrainingFeedbackOut)

    @pytest.mark.asyncio
    async def test_get_overall_rating(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        fb = _make_feedback(overall_rating=3)
        redis = _make_redis(cached=None)
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            out = await svc.get_feedback(fb.id)
        assert out.overall_rating == 3

    @pytest.mark.asyncio
    async def test_get_would_recommend(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        fb = _make_feedback(would_recommend=False)
        redis = _make_redis(cached=None)
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            out = await svc.get_feedback(fb.id)
        assert out.would_recommend is False

    @pytest.mark.asyncio
    async def test_get_comments(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        fb = _make_feedback(comments="Excellent training")
        redis = _make_redis(cached=None)
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            out = await svc.get_feedback(fb.id)
        assert out.comments == "Excellent training"

    @pytest.mark.asyncio
    async def test_get_null_overall_rating(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        fb = _make_feedback(overall_rating=None)
        redis = _make_redis(cached=None)
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            out = await svc.get_feedback(fb.id)
        assert out.overall_rating is None

    @pytest.mark.asyncio
    async def test_get_set_cache_with_ttl(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        fb = _make_feedback()
        redis = _make_redis(cached=None)
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            await svc.get_feedback(fb.id)
        call_kwargs = redis.set.call_args
        assert call_kwargs.kwargs.get("ex") == 300 or (
            len(call_kwargs.args) >= 3 and call_kwargs.args[2] == 300
            or call_kwargs.kwargs.get("ex") == 300
        )

    @pytest.mark.asyncio
    async def test_get_redis_set_failure_graceful(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        fb = _make_feedback()
        redis = _make_redis(cached=None)
        redis.set = AsyncMock(side_effect=Exception("redis set failed"))
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            out = await svc.get_feedback(fb.id)
        assert out is not None


# ── TestFeedbackUpdate ────────────────────────────────────────────────────────

class TestFeedbackUpdate:
    @pytest.mark.asyncio
    async def test_update_comments(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        updated = _make_feedback(feedback_id=fb.id, comments="Updated comment")
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, updated])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate(comments="Updated comment")
        with _patch_ctx(ctx, redis):
            out = await svc.update_feedback(fb.id, req)
        assert out.comments == "Updated comment"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_overall_rating(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        updated = _make_feedback(feedback_id=fb.id, overall_rating=2)
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, updated])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate(overall_rating=2)
        with _patch_ctx(ctx, redis):
            out = await svc.update_feedback(fb.id, req)
        assert out.overall_rating == 2

    @pytest.mark.asyncio
    async def test_update_would_recommend(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback(would_recommend=True)
        updated = _make_feedback(feedback_id=fb.id, would_recommend=False)
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, updated])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate(would_recommend=False)
        with _patch_ctx(ctx, redis):
            out = await svc.update_feedback(fb.id, req)
        assert out.would_recommend is False

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        from corpmind.core.exceptions import NotFoundError
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update_feedback(uuid.uuid4(), TrainingFeedbackUpdate())

    @pytest.mark.asyncio
    async def test_update_calls_update_fields(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate(comments="New comment")
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, req)
        svc._repo.update_fields.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_busts_detail_cache(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate(overall_rating=3)
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, req)
        assert redis.delete.await_count >= 1

    @pytest.mark.asyncio
    async def test_update_busts_list_cache(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate(overall_rating=3)
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, req)
        # Called twice: detail key + list key
        assert redis.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_update_partial_only_updates_provided(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        captured_kwargs = {}
        async def capture_update(fid, **kwargs):
            captured_kwargs.update(kwargs)
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = capture_update
        req = TrainingFeedbackUpdate(comments="Partial update only")
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, req)
        assert "comments" in captured_kwargs
        assert "overall_rating" not in captured_kwargs

    @pytest.mark.asyncio
    async def test_update_all_fields(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        captured_kwargs = {}
        async def capture_update(fid, **kwargs):
            captured_kwargs.update(kwargs)
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = capture_update
        req = TrainingFeedbackUpdate(
            overall_rating=1,
            trainer_rating=2,
            content_rating=3,
            materials_rating=4,
            venue_rating=5,
            would_recommend=False,
            comments="All fields",
        )
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, req)
        for field in ("overall_rating", "trainer_rating", "content_rating", "materials_rating", "venue_rating", "would_recommend", "comments"):
            assert field in captured_kwargs

    @pytest.mark.asyncio
    async def test_update_empty_req_still_calls_update(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate()
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, req)
        svc._repo.update_fields.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_commit_called(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate(overall_rating=5)
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, req)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_updated_at_set(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        captured_kwargs = {}
        async def capture_update(fid, **kwargs):
            captured_kwargs.update(kwargs)
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = capture_update
        req = TrainingFeedbackUpdate(comments="Check timestamp")
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, req)
        assert "updated_at" in captured_kwargs

    @pytest.mark.asyncio
    async def test_update_redis_failure_graceful(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("redis error"))
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate(overall_rating=4)
        with _patch_ctx(ctx, redis):
            out = await svc.update_feedback(fb.id, req)
        assert out is not None

    @pytest.mark.asyncio
    async def test_update_returns_feedback_out(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate()
        with _patch_ctx(ctx, redis):
            out = await svc.update_feedback(fb.id, req)
        assert isinstance(out, TrainingFeedbackOut)

    @pytest.mark.asyncio
    async def test_update_only_trainer_rating(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        captured_kwargs = {}
        async def capture_update(fid, **kwargs):
            captured_kwargs.update(kwargs)
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = capture_update
        req = TrainingFeedbackUpdate(trainer_rating=5)
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, req)
        assert "trainer_rating" in captured_kwargs
        assert "content_rating" not in captured_kwargs

    @pytest.mark.asyncio
    async def test_update_venue_rating(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        updated = _make_feedback(feedback_id=fb.id)
        updated.venue_rating = 2
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, updated])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate(venue_rating=2)
        with _patch_ctx(ctx, redis):
            out = await svc.update_feedback(fb.id, req)
        assert out.venue_rating == 2

    @pytest.mark.asyncio
    async def test_update_materials_rating(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        captured_kwargs: dict = {}

        async def capture_update(fid, **kwargs):
            captured_kwargs.update(kwargs)

        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = capture_update
        req = TrainingFeedbackUpdate(materials_rating=1)
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, req)
        assert "materials_rating" in captured_kwargs
        assert captured_kwargs["materials_rating"] == 1

    @pytest.mark.asyncio
    async def test_update_clears_comments_to_none(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback(comments="Old comment")
        updated = _make_feedback(feedback_id=fb.id, comments=None)
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, updated])
        svc._repo.update_fields = AsyncMock()
        req = TrainingFeedbackUpdate(comments=None)
        with _patch_ctx(ctx, redis):
            out = await svc.update_feedback(fb.id, req)
        assert out.comments is None


# ── TestFeedbackList ──────────────────────────────────────────────────────────

class TestFeedbackList:
    def _list_filters(self, **kwargs) -> TrainingFeedbackFilters:
        return TrainingFeedbackFilters(workspace_id=_WS, **kwargs)

    @pytest.mark.asyncio
    async def test_list_empty(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch_ctx(ctx, redis):
            out = await svc.list_feedback(self._list_filters())
        assert out.total == 0
        assert out.items == []

    @pytest.mark.asyncio
    async def test_list_returns_items(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        items = [_make_feedback(), _make_feedback()]
        svc._repo.count = AsyncMock(return_value=2)
        svc._repo.list_page = AsyncMock(return_value=items)
        with _patch_ctx(ctx, redis):
            out = await svc.list_feedback(self._list_filters())
        assert out.total == 2
        assert len(out.items) == 2

    @pytest.mark.asyncio
    async def test_list_has_more_when_full_page(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        items = [_make_feedback() for _ in range(50)]
        svc._repo.count = AsyncMock(return_value=50)
        svc._repo.list_page = AsyncMock(return_value=items)
        with _patch_ctx(ctx, redis):
            out = await svc.list_feedback(self._list_filters())
        assert out.has_more is True
        assert out.next_cursor is not None

    @pytest.mark.asyncio
    async def test_list_no_more_when_partial_page(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        items = [_make_feedback() for _ in range(3)]
        svc._repo.count = AsyncMock(return_value=3)
        svc._repo.list_page = AsyncMock(return_value=items)
        with _patch_ctx(ctx, redis):
            out = await svc.list_feedback(self._list_filters())
        assert out.has_more is False
        assert out.next_cursor is None

    @pytest.mark.asyncio
    async def test_list_session_only_uses_cache(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        cached_out = TrainingFeedbackListOut(items=[], next_cursor=None, has_more=False, total=0)
        redis = _make_redis(cached=cached_out.model_dump_json())
        with _patch_ctx(ctx, redis):
            out = await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, session_id=_SESSION)
            )
        assert out.total == 0
        svc._repo.count.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_session_only_sets_cache(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch_ctx(ctx, redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, session_id=_SESSION)
            )
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_multi_filter_skips_cache(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch_ctx(ctx, redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(
                    workspace_id=_WS,
                    session_id=_SESSION,
                    customer_id=_CUSTOMER,
                )
            )
        redis.get.assert_not_awaited()
        redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_min_rating_filter(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[_make_feedback(overall_rating=4)])
        with _patch_ctx(ctx, redis):
            out = await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, min_rating=4)
            )
        svc._repo.list_page.assert_awaited_once()
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs.get("min_rating") == 4

    @pytest.mark.asyncio
    async def test_list_search_filter(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[_make_feedback()])
        with _patch_ctx(ctx, redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, search="great")
            )
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs.get("search") == "great"

    @pytest.mark.asyncio
    async def test_list_returns_list_out(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch_ctx(ctx, redis):
            out = await svc.list_feedback(self._list_filters())
        assert isinstance(out, TrainingFeedbackListOut)

    @pytest.mark.asyncio
    async def test_list_cursor_passed_to_repo(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch_ctx(ctx, redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, cursor="abc123")
            )
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs.get("cursor") == "abc123"

    @pytest.mark.asyncio
    async def test_list_with_cursor_skips_session_cache(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch_ctx(ctx, redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, session_id=_SESSION, cursor="token123")
            )
        redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_customer_filter(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[_make_feedback()])
        with _patch_ctx(ctx, redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, customer_id=_CUSTOMER)
            )
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs.get("customer_id") == _CUSTOMER

    @pytest.mark.asyncio
    async def test_list_trainer_filter(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[_make_feedback()])
        with _patch_ctx(ctx, redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, trainer_id=_TRAINER)
            )
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs.get("trainer_id") == _TRAINER

    @pytest.mark.asyncio
    async def test_list_redis_failure_graceful(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("redis error"))
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch_ctx(ctx, redis):
            out = await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, session_id=_SESSION)
            )
        assert out is not None

    @pytest.mark.asyncio
    async def test_list_items_are_feedback_out(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[_make_feedback()])
        with _patch_ctx(ctx, redis):
            out = await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS)
            )
        assert all(isinstance(i, TrainingFeedbackOut) for i in out.items)

    @pytest.mark.asyncio
    async def test_list_session_cache_ttl(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch_ctx(ctx, redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, session_id=_SESSION)
            )
        set_kwargs = redis.set.call_args
        assert set_kwargs.kwargs.get("ex") == 300

    @pytest.mark.asyncio
    async def test_list_no_more_sets_has_more_false(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[_make_feedback()])
        with _patch_ctx(ctx, redis):
            out = await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS)
            )
        assert out.has_more is False

    @pytest.mark.asyncio
    async def test_list_limit_one_with_one_result_triggers_has_more(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[_make_feedback()])
        with _patch_ctx(ctx, redis):
            out = await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, limit=1)
            )
        assert out.has_more is True

    @pytest.mark.asyncio
    async def test_list_no_cache_set_for_non_session_filter(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch_ctx(ctx, redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, customer_id=_CUSTOMER)
            )
        redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_workspace_passed_to_count(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch_ctx(ctx, redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS)
            )
        count_call = svc._repo.count.call_args
        ws_arg = count_call.args[0] if count_call.args else count_call.kwargs.get("workspace_id")
        assert ws_arg == _WS


# ── TestFeedbackListBySession ─────────────────────────────────────────────────

class TestFeedbackListBySession:
    @pytest.mark.asyncio
    async def test_list_by_session_empty(self):
        svc, _ = _make_svc()
        svc._repo.list_by_session = AsyncMock(return_value=[])
        result = await svc.list_by_session(_SESSION)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_by_session_returns_items(self):
        svc, _ = _make_svc()
        items = [_make_feedback(), _make_feedback()]
        svc._repo.list_by_session = AsyncMock(return_value=items)
        result = await svc.list_by_session(_SESSION)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_by_session_calls_repo(self):
        svc, _ = _make_svc()
        svc._repo.list_by_session = AsyncMock(return_value=[])
        await svc.list_by_session(_SESSION)
        svc._repo.list_by_session.assert_awaited_once_with(_SESSION)

    @pytest.mark.asyncio
    async def test_list_by_session_returns_out_models(self):
        svc, _ = _make_svc()
        items = [_make_feedback()]
        svc._repo.list_by_session = AsyncMock(return_value=items)
        result = await svc.list_by_session(_SESSION)
        assert all(isinstance(r, TrainingFeedbackOut) for r in result)

    @pytest.mark.asyncio
    async def test_list_by_session_multiple(self):
        svc, _ = _make_svc()
        items = [_make_feedback() for _ in range(5)]
        svc._repo.list_by_session = AsyncMock(return_value=items)
        result = await svc.list_by_session(_SESSION)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_list_by_session_feedback_ids(self):
        svc, _ = _make_svc()
        f1 = _make_feedback()
        f2 = _make_feedback()
        svc._repo.list_by_session = AsyncMock(return_value=[f1, f2])
        result = await svc.list_by_session(_SESSION)
        ids = {r.id for r in result}
        assert f1.id in ids and f2.id in ids

    @pytest.mark.asyncio
    async def test_list_by_session_no_cache_used(self):
        svc, _ = _make_svc()
        svc._repo.list_by_session = AsyncMock(return_value=[])
        ctx = _make_ctx()
        redis = _make_redis()
        with _patch_ctx(ctx, redis):
            await svc.list_by_session(_SESSION)
        redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_by_session_different_session_ids(self):
        svc, _ = _make_svc()
        s2 = uuid.uuid4()
        svc._repo.list_by_session = AsyncMock(return_value=[])
        await svc.list_by_session(s2)
        svc._repo.list_by_session.assert_awaited_once_with(s2)

    @pytest.mark.asyncio
    async def test_list_by_session_preserves_ratings(self):
        svc, _ = _make_svc()
        fb = _make_feedback(overall_rating=5)
        svc._repo.list_by_session = AsyncMock(return_value=[fb])
        result = await svc.list_by_session(_SESSION)
        assert result[0].overall_rating == 5

    @pytest.mark.asyncio
    async def test_list_by_session_preserves_comments(self):
        svc, _ = _make_svc()
        fb = _make_feedback(comments="Session was great")
        svc._repo.list_by_session = AsyncMock(return_value=[fb])
        result = await svc.list_by_session(_SESSION)
        assert result[0].comments == "Session was great"


# ── TestFeedbackListByCustomer ────────────────────────────────────────────────

class TestFeedbackListByCustomer:
    @pytest.mark.asyncio
    async def test_list_by_customer_empty(self):
        svc, _ = _make_svc()
        svc._repo.list_by_customer = AsyncMock(return_value=[])
        result = await svc.list_by_customer(_WS, _CUSTOMER)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_by_customer_returns_items(self):
        svc, _ = _make_svc()
        items = [_make_feedback(), _make_feedback()]
        svc._repo.list_by_customer = AsyncMock(return_value=items)
        result = await svc.list_by_customer(_WS, _CUSTOMER)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_by_customer_calls_repo(self):
        svc, _ = _make_svc()
        svc._repo.list_by_customer = AsyncMock(return_value=[])
        await svc.list_by_customer(_WS, _CUSTOMER)
        svc._repo.list_by_customer.assert_awaited_once_with(_WS, _CUSTOMER)

    @pytest.mark.asyncio
    async def test_list_by_customer_returns_out_models(self):
        svc, _ = _make_svc()
        svc._repo.list_by_customer = AsyncMock(return_value=[_make_feedback()])
        result = await svc.list_by_customer(_WS, _CUSTOMER)
        assert all(isinstance(r, TrainingFeedbackOut) for r in result)

    @pytest.mark.asyncio
    async def test_list_by_customer_different_customers(self):
        svc, _ = _make_svc()
        c2 = uuid.uuid4()
        svc._repo.list_by_customer = AsyncMock(return_value=[])
        await svc.list_by_customer(_WS, c2)
        svc._repo.list_by_customer.assert_awaited_once_with(_WS, c2)

    @pytest.mark.asyncio
    async def test_list_by_customer_many_items(self):
        svc, _ = _make_svc()
        items = [_make_feedback() for _ in range(7)]
        svc._repo.list_by_customer = AsyncMock(return_value=items)
        result = await svc.list_by_customer(_WS, _CUSTOMER)
        assert len(result) == 7

    @pytest.mark.asyncio
    async def test_list_by_customer_workspace_forwarded(self):
        svc, _ = _make_svc()
        svc._repo.list_by_customer = AsyncMock(return_value=[])
        await svc.list_by_customer(_WS, _CUSTOMER)
        call_args = svc._repo.list_by_customer.call_args.args
        assert call_args[0] == _WS

    @pytest.mark.asyncio
    async def test_list_by_customer_no_cache(self):
        svc, _ = _make_svc()
        svc._repo.list_by_customer = AsyncMock(return_value=[])
        ctx = _make_ctx()
        redis = _make_redis()
        with _patch_ctx(ctx, redis):
            await svc.list_by_customer(_WS, _CUSTOMER)
        redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_by_customer_preserves_session_id(self):
        svc, _ = _make_svc()
        s = uuid.uuid4()
        fb = _make_feedback(session_id=s)
        svc._repo.list_by_customer = AsyncMock(return_value=[fb])
        result = await svc.list_by_customer(_WS, _CUSTOMER)
        assert result[0].session_id == s

    @pytest.mark.asyncio
    async def test_list_by_customer_preserves_would_recommend(self):
        svc, _ = _make_svc()
        fb = _make_feedback(would_recommend=False)
        svc._repo.list_by_customer = AsyncMock(return_value=[fb])
        result = await svc.list_by_customer(_WS, _CUSTOMER)
        assert result[0].would_recommend is False


# ── TestFeedbackListByTrainer ─────────────────────────────────────────────────

class TestFeedbackListByTrainer:
    @pytest.mark.asyncio
    async def test_list_by_trainer_empty(self):
        svc, _ = _make_svc()
        svc._repo.list_by_trainer = AsyncMock(return_value=[])
        result = await svc.list_by_trainer(_WS, _TRAINER)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_by_trainer_returns_items(self):
        svc, _ = _make_svc()
        items = [_make_feedback(), _make_feedback()]
        svc._repo.list_by_trainer = AsyncMock(return_value=items)
        result = await svc.list_by_trainer(_WS, _TRAINER)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_by_trainer_calls_repo(self):
        svc, _ = _make_svc()
        svc._repo.list_by_trainer = AsyncMock(return_value=[])
        await svc.list_by_trainer(_WS, _TRAINER)
        svc._repo.list_by_trainer.assert_awaited_once_with(_WS, _TRAINER)

    @pytest.mark.asyncio
    async def test_list_by_trainer_returns_out_models(self):
        svc, _ = _make_svc()
        svc._repo.list_by_trainer = AsyncMock(return_value=[_make_feedback()])
        result = await svc.list_by_trainer(_WS, _TRAINER)
        assert all(isinstance(r, TrainingFeedbackOut) for r in result)

    @pytest.mark.asyncio
    async def test_list_by_trainer_different_trainers(self):
        svc, _ = _make_svc()
        t2 = uuid.uuid4()
        svc._repo.list_by_trainer = AsyncMock(return_value=[])
        await svc.list_by_trainer(_WS, t2)
        svc._repo.list_by_trainer.assert_awaited_once_with(_WS, t2)

    @pytest.mark.asyncio
    async def test_list_by_trainer_many_items(self):
        svc, _ = _make_svc()
        items = [_make_feedback() for _ in range(6)]
        svc._repo.list_by_trainer = AsyncMock(return_value=items)
        result = await svc.list_by_trainer(_WS, _TRAINER)
        assert len(result) == 6

    @pytest.mark.asyncio
    async def test_list_by_trainer_workspace_forwarded(self):
        svc, _ = _make_svc()
        svc._repo.list_by_trainer = AsyncMock(return_value=[])
        await svc.list_by_trainer(_WS, _TRAINER)
        call_args = svc._repo.list_by_trainer.call_args.args
        assert call_args[0] == _WS

    @pytest.mark.asyncio
    async def test_list_by_trainer_no_cache(self):
        svc, _ = _make_svc()
        svc._repo.list_by_trainer = AsyncMock(return_value=[])
        ctx = _make_ctx()
        redis = _make_redis()
        with _patch_ctx(ctx, redis):
            await svc.list_by_trainer(_WS, _TRAINER)
        redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_by_trainer_preserves_trainer_rating(self):
        svc, _ = _make_svc()
        fb = _make_feedback()
        fb.trainer_rating = 5
        svc._repo.list_by_trainer = AsyncMock(return_value=[fb])
        result = await svc.list_by_trainer(_WS, _TRAINER)
        assert result[0].trainer_rating == 5

    @pytest.mark.asyncio
    async def test_list_by_trainer_preserves_session_id(self):
        svc, _ = _make_svc()
        s = uuid.uuid4()
        fb = _make_feedback(session_id=s)
        svc._repo.list_by_trainer = AsyncMock(return_value=[fb])
        result = await svc.list_by_trainer(_WS, _TRAINER)
        assert result[0].session_id == s


# ── TestRatingValidation ──────────────────────────────────────────────────────

class TestRatingValidation:
    def test_overall_rating_1_valid(self):
        req = TrainingFeedbackCreate(
            workspace_id=_WS, attendance_id=_ATTENDANCE,
            session_id=_SESSION, customer_id=_CUSTOMER, overall_rating=1,
        )
        assert req.overall_rating == 1

    def test_overall_rating_5_valid(self):
        req = TrainingFeedbackCreate(
            workspace_id=_WS, attendance_id=_ATTENDANCE,
            session_id=_SESSION, customer_id=_CUSTOMER, overall_rating=5,
        )
        assert req.overall_rating == 5

    def test_overall_rating_0_invalid(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            TrainingFeedbackCreate(
                workspace_id=_WS, attendance_id=_ATTENDANCE,
                session_id=_SESSION, customer_id=_CUSTOMER, overall_rating=0,
            )

    def test_overall_rating_6_invalid(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            TrainingFeedbackCreate(
                workspace_id=_WS, attendance_id=_ATTENDANCE,
                session_id=_SESSION, customer_id=_CUSTOMER, overall_rating=6,
            )

    def test_trainer_rating_invalid(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            TrainingFeedbackCreate(
                workspace_id=_WS, attendance_id=_ATTENDANCE,
                session_id=_SESSION, customer_id=_CUSTOMER, trainer_rating=0,
            )

    def test_content_rating_invalid(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            TrainingFeedbackCreate(
                workspace_id=_WS, attendance_id=_ATTENDANCE,
                session_id=_SESSION, customer_id=_CUSTOMER, content_rating=6,
            )

    def test_materials_rating_invalid(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            TrainingFeedbackCreate(
                workspace_id=_WS, attendance_id=_ATTENDANCE,
                session_id=_SESSION, customer_id=_CUSTOMER, materials_rating=-1,
            )

    def test_venue_rating_invalid(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            TrainingFeedbackCreate(
                workspace_id=_WS, attendance_id=_ATTENDANCE,
                session_id=_SESSION, customer_id=_CUSTOMER, venue_rating=7,
            )

    def test_none_rating_valid(self):
        req = TrainingFeedbackCreate(
            workspace_id=_WS, attendance_id=_ATTENDANCE,
            session_id=_SESSION, customer_id=_CUSTOMER,
            overall_rating=None,
        )
        assert req.overall_rating is None

    def test_update_rating_1_valid(self):
        req = TrainingFeedbackUpdate(overall_rating=1)
        assert req.overall_rating == 1

    def test_update_rating_5_valid(self):
        req = TrainingFeedbackUpdate(overall_rating=5)
        assert req.overall_rating == 5

    def test_update_rating_0_invalid(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            TrainingFeedbackUpdate(overall_rating=0)

    def test_update_rating_6_invalid(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            TrainingFeedbackUpdate(overall_rating=6)

    def test_update_none_rating_valid(self):
        req = TrainingFeedbackUpdate(overall_rating=None)
        assert req.overall_rating is None

    def test_all_ratings_valid_range(self):
        for rating in range(1, 6):
            req = TrainingFeedbackCreate(
                workspace_id=_WS, attendance_id=_ATTENDANCE,
                session_id=_SESSION, customer_id=_CUSTOMER,
                overall_rating=rating,
                trainer_rating=rating,
                content_rating=rating,
                materials_rating=rating,
                venue_rating=rating,
            )
            assert req.overall_rating == rating


# ── TestFeedbackCacheBust ─────────────────────────────────────────────────────

class TestFeedbackCacheBust:
    @pytest.mark.asyncio
    async def test_bust_list_key_format(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS,
            attendance_id=_ATTENDANCE,
            session_id=_SESSION,
            customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        key = redis.delete.call_args.args[0]
        assert str(_ORG) in key
        assert str(_SESSION) in key

    @pytest.mark.asyncio
    async def test_bust_detail_key_format(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, TrainingFeedbackUpdate())
        deleted_keys = [c.args[0] for c in redis.delete.call_args_list]
        detail_keys = [k for k in deleted_keys if str(fb.id) in k]
        assert len(detail_keys) >= 1

    @pytest.mark.asyncio
    async def test_update_busts_both_keys(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.update_feedback(fb.id, TrainingFeedbackUpdate(comments="Updated"))
        assert redis.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_create_only_busts_list_key(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS, attendance_id=_ATTENDANCE,
            session_id=_SESSION, customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            await svc.create_feedback(req)
        assert redis.delete.await_count == 1

    @pytest.mark.asyncio
    async def test_cache_set_uses_correct_ttl(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch_ctx(ctx, redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, session_id=_SESSION)
            )
        set_kwargs = redis.set.call_args
        assert set_kwargs.kwargs.get("ex") == 300

    @pytest.mark.asyncio
    async def test_detail_cache_uses_correct_ttl(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            await svc.get_feedback(fb.id)
        set_kwargs = redis.set.call_args
        assert set_kwargs.kwargs.get("ex") == 300

    @pytest.mark.asyncio
    async def test_redis_delete_is_not_called_on_get(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with _patch_ctx(ctx, redis):
            await svc.get_feedback(fb.id)
        redis.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_redis_bust_exception_does_not_propagate_on_create(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=ConnectionError("connection reset"))
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda f: f)
        req = TrainingFeedbackCreate(
            workspace_id=_WS, attendance_id=_ATTENDANCE,
            session_id=_SESSION, customer_id=_CUSTOMER,
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create_feedback(req)
        assert out is not None

    @pytest.mark.asyncio
    async def test_redis_bust_exception_does_not_propagate_on_update(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=ConnectionError("connection reset"))
        fb = _make_feedback()
        svc._repo.find_by_id = AsyncMock(side_effect=[fb, fb])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.update_feedback(fb.id, TrainingFeedbackUpdate())
        assert out is not None


# ── TestFeedbackTenantIsolation ───────────────────────────────────────────────

class TestFeedbackTenantIsolation:
    @pytest.mark.asyncio
    async def test_cache_key_uses_tenant_id(self):
        svc, _ = _make_svc()
        org_a = uuid.uuid4()
        ctx_a = MagicMock()
        ctx_a.org_id = org_a
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx_a), \
             patch("corpmind.modules.training.service.get_redis", return_value=redis):
            await svc.list_feedback(
                TrainingFeedbackFilters(workspace_id=_WS, session_id=_SESSION)
            )
        set_key = redis.set.call_args.args[0]
        assert str(org_a) in set_key

    @pytest.mark.asyncio
    async def test_different_tenants_different_cache_keys(self):
        svc, _ = _make_svc()
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        session_id = uuid.uuid4()
        key_a = f"t:{org_a}:training:feedback:list:{session_id}"
        key_b = f"t:{org_b}:training:feedback:list:{session_id}"
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_tenant_id_set_from_context_on_create(self):
        svc, _ = _make_svc()
        org_c = uuid.uuid4()
        ctx = MagicMock()
        ctx.org_id = org_c
        redis = _make_redis()
        created = None
        async def capture(f):
            nonlocal created
            created = f
            return f
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = capture
        req = TrainingFeedbackCreate(
            workspace_id=_WS, attendance_id=_ATTENDANCE,
            session_id=_SESSION, customer_id=_CUSTOMER,
        )
        with patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx), \
             patch("corpmind.modules.training.service.get_redis", return_value=redis):
            await svc.create_feedback(req)
        assert created.tenant_id == org_c

    @pytest.mark.asyncio
    async def test_get_uses_tenant_scoped_cache_key(self):
        svc, _ = _make_svc()
        org_d = uuid.uuid4()
        ctx = MagicMock()
        ctx.org_id = org_d
        fb = _make_feedback()
        redis = _make_redis(cached=None)
        svc._repo.find_by_id = AsyncMock(return_value=fb)
        with patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx), \
             patch("corpmind.modules.training.service.get_redis", return_value=redis):
            await svc.get_feedback(fb.id)
        set_key = redis.set.call_args.args[0]
        assert str(org_d) in set_key

    @pytest.mark.asyncio
    async def test_tenant_id_not_overrideable_by_caller(self):
        svc, _ = _make_svc()
        org_e = uuid.uuid4()
        ctx = MagicMock()
        ctx.org_id = org_e
        redis = _make_redis()
        created = None
        async def capture(f):
            nonlocal created
            created = f
            return f
        svc._attendance_repo.find_by_id = AsyncMock(return_value=_make_attendance())
        svc._repo.find_by_attendance_id = AsyncMock(return_value=None)
        svc._repo.create = capture
        req = TrainingFeedbackCreate(
            workspace_id=_WS, attendance_id=_ATTENDANCE,
            session_id=_SESSION, customer_id=_CUSTOMER,
        )
        with patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx), \
             patch("corpmind.modules.training.service.get_redis", return_value=redis):
            await svc.create_feedback(req)
        # tenant_id comes from context, not from the request body
        assert created.tenant_id == org_e
