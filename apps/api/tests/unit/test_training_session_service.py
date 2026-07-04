"""Unit tests for TrainingSessionService — Sprint 43.

Pure unit tests: no database, no real Redis.
All repo and Redis interactions are mocked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.modules.training.models import TrainingSession
from corpmind.modules.training.schemas import (
    CancelSession,
    CompleteSession,
    TrainingSessionCreate,
    TrainingSessionFilters,
    TrainingSessionUpdate,
)
from corpmind.modules.training.service import (
    TrainingSessionService,
    _SESSION_TRANSITIONS,
    _session_detail_key,
    _session_list_key,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 7, 3, 10, 0, 0, tzinfo=UTC)
_ORG = uuid.uuid4()
_WS = uuid.uuid4()
_ENG = uuid.uuid4()
_SID = uuid.uuid4()
_TRAINER = uuid.uuid4()


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = _ORG
    ctx.user_id = uuid.uuid4()
    return ctx


def _make_redis(cached: str | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _make_session(
    *,
    status: str = "planned",
    engagement_id: uuid.UUID | None = None,
    trainer_id: uuid.UUID | None = None,
    session_number: int | None = 1,
    actual_attendees: int | None = None,
) -> TrainingSession:
    s = TrainingSession()
    s.id = _SID
    s.tenant_id = _ORG
    s.workspace_id = _WS
    s.engagement_id = engagement_id or _ENG
    s.session_name = "Day 1 Morning"
    s.session_number = session_number
    s.status = status
    s.scheduled_start = _NOW + timedelta(hours=1)
    s.scheduled_end = _NOW + timedelta(hours=5)
    s.actual_start = None
    s.actual_end = None
    s.trainer_id = trainer_id
    s.location = "Training Room A"
    s.meeting_link = None
    s.capacity = 30
    s.expected_attendees = 25
    s.actual_attendees = actual_attendees
    s.notes = None
    s.created_at = _NOW
    s.updated_at = _NOW
    return s


def _make_svc() -> tuple[TrainingSessionService, MagicMock]:
    db_session = MagicMock()
    db_session.commit = AsyncMock()
    svc = TrainingSessionService(db_session)
    svc._repo = MagicMock()
    return svc, db_session


# ── Key helpers ────────────────────────────────────────────────────────────────

class TestCacheKeys:
    def test_list_key_format(self) -> None:
        key = _session_list_key(_ORG, _ENG)
        assert f"t:{_ORG}" in key
        assert str(_ENG) in key
        assert "sessions" in key

    def test_detail_key_format(self) -> None:
        key = _session_detail_key(_ORG, _SID)
        assert f"t:{_ORG}" in key
        assert str(_SID) in key
        assert "sessions" in key

    def test_list_key_is_tenant_scoped(self) -> None:
        org2 = uuid.uuid4()
        key1 = _session_list_key(_ORG, _ENG)
        key2 = _session_list_key(org2, _ENG)
        assert key1 != key2

    def test_detail_key_is_tenant_scoped(self) -> None:
        org2 = uuid.uuid4()
        key1 = _session_detail_key(_ORG, _SID)
        key2 = _session_detail_key(org2, _SID)
        assert key1 != key2


# ── Status transitions ─────────────────────────────────────────────────────────

class TestSessionTransitions:
    def test_planned_can_go_to_scheduled(self) -> None:
        assert "scheduled" in _SESSION_TRANSITIONS["planned"]

    def test_planned_can_go_to_in_progress(self) -> None:
        assert "in_progress" in _SESSION_TRANSITIONS["planned"]

    def test_planned_can_go_to_cancelled(self) -> None:
        assert "cancelled" in _SESSION_TRANSITIONS["planned"]

    def test_planned_cannot_go_to_completed(self) -> None:
        assert "completed" not in _SESSION_TRANSITIONS["planned"]

    def test_scheduled_can_go_to_in_progress(self) -> None:
        assert "in_progress" in _SESSION_TRANSITIONS["scheduled"]

    def test_scheduled_can_go_to_cancelled(self) -> None:
        assert "cancelled" in _SESSION_TRANSITIONS["scheduled"]

    def test_scheduled_cannot_go_to_planned(self) -> None:
        assert "planned" not in _SESSION_TRANSITIONS["scheduled"]

    def test_in_progress_can_go_to_completed(self) -> None:
        assert "completed" in _SESSION_TRANSITIONS["in_progress"]

    def test_in_progress_can_go_to_cancelled(self) -> None:
        assert "cancelled" in _SESSION_TRANSITIONS["in_progress"]

    def test_in_progress_cannot_go_to_planned(self) -> None:
        assert "planned" not in _SESSION_TRANSITIONS["in_progress"]

    def test_completed_is_terminal(self) -> None:
        assert len(_SESSION_TRANSITIONS["completed"]) == 0

    def test_cancelled_is_terminal(self) -> None:
        assert len(_SESSION_TRANSITIONS["cancelled"]) == 0


# ── create_session ─────────────────────────────────────────────────────────────

class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_returns_out(self) -> None:
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            req = TrainingSessionCreate(
                workspace_id=_WS,
                engagement_id=_ENG,
                session_name="Day 1 Morning",
            )
            result = await svc.create_session(req)

        assert result.session_name == "Day 1 Morning"
        assert result.engagement_id == _ENG
        assert result.workspace_id == _WS
        assert result.status == "planned"

    @pytest.mark.asyncio
    async def test_create_busts_list_cache(self) -> None:
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            req = TrainingSessionCreate(
                workspace_id=_WS,
                engagement_id=_ENG,
                session_name="Session A",
            )
            await svc.create_session(req)

        redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_with_all_optional_fields(self) -> None:
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock()
        redis = _make_redis()
        trainer_id = uuid.uuid4()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            req = TrainingSessionCreate(
                workspace_id=_WS,
                engagement_id=_ENG,
                session_name="Day 2",
                session_number=2,
                status="scheduled",
                trainer_id=trainer_id,
                capacity=50,
                expected_attendees=40,
                notes="Bring laptops",
            )
            result = await svc.create_session(req)

        assert result.session_number == 2
        assert result.status == "scheduled"
        assert result.trainer_id == trainer_id
        assert result.capacity == 50
        assert result.notes == "Bring laptops"

    @pytest.mark.asyncio
    async def test_create_sets_tenant_id_from_context(self) -> None:
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            req = TrainingSessionCreate(
                workspace_id=_WS,
                engagement_id=_ENG,
                session_name="S",
            )
            result = await svc.create_session(req)

        assert result.tenant_id == _ORG

    @pytest.mark.asyncio
    async def test_create_actual_start_is_none(self) -> None:
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            req = TrainingSessionCreate(
                workspace_id=_WS,
                engagement_id=_ENG,
                session_name="S",
            )
            result = await svc.create_session(req)

        assert result.actual_start is None
        assert result.actual_end is None
        assert result.actual_attendees is None

    @pytest.mark.asyncio
    async def test_create_redis_error_does_not_propagate(self) -> None:
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("Redis down"))

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            req = TrainingSessionCreate(
                workspace_id=_WS,
                engagement_id=_ENG,
                session_name="S",
            )
            result = await svc.create_session(req)

        assert result.session_name == "S"


# ── get_session ────────────────────────────────────────────────────────────────

class TestGetSession:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db(self) -> None:
        svc, _ = _make_svc()
        session_obj = _make_session()
        from corpmind.modules.training.schemas import TrainingSessionOut

        cached_json = TrainingSessionOut.model_validate(session_obj).model_dump_json()
        redis = _make_redis(cached=cached_json)

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            result = await svc.get_session(_SID)

        assert result.id == _SID
        svc._repo.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_hits_db_and_stores(self) -> None:
        svc, _ = _make_svc()
        session_obj = _make_session()
        svc._repo.find_by_id = AsyncMock(return_value=session_obj)
        redis = _make_redis(cached=None)

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            result = await svc.get_session(_SID)

        assert result.id == _SID
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        redis = _make_redis(cached=None)

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            with pytest.raises(NotFoundError):
                await svc.get_session(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_redis_get_error_falls_back_to_db(self) -> None:
        svc, _ = _make_svc()
        session_obj = _make_session()
        svc._repo.find_by_id = AsyncMock(return_value=session_obj)
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("Redis error"))

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            result = await svc.get_session(_SID)

        assert result.id == _SID


# ── update_session ─────────────────────────────────────────────────────────────

class TestUpdateSession:
    @pytest.mark.asyncio
    async def test_update_not_found_raises(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)

        with patch(
            "corpmind.modules.training.service.get_tenant_context",
            return_value=_make_ctx(),
        ):
            with pytest.raises(NotFoundError):
                await svc.update_session(
                    uuid.uuid4(), TrainingSessionUpdate(session_name="X")
                )

    @pytest.mark.asyncio
    async def test_update_applies_fields(self) -> None:
        svc, _ = _make_svc()
        session_obj = _make_session()
        svc._repo.find_by_id = AsyncMock(return_value=session_obj)
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()

        updated = _make_session(status="planned")
        updated.session_name = "Updated Name"

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.update_session(_SID, TrainingSessionUpdate(session_name="Updated Name"))

        svc._repo.update_fields.assert_awaited_once()
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["session_name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_busts_caches(self) -> None:
        svc, _ = _make_svc()
        session_obj = _make_session()
        svc._repo.find_by_id = AsyncMock(return_value=session_obj)
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.update_session(_SID, TrainingSessionUpdate(notes="New"))

        assert redis.delete.await_count == 2


# ── start_session ──────────────────────────────────────────────────────────────

class TestStartSession:
    @pytest.mark.asyncio
    async def test_start_from_planned(self) -> None:
        svc, _ = _make_svc()
        session_obj = _make_session(status="planned")
        svc._repo.find_by_id = AsyncMock(return_value=session_obj)
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.start_session(_SID)

        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["status"] == "in_progress"
        assert call_kwargs["actual_start"] is not None

    @pytest.mark.asyncio
    async def test_start_from_scheduled(self) -> None:
        svc, _ = _make_svc()
        session_obj = _make_session(status="scheduled")
        svc._repo.find_by_id = AsyncMock(return_value=session_obj)
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.start_session(_SID)

        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_start_from_completed_raises(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="completed"))

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
        ):
            with pytest.raises(ValidationError):
                await svc.start_session(_SID)

    @pytest.mark.asyncio
    async def test_start_from_cancelled_raises(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="cancelled"))

        with patch(
            "corpmind.modules.training.service.get_tenant_context",
            return_value=_make_ctx(),
        ):
            with pytest.raises(ValidationError):
                await svc.start_session(_SID)

    @pytest.mark.asyncio
    async def test_start_not_found_raises(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)

        with patch(
            "corpmind.modules.training.service.get_tenant_context",
            return_value=_make_ctx(),
        ):
            with pytest.raises(NotFoundError):
                await svc.start_session(uuid.uuid4())


# ── complete_session ───────────────────────────────────────────────────────────

class TestCompleteSession:
    @pytest.mark.asyncio
    async def test_complete_from_in_progress(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="in_progress"))
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.complete_session(_SID, CompleteSession(actual_attendees=20))

        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["status"] == "completed"
        assert call_kwargs["actual_attendees"] == 20
        assert call_kwargs["actual_end"] is not None

    @pytest.mark.asyncio
    async def test_complete_sets_notes(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="in_progress"))
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.complete_session(
                _SID, CompleteSession(notes="Great session")
            )

        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["notes"] == "Great session"

    @pytest.mark.asyncio
    async def test_complete_from_planned_raises(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="planned"))

        with patch(
            "corpmind.modules.training.service.get_tenant_context",
            return_value=_make_ctx(),
        ):
            with pytest.raises(ValidationError):
                await svc.complete_session(_SID, CompleteSession())

    @pytest.mark.asyncio
    async def test_complete_from_cancelled_raises(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="cancelled"))

        with patch(
            "corpmind.modules.training.service.get_tenant_context",
            return_value=_make_ctx(),
        ):
            with pytest.raises(ValidationError):
                await svc.complete_session(_SID, CompleteSession())

    @pytest.mark.asyncio
    async def test_complete_with_custom_actual_end(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="in_progress"))
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()
        custom_end = _NOW + timedelta(hours=3)

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.complete_session(_SID, CompleteSession(actual_end=custom_end))

        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["actual_end"] == custom_end


# ── cancel_session ─────────────────────────────────────────────────────────────

class TestCancelSession:
    @pytest.mark.asyncio
    async def test_cancel_from_planned(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="planned"))
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.cancel_session(_SID, CancelSession(notes="Venue unavailable"))

        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["status"] == "cancelled"
        assert call_kwargs["notes"] == "Venue unavailable"

    @pytest.mark.asyncio
    async def test_cancel_from_scheduled(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="scheduled"))
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.cancel_session(_SID, CancelSession())

        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_from_in_progress(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="in_progress"))
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.cancel_session(_SID, CancelSession())

        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_from_completed_raises(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="completed"))

        with patch(
            "corpmind.modules.training.service.get_tenant_context",
            return_value=_make_ctx(),
        ):
            with pytest.raises(ValidationError):
                await svc.cancel_session(_SID, CancelSession())

    @pytest.mark.asyncio
    async def test_cancel_without_notes(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_session(status="planned"))
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.cancel_session(_SID, CancelSession())

        call_kwargs = svc._repo.update_fields.call_args[1]
        assert "notes" not in call_kwargs


# ── assign_trainer ─────────────────────────────────────────────────────────────

class TestAssignTrainer:
    @pytest.mark.asyncio
    async def test_assign_trainer_success(self) -> None:
        svc, _ = _make_svc()
        session_obj = _make_session()
        svc._repo.find_by_id = AsyncMock(return_value=session_obj)
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()
        trainer_id = uuid.uuid4()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.assign_trainer(_SID, trainer_id)

        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["trainer_id"] == trainer_id

    @pytest.mark.asyncio
    async def test_assign_trainer_not_found_raises(self) -> None:
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)

        with patch(
            "corpmind.modules.training.service.get_tenant_context",
            return_value=_make_ctx(),
        ):
            with pytest.raises(NotFoundError):
                await svc.assign_trainer(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_assign_trainer_busts_caches(self) -> None:
        svc, _ = _make_svc()
        session_obj = _make_session()
        svc._repo.find_by_id = AsyncMock(return_value=session_obj)
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.assign_trainer(_SID, uuid.uuid4())

        assert redis.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_assign_trainer_redis_error_does_not_propagate(self) -> None:
        svc, _ = _make_svc()
        session_obj = _make_session()
        svc._repo.find_by_id = AsyncMock(return_value=session_obj)
        svc._repo.update_fields = AsyncMock()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("Redis down"))

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
            patch.object(svc, "get_session", AsyncMock(return_value=MagicMock(id=_SID))),
        ):
            await svc.assign_trainer(_SID, uuid.uuid4())


# ── list_sessions ──────────────────────────────────────────────────────────────

class TestListSessions:
    def _make_session_obj(self, engagement_id: uuid.UUID | None = None) -> TrainingSession:
        s = _make_session(engagement_id=engagement_id)
        s.id = uuid.uuid4()
        return s

    @pytest.mark.asyncio
    async def test_list_cache_hit_returns_without_db(self) -> None:
        svc, _ = _make_svc()
        from corpmind.modules.training.schemas import TrainingSessionListOut, TrainingSessionOut

        session_obj = _make_session(engagement_id=_ENG)
        out_item = TrainingSessionOut.model_validate(session_obj)
        cached_data = TrainingSessionListOut(
            items=[out_item], next_cursor=None, has_more=False, total=1
        )
        redis = _make_redis(cached=cached_data.model_dump_json())

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            filters = TrainingSessionFilters(
                workspace_id=_WS, engagement_id=_ENG
            )
            result = await svc.list_sessions(filters)

        assert result.total == 1
        svc._repo.count.assert_not_called()
        svc._repo.list_page.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_cache_miss_hits_db(self) -> None:
        svc, _ = _make_svc()
        session_obj = _make_session(engagement_id=_ENG)
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[session_obj])
        redis = _make_redis(cached=None)

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            filters = TrainingSessionFilters(
                workspace_id=_WS, engagement_id=_ENG
            )
            result = await svc.list_sessions(filters)

        assert result.total == 1
        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_list_has_more_when_full_page(self) -> None:
        svc, _ = _make_svc()
        sessions = [_make_session() for _ in range(50)]
        for i, s in enumerate(sessions):
            s.id = uuid.uuid4()
            s.created_at = _NOW - timedelta(seconds=i)

        svc._repo.count = AsyncMock(return_value=100)
        svc._repo.list_page = AsyncMock(return_value=sessions)
        redis = _make_redis(cached=None)

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            filters = TrainingSessionFilters(workspace_id=_WS, limit=50)
            result = await svc.list_sessions(filters)

        assert result.has_more is True
        assert result.next_cursor is not None

    @pytest.mark.asyncio
    async def test_list_no_more_when_partial_page(self) -> None:
        svc, _ = _make_svc()
        sessions = [_make_session() for _ in range(3)]
        for s in sessions:
            s.id = uuid.uuid4()

        svc._repo.count = AsyncMock(return_value=3)
        svc._repo.list_page = AsyncMock(return_value=sessions)
        redis = _make_redis(cached=None)

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            filters = TrainingSessionFilters(workspace_id=_WS, limit=50)
            result = await svc.list_sessions(filters)

        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_list_with_status_filter_skips_cache(self) -> None:
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        redis = _make_redis(cached="should_not_be_used")

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            filters = TrainingSessionFilters(
                workspace_id=_WS, engagement_id=_ENG, status="planned"
            )
            await svc.list_sessions(filters)

        redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_empty_engagement(self) -> None:
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        redis = _make_redis(cached=None)

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            filters = TrainingSessionFilters(workspace_id=_WS, engagement_id=_ENG)
            result = await svc.list_sessions(filters)

        assert result.total == 0
        assert result.items == []
        assert result.has_more is False


# ── list_by_engagement ─────────────────────────────────────────────────────────

class TestListByEngagement:
    @pytest.mark.asyncio
    async def test_returns_sessions_for_engagement(self) -> None:
        svc, _ = _make_svc()
        s1 = _make_session(session_number=1)
        s2 = _make_session(session_number=2)
        s2.id = uuid.uuid4()
        svc._repo.list_by_engagement = AsyncMock(return_value=[s1, s2])

        result = await svc.list_by_engagement(_ENG)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_sessions(self) -> None:
        svc, _ = _make_svc()
        svc._repo.list_by_engagement = AsyncMock(return_value=[])

        result = await svc.list_by_engagement(_ENG)

        assert result == []


# ── list_by_trainer ────────────────────────────────────────────────────────────

class TestListByTrainer:
    @pytest.mark.asyncio
    async def test_returns_sessions_for_trainer(self) -> None:
        svc, _ = _make_svc()
        s1 = _make_session(trainer_id=_TRAINER)
        s2 = _make_session(trainer_id=_TRAINER)
        s2.id = uuid.uuid4()
        svc._repo.list_by_trainer = AsyncMock(return_value=[s1, s2])

        result = await svc.list_by_trainer(_WS, _TRAINER)

        assert len(result) == 2
        svc._repo.list_by_trainer.assert_awaited_once_with(_WS, _TRAINER)

    @pytest.mark.asyncio
    async def test_returns_empty_when_trainer_has_no_sessions(self) -> None:
        svc, _ = _make_svc()
        svc._repo.list_by_trainer = AsyncMock(return_value=[])

        result = await svc.list_by_trainer(_WS, _TRAINER)

        assert result == []


# ── Schemas validation ─────────────────────────────────────────────────────────

class TestSessionSchemas:
    def test_create_valid(self) -> None:
        req = TrainingSessionCreate(
            workspace_id=_WS,
            engagement_id=_ENG,
            session_name="Morning Session",
        )
        assert req.session_name == "Morning Session"
        assert req.status == "planned"

    def test_create_rejects_empty_name(self) -> None:
        with pytest.raises(Exception):
            TrainingSessionCreate(
                workspace_id=_WS,
                engagement_id=_ENG,
                session_name="  ",
            )

    def test_create_rejects_invalid_status(self) -> None:
        with pytest.raises(Exception):
            TrainingSessionCreate(
                workspace_id=_WS,
                engagement_id=_ENG,
                session_name="S",
                status="invalid",
            )

    def test_create_rejects_negative_capacity(self) -> None:
        with pytest.raises(Exception):
            TrainingSessionCreate(
                workspace_id=_WS,
                engagement_id=_ENG,
                session_name="S",
                capacity=-1,
            )

    def test_create_rejects_zero_session_number(self) -> None:
        with pytest.raises(Exception):
            TrainingSessionCreate(
                workspace_id=_WS,
                engagement_id=_ENG,
                session_name="S",
                session_number=0,
            )

    def test_update_rejects_blank_name(self) -> None:
        with pytest.raises(Exception):
            TrainingSessionUpdate(session_name="  ")

    def test_update_accepts_none_name(self) -> None:
        req = TrainingSessionUpdate(session_name=None)
        assert req.session_name is None

    def test_valid_statuses_are_five(self) -> None:
        from corpmind.modules.training.schemas import VALID_SESSION_STATUSES

        assert len(VALID_SESSION_STATUSES) == 5

    def test_all_expected_statuses_present(self) -> None:
        from corpmind.modules.training.schemas import VALID_SESSION_STATUSES

        for s in ("planned", "scheduled", "in_progress", "completed", "cancelled"):
            assert s in VALID_SESSION_STATUSES


# ── Tenant isolation ───────────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_create_uses_ctx_org_id_not_caller_supplied(self) -> None:
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock()
        redis = _make_redis()
        other_org = uuid.uuid4()
        ctx = _make_ctx()
        ctx.org_id = other_org

        with (
            patch(
                "corpmind.modules.training.service.get_tenant_context",
                return_value=ctx,
            ),
            patch(
                "corpmind.modules.training.service.get_redis",
                return_value=redis,
            ),
        ):
            req = TrainingSessionCreate(
                workspace_id=_WS,
                engagement_id=_ENG,
                session_name="S",
            )
            result = await svc.create_session(req)

        assert result.tenant_id == other_org

    @pytest.mark.asyncio
    async def test_cache_key_includes_org_id(self) -> None:
        org1 = uuid.uuid4()
        org2 = uuid.uuid4()
        key1 = _session_list_key(org1, _ENG)
        key2 = _session_list_key(org2, _ENG)
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_detail_cache_key_includes_org_id(self) -> None:
        org1 = uuid.uuid4()
        org2 = uuid.uuid4()
        key1 = _session_detail_key(org1, _SID)
        key2 = _session_detail_key(org2, _SID)
        assert key1 != key2


# ── Events dataclasses ─────────────────────────────────────────────────────────

class TestSessionEvents:
    def test_created_event_fields(self) -> None:
        from corpmind.modules.training.events import TrainingSessionCreated

        evt = TrainingSessionCreated(
            session_id=_SID,
            engagement_id=_ENG,
            tenant_id=_ORG,
            workspace_id=_WS,
            session_name="Day 1",
        )
        assert evt.session_id == _SID
        assert evt.engagement_id == _ENG
        assert evt.occurred_at is not None

    def test_started_event_fields(self) -> None:
        from corpmind.modules.training.events import TrainingSessionStarted

        evt = TrainingSessionStarted(
            session_id=_SID,
            engagement_id=_ENG,
            tenant_id=_ORG,
        )
        assert evt.session_id == _SID

    def test_completed_event_with_attendees(self) -> None:
        from corpmind.modules.training.events import TrainingSessionCompleted

        evt = TrainingSessionCompleted(
            session_id=_SID,
            engagement_id=_ENG,
            tenant_id=_ORG,
            actual_attendees=42,
        )
        assert evt.actual_attendees == 42

    def test_cancelled_event_fields(self) -> None:
        from corpmind.modules.training.events import TrainingSessionCancelled

        evt = TrainingSessionCancelled(
            session_id=_SID,
            engagement_id=_ENG,
            tenant_id=_ORG,
        )
        assert evt.session_id == _SID

    def test_trainer_assigned_event_fields(self) -> None:
        from corpmind.modules.training.events import TrainingSessionTrainerAssigned

        evt = TrainingSessionTrainerAssigned(
            session_id=_SID,
            engagement_id=_ENG,
            tenant_id=_ORG,
            trainer_id=_TRAINER,
        )
        assert evt.trainer_id == _TRAINER

    def test_events_are_frozen(self) -> None:
        from corpmind.modules.training.events import TrainingSessionCreated

        evt = TrainingSessionCreated(
            session_id=_SID,
            engagement_id=_ENG,
            tenant_id=_ORG,
            workspace_id=_WS,
            session_name="X",
        )
        with pytest.raises(Exception):
            evt.session_name = "Y"  # type: ignore[misc]
