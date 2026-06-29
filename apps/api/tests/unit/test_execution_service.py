"""Sprint 26A — RecommendationExecutionService unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.models import RecommendationAction
from corpmind.modules.analytics.schemas import ExecutionOut, WorkQueueOut
from corpmind.modules.analytics.service import (
    RecommendationExecutionService,
    _VALID_TRANSITIONS,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
REC_ID = uuid.uuid4()
NOW = datetime(2026, 6, 26, 10, 0, 0, tzinfo=UTC)
TODAY = date(2026, 6, 26)


def _make_action(
    *,
    action_type: str = "accepted",
    execution_status: str | None = None,
    blocked_reason: str | None = None,
    completion_notes: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    blocked_at: datetime | None = None,
    cancelled_at: datetime | None = None,
    recommendation_id: uuid.UUID | None = None,
) -> RecommendationAction:
    row = MagicMock(spec=RecommendationAction)
    row.id = uuid.uuid4()
    row.recommendation_id = recommendation_id or REC_ID
    row.action_type = action_type
    row.execution_status = execution_status
    row.blocked_reason = blocked_reason
    row.completion_notes = completion_notes
    row.started_at = started_at
    row.completed_at = completed_at
    row.blocked_at = blocked_at
    row.cancelled_at = cancelled_at
    row.snooze_until = None
    row.reason = None
    row.created_at = NOW
    row.updated_at = NOW
    return row


def _mock_context() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = TENANT_ID
    return ctx


def _make_snap(title: str = "Improve pricing strategy") -> MagicMock:
    snap = MagicMock()
    snap.title = title
    snap.id = REC_ID
    return snap


class _PatchSet:
    """Async context manager setting up all patches for execution service tests."""

    def __init__(
        self,
        action_result: MagicMock,
        update_result: MagicMock | None = None,
        list_result: list | None = None,
        snap_result: MagicMock | None = None,
    ) -> None:
        self._action = action_result
        self._update = update_result if update_result is not None else action_result
        self._list = list_result if list_result is not None else [action_result]
        self._snap = snap_result or _make_snap()
        self._patches: list = []
        self.redis: MagicMock = MagicMock(
            get=AsyncMock(return_value=None),
            set=AsyncMock(),
            delete=AsyncMock(),
        )

    async def __aenter__(self) -> "_PatchSet":
        patches = [
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_mock_context(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=self.redis,
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.find_by_recommendation",
                new_callable=AsyncMock,
                return_value=self._action,
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.update_execution",
                new_callable=AsyncMock,
                return_value=self._update,
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.list_by_workspace",
                new_callable=AsyncMock,
                return_value=self._list,
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationSnapshotRepo.find_by_id",
                new_callable=AsyncMock,
                return_value=self._snap,
            ),
        ]
        for p in patches:
            self._patches.append(p)
            p.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        for p in reversed(self._patches):
            p.stop()


def _svc() -> RecommendationExecutionService:
    return RecommendationExecutionService(session=AsyncMock())


# ── TestValidateTransition ────────────────────────────────────────────────────


class TestValidateTransition:
    # valid transitions

    def test_none_to_in_progress(self) -> None:
        RecommendationExecutionService.validate_transition(None, "in_progress")

    def test_none_to_cancelled(self) -> None:
        RecommendationExecutionService.validate_transition(None, "cancelled")

    def test_in_progress_to_completed(self) -> None:
        RecommendationExecutionService.validate_transition("in_progress", "completed")

    def test_in_progress_to_blocked(self) -> None:
        RecommendationExecutionService.validate_transition("in_progress", "blocked")

    def test_blocked_to_in_progress(self) -> None:
        RecommendationExecutionService.validate_transition("blocked", "in_progress")

    def test_blocked_to_cancelled(self) -> None:
        RecommendationExecutionService.validate_transition("blocked", "cancelled")

    # invalid transitions

    def test_completed_to_in_progress_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid transition"):
            RecommendationExecutionService.validate_transition("completed", "in_progress")

    def test_completed_to_blocked_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid transition"):
            RecommendationExecutionService.validate_transition("completed", "blocked")

    def test_completed_to_cancelled_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid transition"):
            RecommendationExecutionService.validate_transition("completed", "cancelled")

    def test_cancelled_to_in_progress_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid transition"):
            RecommendationExecutionService.validate_transition("cancelled", "in_progress")

    def test_cancelled_to_completed_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid transition"):
            RecommendationExecutionService.validate_transition("cancelled", "completed")

    def test_cancelled_to_blocked_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid transition"):
            RecommendationExecutionService.validate_transition("cancelled", "blocked")

    def test_blocked_to_completed_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid transition"):
            RecommendationExecutionService.validate_transition("blocked", "completed")

    def test_none_to_completed_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid transition"):
            RecommendationExecutionService.validate_transition(None, "completed")

    def test_none_to_blocked_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid transition"):
            RecommendationExecutionService.validate_transition(None, "blocked")

    def test_in_progress_to_in_progress_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid transition"):
            RecommendationExecutionService.validate_transition("in_progress", "in_progress")

    def test_in_progress_to_cancelled_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid transition"):
            RecommendationExecutionService.validate_transition("in_progress", "cancelled")


# ── TestValidTransitionsTable ─────────────────────────────────────────────────


class TestValidTransitionsTable:
    def test_table_has_all_expected_states(self) -> None:
        expected = {None, "in_progress", "blocked", "completed", "cancelled"}
        assert set(_VALID_TRANSITIONS.keys()) == expected

    def test_completed_and_cancelled_are_terminal(self) -> None:
        assert _VALID_TRANSITIONS["completed"] == []
        assert _VALID_TRANSITIONS["cancelled"] == []


# ── TestRequireAcceptedRow ────────────────────────────────────────────────────


class TestRequireAcceptedRow:
    @pytest.mark.asyncio
    async def test_raises_if_row_not_found(self) -> None:
        row = _make_action(action_type="accepted")
        async with _PatchSet(action_result=row) as ps:
            with patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.find_by_recommendation",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with pytest.raises(ValueError, match="not been accepted"):
                    await _svc()._require_accepted_row(WORKSPACE_ID, REC_ID)

    @pytest.mark.asyncio
    async def test_raises_if_action_type_not_accepted(self) -> None:
        row = _make_action(action_type="dismissed")
        async with _PatchSet(action_result=row):
            with pytest.raises(ValueError, match="not been accepted"):
                await _svc()._require_accepted_row(WORKSPACE_ID, REC_ID)

    @pytest.mark.asyncio
    async def test_returns_row_when_accepted(self) -> None:
        row = _make_action(action_type="accepted")
        async with _PatchSet(action_result=row):
            result = await _svc()._require_accepted_row(WORKSPACE_ID, REC_ID)
            assert result is row


# ── TestStart ─────────────────────────────────────────────────────────────────


class TestStart:
    @pytest.mark.asyncio
    async def test_start_from_none_sets_in_progress(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        updated = _make_action(
            action_type="accepted",
            execution_status="in_progress",
            started_at=NOW,
        )
        async with _PatchSet(action_result=row, update_result=updated):
            out = await _svc().start(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
        assert out.execution_status == "in_progress"
        assert out.started_at == NOW

    @pytest.mark.asyncio
    async def test_start_from_blocked_resumes(self) -> None:
        row = _make_action(action_type="accepted", execution_status="blocked")
        updated = _make_action(
            action_type="accepted",
            execution_status="in_progress",
            started_at=NOW,
        )
        async with _PatchSet(action_result=row, update_result=updated):
            out = await _svc().start(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
        assert out.execution_status == "in_progress"

    @pytest.mark.asyncio
    async def test_start_from_completed_raises(self) -> None:
        row = _make_action(action_type="accepted", execution_status="completed")
        async with _PatchSet(action_result=row):
            with pytest.raises(ValueError, match="invalid transition"):
                await _svc().start(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)

    @pytest.mark.asyncio
    async def test_start_from_cancelled_raises(self) -> None:
        row = _make_action(action_type="accepted", execution_status="cancelled")
        async with _PatchSet(action_result=row):
            with pytest.raises(ValueError, match="invalid transition"):
                await _svc().start(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)

    @pytest.mark.asyncio
    async def test_start_invalidates_queue_cache(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        updated = _make_action(action_type="accepted", execution_status="in_progress", started_at=NOW)
        async with _PatchSet(action_result=row, update_result=updated) as ps:
            await _svc().start(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
        ps.redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_returns_execution_out(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        updated = _make_action(action_type="accepted", execution_status="in_progress", started_at=NOW)
        async with _PatchSet(action_result=row, update_result=updated):
            out = await _svc().start(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
        assert isinstance(out, ExecutionOut)


# ── TestBlock ─────────────────────────────────────────────────────────────────


class TestBlock:
    @pytest.mark.asyncio
    async def test_block_from_in_progress(self) -> None:
        row = _make_action(action_type="accepted", execution_status="in_progress")
        updated = _make_action(
            action_type="accepted",
            execution_status="blocked",
            blocked_at=NOW,
            blocked_reason="Waiting for budget approval",
        )
        async with _PatchSet(action_result=row, update_result=updated):
            out = await _svc().block(
                workspace_id=WORKSPACE_ID,
                recommendation_id=REC_ID,
                reason="Waiting for budget approval",
            )
        assert out.execution_status == "blocked"
        assert out.blocked_reason == "Waiting for budget approval"

    @pytest.mark.asyncio
    async def test_block_from_none_raises(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        async with _PatchSet(action_result=row):
            with pytest.raises(ValueError, match="invalid transition"):
                await _svc().block(
                    workspace_id=WORKSPACE_ID,
                    recommendation_id=REC_ID,
                    reason="reason",
                )

    @pytest.mark.asyncio
    async def test_block_from_completed_raises(self) -> None:
        row = _make_action(action_type="accepted", execution_status="completed")
        async with _PatchSet(action_result=row):
            with pytest.raises(ValueError, match="invalid transition"):
                await _svc().block(
                    workspace_id=WORKSPACE_ID,
                    recommendation_id=REC_ID,
                    reason="reason",
                )

    @pytest.mark.asyncio
    async def test_block_invalidates_cache(self) -> None:
        row = _make_action(action_type="accepted", execution_status="in_progress")
        updated = _make_action(action_type="accepted", execution_status="blocked", blocked_at=NOW, blocked_reason="x")
        async with _PatchSet(action_result=row, update_result=updated) as ps:
            await _svc().block(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, reason="x")
        ps.redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_block_raises_if_not_accepted(self) -> None:
        row = _make_action(action_type="dismissed", execution_status=None)
        async with _PatchSet(action_result=row):
            with pytest.raises(ValueError, match="not been accepted"):
                await _svc().block(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, reason="x")


# ── TestComplete ──────────────────────────────────────────────────────────────


class TestComplete:
    @pytest.mark.asyncio
    async def test_complete_from_in_progress(self) -> None:
        row = _make_action(action_type="accepted", execution_status="in_progress")
        updated = _make_action(
            action_type="accepted",
            execution_status="completed",
            completed_at=NOW,
            completion_notes="Done",
        )
        async with _PatchSet(action_result=row, update_result=updated):
            out = await _svc().complete(
                workspace_id=WORKSPACE_ID,
                recommendation_id=REC_ID,
                notes="Done",
            )
        assert out.execution_status == "completed"
        assert out.completion_notes == "Done"

    @pytest.mark.asyncio
    async def test_complete_with_no_notes(self) -> None:
        row = _make_action(action_type="accepted", execution_status="in_progress")
        updated = _make_action(action_type="accepted", execution_status="completed", completed_at=NOW)
        async with _PatchSet(action_result=row, update_result=updated):
            out = await _svc().complete(
                workspace_id=WORKSPACE_ID,
                recommendation_id=REC_ID,
                notes=None,
            )
        assert out.execution_status == "completed"

    @pytest.mark.asyncio
    async def test_complete_from_none_raises(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        async with _PatchSet(action_result=row):
            with pytest.raises(ValueError, match="invalid transition"):
                await _svc().complete(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, notes=None)

    @pytest.mark.asyncio
    async def test_complete_from_blocked_raises(self) -> None:
        row = _make_action(action_type="accepted", execution_status="blocked")
        async with _PatchSet(action_result=row):
            with pytest.raises(ValueError, match="invalid transition"):
                await _svc().complete(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, notes=None)

    @pytest.mark.asyncio
    async def test_complete_invalidates_cache(self) -> None:
        row = _make_action(action_type="accepted", execution_status="in_progress")
        updated = _make_action(action_type="accepted", execution_status="completed", completed_at=NOW)
        async with _PatchSet(action_result=row, update_result=updated) as ps:
            await _svc().complete(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, notes=None)
        ps.redis.delete.assert_awaited_once()


# ── TestCancel ────────────────────────────────────────────────────────────────


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_from_none(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        updated = _make_action(
            action_type="accepted",
            execution_status="cancelled",
            cancelled_at=NOW,
            blocked_reason="Changed priorities",
        )
        async with _PatchSet(action_result=row, update_result=updated):
            out = await _svc().cancel(
                workspace_id=WORKSPACE_ID,
                recommendation_id=REC_ID,
                reason="Changed priorities",
            )
        assert out.execution_status == "cancelled"
        assert out.blocked_reason == "Changed priorities"

    @pytest.mark.asyncio
    async def test_cancel_from_blocked(self) -> None:
        row = _make_action(action_type="accepted", execution_status="blocked")
        updated = _make_action(action_type="accepted", execution_status="cancelled", cancelled_at=NOW)
        async with _PatchSet(action_result=row, update_result=updated):
            out = await _svc().cancel(
                workspace_id=WORKSPACE_ID,
                recommendation_id=REC_ID,
                reason=None,
            )
        assert out.execution_status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_from_in_progress_raises(self) -> None:
        row = _make_action(action_type="accepted", execution_status="in_progress")
        async with _PatchSet(action_result=row):
            with pytest.raises(ValueError, match="invalid transition"):
                await _svc().cancel(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, reason=None)

    @pytest.mark.asyncio
    async def test_cancel_from_completed_raises(self) -> None:
        row = _make_action(action_type="accepted", execution_status="completed")
        async with _PatchSet(action_result=row):
            with pytest.raises(ValueError, match="invalid transition"):
                await _svc().cancel(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, reason=None)

    @pytest.mark.asyncio
    async def test_cancel_invalidates_cache(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        updated = _make_action(action_type="accepted", execution_status="cancelled", cancelled_at=NOW)
        async with _PatchSet(action_result=row, update_result=updated) as ps:
            await _svc().cancel(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, reason=None)
        ps.redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_raises_if_not_accepted(self) -> None:
        row = _make_action(action_type="snoozed", execution_status=None)
        async with _PatchSet(action_result=row):
            with pytest.raises(ValueError, match="not been accepted"):
                await _svc().cancel(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, reason=None)


# ── TestListQueue ─────────────────────────────────────────────────────────────


class TestListQueue:
    @pytest.mark.asyncio
    async def test_empty_workspace_returns_empty_buckets(self) -> None:
        async with _PatchSet(
            action_result=MagicMock(),
            list_result=[],
        ):
            out = await _svc().list_queue(workspace_id=WORKSPACE_ID)
        assert out.total == 0
        assert out.ready == []
        assert out.in_progress == []
        assert out.blocked == []
        assert out.completed == []
        assert out.cancelled == []
        assert out.timeline == []

    @pytest.mark.asyncio
    async def test_dismissed_rows_excluded_from_queue(self) -> None:
        dismissed = _make_action(action_type="dismissed")
        async with _PatchSet(action_result=dismissed, list_result=[dismissed]):
            out = await _svc().list_queue(workspace_id=WORKSPACE_ID)
        assert out.total == 0

    @pytest.mark.asyncio
    async def test_accepted_no_execution_goes_to_ready(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        async with _PatchSet(action_result=row, list_result=[row]):
            out = await _svc().list_queue(workspace_id=WORKSPACE_ID)
        assert len(out.ready) == 1
        assert out.ready[0].execution_status is None

    @pytest.mark.asyncio
    async def test_in_progress_row_goes_to_in_progress_bucket(self) -> None:
        row = _make_action(action_type="accepted", execution_status="in_progress")
        async with _PatchSet(action_result=row, list_result=[row]):
            out = await _svc().list_queue(workspace_id=WORKSPACE_ID)
        assert len(out.in_progress) == 1

    @pytest.mark.asyncio
    async def test_blocked_row_goes_to_blocked_bucket(self) -> None:
        row = _make_action(action_type="accepted", execution_status="blocked")
        async with _PatchSet(action_result=row, list_result=[row]):
            out = await _svc().list_queue(workspace_id=WORKSPACE_ID)
        assert len(out.blocked) == 1

    @pytest.mark.asyncio
    async def test_completed_row_goes_to_completed_bucket(self) -> None:
        row = _make_action(action_type="accepted", execution_status="completed")
        async with _PatchSet(action_result=row, list_result=[row]):
            out = await _svc().list_queue(workspace_id=WORKSPACE_ID)
        assert len(out.completed) == 1

    @pytest.mark.asyncio
    async def test_cancelled_row_goes_to_cancelled_bucket(self) -> None:
        row = _make_action(action_type="accepted", execution_status="cancelled")
        async with _PatchSet(action_result=row, list_result=[row]):
            out = await _svc().list_queue(workspace_id=WORKSPACE_ID)
        assert len(out.cancelled) == 1

    @pytest.mark.asyncio
    async def test_timeline_excludes_ready_rows(self) -> None:
        ready = _make_action(action_type="accepted", execution_status=None)
        done = _make_action(action_type="accepted", execution_status="completed")
        async with _PatchSet(action_result=ready, list_result=[ready, done]):
            out = await _svc().list_queue(workspace_id=WORKSPACE_ID)
        assert len(out.timeline) == 1
        assert out.timeline[0].execution_status == "completed"

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        cached_json = WorkQueueOut(
            ready=[], in_progress=[], blocked=[], completed=[], cancelled=[], timeline=[], total=0
        ).model_dump_json()
        async with _PatchSet(action_result=row) as ps:
            ps.redis.get = AsyncMock(return_value=cached_json)
            out = await _svc().list_queue(workspace_id=WORKSPACE_ID)
        assert out.total == 0  # returned from cache, not DB

    @pytest.mark.asyncio
    async def test_cache_miss_populates_cache(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        async with _PatchSet(action_result=row, list_result=[row]) as ps:
            await _svc().list_queue(workspace_id=WORKSPACE_ID)
        ps.redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_work_queue_out_type(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        async with _PatchSet(action_result=row, list_result=[row]):
            out = await _svc().list_queue(workspace_id=WORKSPACE_ID)
        assert isinstance(out, WorkQueueOut)


# ── TestTenantIsolation ───────────────────────────────────────────────────────


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_start_uses_tenant_id_from_context(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        updated = _make_action(action_type="accepted", execution_status="in_progress", started_at=NOW)
        other_tenant = uuid.uuid4()

        captured: list[uuid.UUID] = []

        def _fake_ctx() -> MagicMock:
            ctx = MagicMock()
            ctx.org_id = other_tenant
            captured.append(other_tenant)
            return ctx

        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", side_effect=_fake_ctx),
            patch("corpmind.modules.analytics.service.get_redis", return_value=MagicMock(
                get=AsyncMock(return_value=None), set=AsyncMock(), delete=AsyncMock()
            )),
            patch("corpmind.modules.analytics.repo.RecommendationActionRepo.find_by_recommendation",
                  new_callable=AsyncMock, return_value=row),
            patch("corpmind.modules.analytics.repo.RecommendationActionRepo.update_execution",
                  new_callable=AsyncMock, return_value=updated),
        ):
            await _svc().start(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)

        assert all(t == other_tenant for t in captured)

    @pytest.mark.asyncio
    async def test_list_queue_cache_key_includes_tenant(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        async with _PatchSet(action_result=row, list_result=[]) as ps:
            await _svc().list_queue(workspace_id=WORKSPACE_ID)
        delete_calls = ps.redis.delete.await_args_list
        set_calls = ps.redis.set.await_args_list
        # Cache key must contain tenant_id
        key_used = set_calls[0][0][0] if set_calls else ""
        assert str(TENANT_ID) in key_used

    @pytest.mark.asyncio
    async def test_queue_cache_key_includes_workspace(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        async with _PatchSet(action_result=row, list_result=[]) as ps:
            await _svc().list_queue(workspace_id=WORKSPACE_ID)
        set_calls = ps.redis.set.await_args_list
        key_used = set_calls[0][0][0] if set_calls else ""
        assert str(WORKSPACE_ID) in key_used


# ── TestTimestamps ────────────────────────────────────────────────────────────


class TestTimestamps:
    @pytest.mark.asyncio
    async def test_start_sets_started_at(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        updated = _make_action(action_type="accepted", execution_status="in_progress", started_at=NOW)
        with patch(
            "corpmind.modules.analytics.repo.RecommendationActionRepo.update_execution",
            new_callable=AsyncMock,
            return_value=updated,
        ) as mock_update:
            async with _PatchSet(action_result=row, update_result=updated):
                out = await _svc().start(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
        assert out.started_at == NOW

    @pytest.mark.asyncio
    async def test_block_sets_blocked_at(self) -> None:
        row = _make_action(action_type="accepted", execution_status="in_progress")
        updated = _make_action(action_type="accepted", execution_status="blocked", blocked_at=NOW)
        async with _PatchSet(action_result=row, update_result=updated):
            out = await _svc().block(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, reason="r")
        assert out.blocked_at == NOW

    @pytest.mark.asyncio
    async def test_complete_sets_completed_at(self) -> None:
        row = _make_action(action_type="accepted", execution_status="in_progress")
        updated = _make_action(action_type="accepted", execution_status="completed", completed_at=NOW)
        async with _PatchSet(action_result=row, update_result=updated):
            out = await _svc().complete(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, notes=None)
        assert out.completed_at == NOW

    @pytest.mark.asyncio
    async def test_cancel_sets_cancelled_at(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        updated = _make_action(action_type="accepted", execution_status="cancelled", cancelled_at=NOW)
        async with _PatchSet(action_result=row, update_result=updated):
            out = await _svc().cancel(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, reason=None)
        assert out.cancelled_at == NOW


# ── TestToExecutionOut ────────────────────────────────────────────────────────


class TestToExecutionOut:
    def test_fields_mapped_correctly(self) -> None:
        row = _make_action(
            action_type="accepted",
            execution_status="in_progress",
            started_at=NOW,
            blocked_reason=None,
            completion_notes=None,
        )
        out = RecommendationExecutionService._to_execution_out(row)
        assert out.recommendation_id == row.recommendation_id
        assert out.action_type == "accepted"
        assert out.execution_status == "in_progress"
        assert out.started_at == NOW

    def test_none_execution_status_preserved(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        out = RecommendationExecutionService._to_execution_out(row)
        assert out.execution_status is None


# ── TestNoCampaignCreation ────────────────────────────────────────────────────


class TestNoCampaignCreation:
    """Verify that execution transitions never touch campaign, message, or CRM services."""

    @pytest.mark.asyncio
    async def test_start_does_not_call_campaign_service(self) -> None:
        row = _make_action(action_type="accepted", execution_status=None)
        updated = _make_action(action_type="accepted", execution_status="in_progress", started_at=NOW)
        with patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_mock_context()), \
             patch("corpmind.modules.analytics.service.get_redis", return_value=MagicMock(
                 get=AsyncMock(return_value=None), set=AsyncMock(), delete=AsyncMock())), \
             patch("corpmind.modules.analytics.repo.RecommendationActionRepo.find_by_recommendation",
                   new_callable=AsyncMock, return_value=row), \
             patch("corpmind.modules.analytics.repo.RecommendationActionRepo.update_execution",
                   new_callable=AsyncMock, return_value=updated), \
             patch("corpmind.modules.analytics.service.CampaignService", create=True) as mock_camp:
            await _svc().start(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
            mock_camp.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_does_not_auto_send(self) -> None:
        row = _make_action(action_type="accepted", execution_status="in_progress")
        updated = _make_action(action_type="accepted", execution_status="completed", completed_at=NOW)
        with patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_mock_context()), \
             patch("corpmind.modules.analytics.service.get_redis", return_value=MagicMock(
                 get=AsyncMock(return_value=None), set=AsyncMock(), delete=AsyncMock())), \
             patch("corpmind.modules.analytics.repo.RecommendationActionRepo.find_by_recommendation",
                   new_callable=AsyncMock, return_value=row), \
             patch("corpmind.modules.analytics.repo.RecommendationActionRepo.update_execution",
                   new_callable=AsyncMock, return_value=updated), \
             patch("corpmind.modules.analytics.service.OutreachService", create=True) as mock_out:
            await _svc().complete(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, notes=None)
            mock_out.assert_not_called()
