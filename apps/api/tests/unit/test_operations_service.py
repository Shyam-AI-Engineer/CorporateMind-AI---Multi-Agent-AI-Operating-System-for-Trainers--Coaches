"""Unit tests for BusinessOperationsService — Sprint 29."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.operations.schemas import (
    BusinessTaskIn,
    BusinessTaskOut,
    BusinessTaskUpdate,
    GroupedTasksOut,
    WorkloadOut,
)
from corpmind.modules.operations.service import BusinessOperationsService

# ── Constants ──────────────────────────────────────────────────────────────────

ORG_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WS_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
TASK_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
TASK_ID2 = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
TASK_ID3 = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
TASK_ID4 = uuid.UUID("11111111-1111-1111-1111-111111111111")
TASK_ID5 = uuid.UUID("22222222-2222-2222-2222-222222222222")

NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=timezone.utc)
PAST_DATE = date(2026, 6, 20)   # overdue
FUTURE_DATE = date(2026, 7, 10)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _task(
    id: uuid.UUID = TASK_ID,
    status: str = "backlog",
    priority: str = "medium",
    assignee: str | None = None,
    due_date: date | None = None,
    completed_at: datetime | None = None,
    title: str = "Test task",
) -> MagicMock:
    """Create a lightweight BusinessTask-like mock with all required attributes."""
    t = MagicMock()
    t.id = id
    t.workspace_id = WS_ID
    t.tenant_id = ORG_ID
    t.status = status
    t.priority = priority
    t.assignee = assignee
    t.due_date = due_date
    t.completed_at = completed_at
    t.title = title
    t.description = None
    t.source_type = None
    t.source_id = None
    t.assigned_user_id = None
    t.created_by = str(USER_ID)
    t.created_at = NOW
    t.updated_at = NOW
    return t


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = ORG_ID
    ctx.workspace_id = WS_ID
    ctx.user_id = USER_ID
    return ctx


def _make_redis(cached_value: str | None = None) -> MagicMock:
    """Redis stub with async get/set/delete that mirrors aioredis interface."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached_value)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _svc() -> tuple[BusinessOperationsService, MagicMock]:
    """Create a service with a mock repo injected directly (bypasses DB session)."""
    session = MagicMock()
    svc = BusinessOperationsService(session=session)
    repo = MagicMock()
    svc._repo = repo       # direct injection — avoids needing a real AsyncSession
    return svc, repo


@contextmanager
def _patch(ctx: MagicMock, redis: MagicMock):
    """Patch both module-level dependencies for async service methods."""
    with patch("corpmind.modules.operations.service.get_tenant_context", return_value=ctx):
        with patch("corpmind.modules.operations.service.get_redis", return_value=redis):
            yield


# ── Cache key helpers ─────────────────────────────────────────────────────────

class TestCacheKeys:
    def test_tasks_key_contains_org_and_workspace(self) -> None:
        svc, _ = _svc()
        tasks_key, _ = svc._cache_keys(ORG_ID, WS_ID)
        assert str(ORG_ID) in tasks_key
        assert str(WS_ID) in tasks_key

    def test_tasks_key_contains_operations_namespace(self) -> None:
        svc, _ = _svc()
        tasks_key, _ = svc._cache_keys(ORG_ID, WS_ID)
        assert "operations" in tasks_key

    def test_workload_key_contains_workload(self) -> None:
        svc, _ = _svc()
        _, workload_key = svc._cache_keys(ORG_ID, WS_ID)
        assert "workload" in workload_key

    def test_tasks_and_workload_keys_are_distinct(self) -> None:
        svc, _ = _svc()
        tasks_key, workload_key = svc._cache_keys(ORG_ID, WS_ID)
        assert tasks_key != workload_key

    def test_different_orgs_produce_different_keys(self) -> None:
        svc, _ = _svc()
        org2 = uuid.UUID("99999999-9999-9999-9999-999999999999")
        k1, _ = svc._cache_keys(ORG_ID, WS_ID)
        k2, _ = svc._cache_keys(org2, WS_ID)
        assert k1 != k2

    def test_different_workspaces_produce_different_keys(self) -> None:
        svc, _ = _svc()
        ws2 = uuid.UUID("77777777-7777-7777-7777-777777777777")
        k1, _ = svc._cache_keys(ORG_ID, WS_ID)
        k2, _ = svc._cache_keys(ORG_ID, ws2)
        assert k1 != k2


# ── _group_tasks ──────────────────────────────────────────────────────────────

class TestGroupTasks:
    def test_empty_list_returns_empty_grouped(self) -> None:
        svc, _ = _svc()
        result = svc._group_tasks([])
        assert isinstance(result, GroupedTasksOut)
        assert result.total == 0
        assert result.backlog == []
        assert result.in_progress == []
        assert result.blocked == []
        assert result.completed == []

    def test_backlog_task_goes_to_backlog(self) -> None:
        svc, _ = _svc()
        result = svc._group_tasks([_task(status="backlog")])
        assert len(result.backlog) == 1

    def test_in_progress_task_goes_to_in_progress(self) -> None:
        svc, _ = _svc()
        result = svc._group_tasks([_task(status="in_progress")])
        assert len(result.in_progress) == 1

    def test_blocked_task_goes_to_blocked(self) -> None:
        svc, _ = _svc()
        result = svc._group_tasks([_task(status="blocked")])
        assert len(result.blocked) == 1

    def test_completed_task_goes_to_completed(self) -> None:
        svc, _ = _svc()
        result = svc._group_tasks([_task(status="completed")])
        assert len(result.completed) == 1

    def test_deleted_task_excluded_from_all_groups(self) -> None:
        svc, _ = _svc()
        result = svc._group_tasks([_task(status="deleted")])
        assert result.total == 0
        assert result.backlog == []
        assert result.in_progress == []
        assert result.blocked == []
        assert result.completed == []

    def test_mixed_statuses_distributed_correctly(self) -> None:
        svc, _ = _svc()
        tasks = [
            _task(TASK_ID, "backlog"),
            _task(TASK_ID2, "in_progress"),
            _task(TASK_ID3, "blocked"),
            _task(TASK_ID4, "completed"),
        ]
        result = svc._group_tasks(tasks)
        assert len(result.backlog) == 1
        assert len(result.in_progress) == 1
        assert len(result.blocked) == 1
        assert len(result.completed) == 1

    def test_total_counts_all_non_deleted(self) -> None:
        svc, _ = _svc()
        tasks = [
            _task(TASK_ID, "backlog"),
            _task(TASK_ID2, "in_progress"),
            _task(TASK_ID3, "deleted"),
        ]
        result = svc._group_tasks(tasks)
        assert result.total == 2

    def test_multiple_tasks_in_same_bucket(self) -> None:
        svc, _ = _svc()
        tasks = [_task(TASK_ID, "backlog"), _task(TASK_ID2, "backlog")]
        result = svc._group_tasks(tasks)
        assert len(result.backlog) == 2
        assert result.total == 2

    def test_returns_business_task_out_instances(self) -> None:
        svc, _ = _svc()
        result = svc._group_tasks([_task(status="backlog")])
        assert isinstance(result.backlog[0], BusinessTaskOut)


# ── _compute_workload ─────────────────────────────────────────────────────────

class TestComputeWorkload:
    def test_empty_list_returns_zeros(self) -> None:
        svc, _ = _svc()
        result = svc._compute_workload([], 0)
        assert isinstance(result, WorkloadOut)
        assert result.total_open == 0
        assert result.overdue == 0
        assert result.completed_today == 0
        assert result.blocked == 0

    def test_total_open_counts_backlog_in_progress_blocked(self) -> None:
        svc, _ = _svc()
        tasks = [
            _task(TASK_ID, "backlog"),
            _task(TASK_ID2, "in_progress"),
            _task(TASK_ID3, "blocked"),
            _task(TASK_ID4, "completed"),
        ]
        result = svc._compute_workload(tasks, 1)
        assert result.total_open == 3

    def test_blocked_count_matches_blocked_status(self) -> None:
        svc, _ = _svc()
        tasks = [
            _task(TASK_ID, "blocked"),
            _task(TASK_ID2, "blocked"),
            _task(TASK_ID3, "backlog"),
        ]
        result = svc._compute_workload(tasks, 0)
        assert result.blocked == 2

    def test_completed_today_uses_repo_value(self) -> None:
        svc, _ = _svc()
        result = svc._compute_workload([], 5)
        assert result.completed_today == 5

    def test_overdue_counts_open_tasks_with_past_due_date(self) -> None:
        svc, _ = _svc()
        tasks = [
            _task(TASK_ID, "backlog", due_date=PAST_DATE),
            _task(TASK_ID2, "in_progress", due_date=PAST_DATE),
            _task(TASK_ID3, "completed", due_date=PAST_DATE),   # completed — not overdue
            _task(TASK_ID4, "backlog", due_date=FUTURE_DATE),   # future — not overdue
        ]
        result = svc._compute_workload(tasks, 0)
        assert result.overdue == 2

    def test_no_due_date_not_counted_as_overdue(self) -> None:
        svc, _ = _svc()
        t = _task(TASK_ID, "backlog", due_date=None)
        result = svc._compute_workload([t], 0)
        assert result.overdue == 0

    def test_by_priority_counts_open_tasks_only(self) -> None:
        svc, _ = _svc()
        tasks = [
            _task(TASK_ID, "backlog", priority="high"),
            _task(TASK_ID2, "in_progress", priority="high"),
            _task(TASK_ID3, "backlog", priority="medium"),
            _task(TASK_ID4, "completed", priority="high"),  # completed excluded
        ]
        result = svc._compute_workload(tasks, 0)
        assert result.by_priority.get("high", 0) == 2
        assert result.by_priority.get("medium", 0) == 1

    def test_by_assignee_counts_open_tasks_only(self) -> None:
        svc, _ = _svc()
        tasks = [
            _task(TASK_ID, "backlog", assignee="alice"),
            _task(TASK_ID2, "in_progress", assignee="alice"),
            _task(TASK_ID3, "completed", assignee="alice"),  # completed excluded
            _task(TASK_ID4, "backlog", assignee="bob"),
        ]
        result = svc._compute_workload(tasks, 0)
        assert result.by_assignee.get("alice", 0) == 2
        assert result.by_assignee.get("bob", 0) == 1

    def test_unassigned_tasks_excluded_from_by_assignee(self) -> None:
        svc, _ = _svc()
        t = _task(TASK_ID, "backlog", assignee=None)
        result = svc._compute_workload([t], 0)
        assert None not in result.by_assignee
        assert len(result.by_assignee) == 0

    def test_deleted_tasks_excluded_from_workload(self) -> None:
        svc, _ = _svc()
        t = _task(TASK_ID, "deleted")
        result = svc._compute_workload([t], 0)
        assert result.total_open == 0


# ── list_tasks ─────────────────────────────────────────────────────────────────

class TestListTasks:
    @pytest.mark.asyncio
    async def test_returns_grouped_tasks_out(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        repo.list_active = AsyncMock(return_value=[_task()])
        with _patch(ctx, redis):
            result = await svc.list_tasks(WS_ID)
        assert isinstance(result, GroupedTasksOut)

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_without_repo(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        cached = GroupedTasksOut(backlog=[], in_progress=[], blocked=[], completed=[], total=0)
        redis = _make_redis(cached_value=cached.model_dump_json())
        with _patch(ctx, redis):
            result = await svc.list_tasks(WS_ID)
        repo.list_active.assert_not_called()
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_cache_miss_calls_repo_list_active(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        repo.list_active = AsyncMock(return_value=[])
        with _patch(ctx, redis):
            await svc.list_tasks(WS_ID)
        repo.list_active.assert_called_once_with(WS_ID)

    @pytest.mark.asyncio
    async def test_result_written_to_cache_on_miss(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        repo.list_active = AsyncMock(return_value=[])
        with _patch(ctx, redis):
            await svc.list_tasks(WS_ID)
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_written_with_correct_ttl(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        repo.list_active = AsyncMock(return_value=[])
        with _patch(ctx, redis):
            await svc.list_tasks(WS_ID)
        _, kwargs = redis.set.call_args
        assert kwargs.get("ex") == 300  # 5 minute TTL


# ── create_task ────────────────────────────────────────────────────────────────

class TestCreateTask:
    @pytest.mark.asyncio
    async def test_returns_business_task_out(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()

        async def create_with_ts(task):
            task.created_at = NOW
            task.updated_at = NOW
            return task

        repo.create = create_with_ts
        data = BusinessTaskIn(workspace_id=WS_ID, title="My task")
        with _patch(ctx, redis):
            result = await svc.create_task(data, str(USER_ID))
        assert isinstance(result, BusinessTaskOut)

    @pytest.mark.asyncio
    async def test_cache_invalidated_after_create(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()

        async def create_with_ts(task):
            task.created_at = NOW
            task.updated_at = NOW
            return task

        repo.create = create_with_ts
        data = BusinessTaskIn(workspace_id=WS_ID, title="My task")
        with _patch(ctx, redis):
            await svc.create_task(data, str(USER_ID))
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_task_title_stored_correctly(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        created_tasks: list = []

        async def capture_create(task):
            created_tasks.append(task)
            task.created_at = NOW
            task.updated_at = NOW
            return task

        repo.create = capture_create
        data = BusinessTaskIn(workspace_id=WS_ID, title="Specific Title")
        with _patch(ctx, redis):
            await svc.create_task(data, str(USER_ID))
        assert created_tasks[0].title == "Specific Title"

    @pytest.mark.asyncio
    async def test_default_status_is_backlog(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        created_tasks: list = []

        async def capture_create(task):
            created_tasks.append(task)
            task.created_at = NOW
            task.updated_at = NOW
            return task

        repo.create = capture_create
        data = BusinessTaskIn(workspace_id=WS_ID, title="Task")
        with _patch(ctx, redis):
            await svc.create_task(data, str(USER_ID))
        assert created_tasks[0].status == "backlog"

    @pytest.mark.asyncio
    async def test_default_priority_is_medium(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        created_tasks: list = []

        async def capture_create(task):
            created_tasks.append(task)
            task.created_at = NOW
            task.updated_at = NOW
            return task

        repo.create = capture_create
        data = BusinessTaskIn(workspace_id=WS_ID, title="Task")
        with _patch(ctx, redis):
            await svc.create_task(data, str(USER_ID))
        assert created_tasks[0].priority == "medium"

    @pytest.mark.asyncio
    async def test_created_by_stored_from_argument(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        created_tasks: list = []

        async def capture_create(task):
            created_tasks.append(task)
            task.created_at = NOW
            task.updated_at = NOW
            return task

        repo.create = capture_create
        data = BusinessTaskIn(workspace_id=WS_ID, title="Task")
        with _patch(ctx, redis):
            await svc.create_task(data, "creator-xyz")
        assert created_tasks[0].created_by == "creator-xyz"

    @pytest.mark.asyncio
    async def test_high_priority_task_stored(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        created_tasks: list = []

        async def capture_create(task):
            created_tasks.append(task)
            task.created_at = NOW
            task.updated_at = NOW
            return task

        repo.create = capture_create
        data = BusinessTaskIn(workspace_id=WS_ID, title="Urgent", priority="high")
        with _patch(ctx, redis):
            await svc.create_task(data, str(USER_ID))
        assert created_tasks[0].priority == "high"


# ── update_task ────────────────────────────────────────────────────────────────

class TestUpdateTask:
    @pytest.mark.asyncio
    async def test_returns_updated_task_out(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="in_progress")
        repo.find_by_id = AsyncMock(return_value=t)
        repo.update_fields = AsyncMock()
        data = BusinessTaskUpdate(status="in_progress")
        with _patch(ctx, redis):
            result = await svc.update_task(TASK_ID, WS_ID, data)
        assert isinstance(result, BusinessTaskOut)

    @pytest.mark.asyncio
    async def test_not_found_raises_not_found_error(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        repo.find_by_id = AsyncMock(return_value=None)
        data = BusinessTaskUpdate(status="completed")
        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update_task(TASK_ID, WS_ID, data)

    @pytest.mark.asyncio
    async def test_completing_sets_completed_at(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="in_progress")
        updates: dict = {}

        async def capture_update(task_id, **values):
            updates.update(values)

        repo.find_by_id = AsyncMock(return_value=t)
        repo.update_fields = capture_update
        data = BusinessTaskUpdate(status="completed")
        with _patch(ctx, redis):
            await svc.update_task(TASK_ID, WS_ID, data)
        assert "completed_at" in updates
        assert updates["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_non_complete_status_does_not_set_completed_at(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="backlog")
        updates: dict = {}

        async def capture_update(task_id, **values):
            updates.update(values)

        repo.find_by_id = AsyncMock(return_value=t)
        repo.update_fields = capture_update
        data = BusinessTaskUpdate(status="in_progress")
        with _patch(ctx, redis):
            await svc.update_task(TASK_ID, WS_ID, data)
        assert "completed_at" not in updates

    @pytest.mark.asyncio
    async def test_workspace_mismatch_raises_not_found(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="backlog")
        t.workspace_id = uuid.UUID("88888888-8888-8888-8888-888888888888")  # different ws
        repo.find_by_id = AsyncMock(return_value=t)
        data = BusinessTaskUpdate(status="completed")
        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update_task(TASK_ID, WS_ID, data)

    @pytest.mark.asyncio
    async def test_deleted_task_raises_not_found(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="deleted")
        repo.find_by_id = AsyncMock(return_value=t)
        data = BusinessTaskUpdate(status="completed")
        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update_task(TASK_ID, WS_ID, data)

    @pytest.mark.asyncio
    async def test_cache_invalidated_after_update(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="backlog")
        repo.find_by_id = AsyncMock(return_value=t)
        repo.update_fields = AsyncMock()
        data = BusinessTaskUpdate(status="in_progress")
        with _patch(ctx, redis):
            await svc.update_task(TASK_ID, WS_ID, data)
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_none_fields_not_passed_to_update_fields(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="backlog", assignee="alice")
        updates: dict = {}

        async def capture_update(task_id, **values):
            updates.update(values)

        repo.find_by_id = AsyncMock(return_value=t)
        repo.update_fields = capture_update
        # only status provided; assignee=None means "don't change"
        data = BusinessTaskUpdate(status="in_progress")
        with _patch(ctx, redis):
            await svc.update_task(TASK_ID, WS_ID, data)
        assert "assignee" not in updates

    @pytest.mark.asyncio
    async def test_assignee_update_passed_when_provided(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="backlog")
        updates: dict = {}

        async def capture_update(task_id, **values):
            updates.update(values)

        repo.find_by_id = AsyncMock(return_value=t)
        repo.update_fields = capture_update
        data = BusinessTaskUpdate(assignee="bob")
        with _patch(ctx, redis):
            await svc.update_task(TASK_ID, WS_ID, data)
        assert updates.get("assignee") == "bob"


# ── delete_task ────────────────────────────────────────────────────────────────

class TestDeleteTask:
    @pytest.mark.asyncio
    async def test_soft_deletes_sets_status_deleted(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="backlog")
        updates: dict = {}

        async def capture_update(task_id, **values):
            updates.update(values)

        repo.find_by_id = AsyncMock(return_value=t)
        repo.update_fields = capture_update
        with _patch(ctx, redis):
            await svc.delete_task(TASK_ID, WS_ID)
        assert updates.get("status") == "deleted"

    @pytest.mark.asyncio
    async def test_not_found_raises_not_found_error(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        repo.find_by_id = AsyncMock(return_value=None)
        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.delete_task(TASK_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_already_deleted_raises_not_found(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="deleted")
        repo.find_by_id = AsyncMock(return_value=t)
        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.delete_task(TASK_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_cache_invalidated_after_delete(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="backlog")
        repo.find_by_id = AsyncMock(return_value=t)
        repo.update_fields = AsyncMock()
        with _patch(ctx, redis):
            await svc.delete_task(TASK_ID, WS_ID)
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_workspace_mismatch_raises_not_found(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="backlog")
        t.workspace_id = uuid.UUID("88888888-8888-8888-8888-888888888888")
        repo.find_by_id = AsyncMock(return_value=t)
        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.delete_task(TASK_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_updated_at_set_on_soft_delete(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        t = _task(status="in_progress")
        updates: dict = {}

        async def capture_update(task_id, **values):
            updates.update(values)

        repo.find_by_id = AsyncMock(return_value=t)
        repo.update_fields = capture_update
        with _patch(ctx, redis):
            await svc.delete_task(TASK_ID, WS_ID)
        assert "updated_at" in updates


# ── get_workload ───────────────────────────────────────────────────────────────

class TestGetWorkload:
    @pytest.mark.asyncio
    async def test_returns_workload_out(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        repo.list_active = AsyncMock(return_value=[])
        repo.count_completed_today = AsyncMock(return_value=0)
        with _patch(ctx, redis):
            result = await svc.get_workload(WS_ID)
        assert isinstance(result, WorkloadOut)

    @pytest.mark.asyncio
    async def test_cache_hit_skips_repo(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        cached = WorkloadOut(
            total_open=3, overdue=1, completed_today=2, blocked=0,
            by_priority={}, by_assignee={}
        )
        redis = _make_redis(cached_value=cached.model_dump_json())
        with _patch(ctx, redis):
            result = await svc.get_workload(WS_ID)
        repo.list_active.assert_not_called()
        assert result.total_open == 3

    @pytest.mark.asyncio
    async def test_cache_miss_calls_list_active(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        repo.list_active = AsyncMock(return_value=[])
        repo.count_completed_today = AsyncMock(return_value=0)
        with _patch(ctx, redis):
            await svc.get_workload(WS_ID)
        repo.list_active.assert_called_once_with(WS_ID)

    @pytest.mark.asyncio
    async def test_completed_today_from_count_completed_today(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        repo.list_active = AsyncMock(return_value=[])
        repo.count_completed_today = AsyncMock(return_value=7)
        with _patch(ctx, redis):
            result = await svc.get_workload(WS_ID)
        assert result.completed_today == 7

    @pytest.mark.asyncio
    async def test_result_written_to_cache(self) -> None:
        svc, repo = _svc()
        ctx = _make_ctx()
        redis = _make_redis()
        repo.list_active = AsyncMock(return_value=[])
        repo.count_completed_today = AsyncMock(return_value=0)
        with _patch(ctx, redis):
            await svc.get_workload(WS_ID)
        redis.set.assert_called_once()


# ── _invalidate ───────────────────────────────────────────────────────────────

class TestInvalidate:
    @pytest.mark.asyncio
    async def test_deletes_both_cache_keys(self) -> None:
        svc, _ = _svc()
        redis = _make_redis()
        with patch("corpmind.modules.operations.service.get_redis", return_value=redis):
            await svc._invalidate(ORG_ID, WS_ID)
        redis.delete.assert_called_once()
        args = redis.delete.call_args[0]
        assert len(args) == 2

    @pytest.mark.asyncio
    async def test_tasks_key_in_deleted_args(self) -> None:
        svc, _ = _svc()
        redis = _make_redis()
        with patch("corpmind.modules.operations.service.get_redis", return_value=redis):
            await svc._invalidate(ORG_ID, WS_ID)
        tasks_key, _ = svc._cache_keys(ORG_ID, WS_ID)
        args = redis.delete.call_args[0]
        assert tasks_key in args

    @pytest.mark.asyncio
    async def test_workload_key_in_deleted_args(self) -> None:
        svc, _ = _svc()
        redis = _make_redis()
        with patch("corpmind.modules.operations.service.get_redis", return_value=redis):
            await svc._invalidate(ORG_ID, WS_ID)
        _, workload_key = svc._cache_keys(ORG_ID, WS_ID)
        args = redis.delete.call_args[0]
        assert workload_key in args

    @pytest.mark.asyncio
    async def test_redis_error_silently_swallowed(self) -> None:
        svc, _ = _svc()
        redis = MagicMock()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))
        with patch("corpmind.modules.operations.service.get_redis", return_value=redis):
            # should not raise
            await svc._invalidate(ORG_ID, WS_ID)


# ── Schema validation ─────────────────────────────────────────────────────────

class TestSchemas:
    def test_task_in_requires_workspace_id(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            BusinessTaskIn(title="No workspace")  # type: ignore[call-arg]

    def test_task_in_requires_title(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            BusinessTaskIn(workspace_id=str(WS_ID))  # type: ignore[call-arg]

    def test_task_in_title_cannot_be_blank(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            BusinessTaskIn(workspace_id=WS_ID, title="   ")

    def test_task_in_defaults_priority_to_medium(self) -> None:
        t = BusinessTaskIn(workspace_id=WS_ID, title="Test")
        assert t.priority == "medium"

    def test_task_in_invalid_priority_raises(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            BusinessTaskIn(workspace_id=WS_ID, title="T", priority="urgent")  # type: ignore[arg-type]

    def test_task_in_invalid_source_type_raises(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            BusinessTaskIn(workspace_id=WS_ID, title="T", source_type="ftp")  # type: ignore[arg-type]

    def test_task_update_all_optional_defaults_none(self) -> None:
        t = BusinessTaskUpdate()
        assert t.status is None
        assert t.assignee is None
        assert t.due_date is None

    def test_task_update_valid_status_accepted(self) -> None:
        t = BusinessTaskUpdate(status="completed")
        assert t.status == "completed"

    def test_task_update_invalid_status_raises(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            BusinessTaskUpdate(status="done")  # type: ignore[arg-type]

    def test_grouped_tasks_total_field(self) -> None:
        g = GroupedTasksOut(backlog=[], in_progress=[], blocked=[], completed=[], total=5)
        assert g.total == 5

    def test_workload_by_priority_map(self) -> None:
        w = WorkloadOut(
            total_open=4, overdue=1, completed_today=2, blocked=0,
            by_priority={"high": 2}, by_assignee={"alice": 3}
        )
        assert w.by_priority["high"] == 2
        assert w.by_assignee["alice"] == 3

    def test_business_task_out_from_attributes(self) -> None:
        t = _task()
        out = BusinessTaskOut.model_validate(t)
        assert out.title == "Test task"
        assert out.status == "backlog"
        assert out.priority == "medium"

    def test_valid_source_types_all_accepted(self) -> None:
        for st in ["manual", "crm", "campaign", "proposal", "recommendation"]:
            t = BusinessTaskIn(workspace_id=WS_ID, title="T", source_type=st)  # type: ignore[arg-type]
            assert t.source_type == st

    def test_valid_update_statuses_all_accepted(self) -> None:
        for s in ["backlog", "in_progress", "blocked", "completed"]:
            t = BusinessTaskUpdate(status=s)  # type: ignore[arg-type]
            assert t.status == s

    def test_valid_priorities_all_accepted(self) -> None:
        for p in ["high", "medium", "low"]:
            t = BusinessTaskIn(workspace_id=WS_ID, title="T", priority=p)  # type: ignore[arg-type]
            assert t.priority == p
