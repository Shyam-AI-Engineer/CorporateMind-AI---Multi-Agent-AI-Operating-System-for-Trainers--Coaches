"""Unit tests for WorkflowExecutionService — Sprint 34.

108 tests across 15 classes.
All DB and Redis interactions are mocked; only pure service logic is exercised.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.workflows.schemas import (
    BlockStepIn,
    CompleteStepIn,
    SkipStepIn,
    WorkflowRunIn,
    WorkflowRunListPage,
    WorkflowRunOut,
    WorkflowRunStepOut,
)
from corpmind.modules.workflows.service import (
    PermissionDeniedError,
    SkipRequiredStepError,
    StepStateError,
    WorkflowExecutionService,
    WorkflowRunImmutableError,
    _run_detail_key as svc_run_detail_key,
    _run_list_key as svc_run_list_key,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

ORG_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WS_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
TMPL_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
RUN_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
STEP_ID = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
STEP2_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ASSIGNED_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

NOW = datetime(2026, 6, 29, 10, 0, 0, tzinfo=UTC)


def _make_ctx(role: str = "owner") -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = ORG_ID
    ctx.user_id = USER_ID
    ctx.role = role
    return ctx


def _make_redis(cached: Any = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _make_svc() -> WorkflowExecutionService:
    svc = WorkflowExecutionService(MagicMock())
    # Pre-configure ALL async methods so no test fails due to un-awaitable MagicMock
    svc._run_repo = MagicMock()
    svc._run_repo.find_by_id = AsyncMock(return_value=None)
    svc._run_repo.create = AsyncMock(return_value=MagicMock())
    svc._run_repo.update_fields = AsyncMock()
    svc._run_repo.list_page = AsyncMock(return_value=([], None))

    svc._run_step_repo = MagicMock()
    svc._run_step_repo.find_by_id = AsyncMock(return_value=None)
    svc._run_step_repo.create = AsyncMock(return_value=MagicMock())
    svc._run_step_repo.update_fields = AsyncMock()
    svc._run_step_repo.find_by_run = AsyncMock(return_value=[])

    svc._template_repo = MagicMock()
    svc._template_repo.find_by_id = AsyncMock(return_value=None)

    svc._step_repo = MagicMock()
    svc._step_repo.find_by_template = AsyncMock(return_value=[])

    svc._notify = AsyncMock()
    return svc


def _make_run(
    status: str = "active",
    assigned_to: uuid.UUID | None = None,
) -> MagicMock:
    run = MagicMock()
    run.id = RUN_ID
    run.tenant_id = ORG_ID
    run.workspace_id = WS_ID
    run.workflow_template_id = TMPL_ID
    run.title = "Test Run"
    run.status = status
    run.started_by = USER_ID
    run.assigned_to = assigned_to
    run.started_at = NOW
    run.completed_at = None
    run.cancelled_at = None
    run.run_steps = []
    return run


def _make_run_step(
    status: str = "pending",
    required: bool = True,
    step_order: int = 1,
    step_id: uuid.UUID | None = None,
) -> MagicMock:
    step = MagicMock()
    step.id = step_id or STEP_ID
    step.tenant_id = ORG_ID
    step.workspace_id = WS_ID
    step.workflow_run_id = RUN_ID
    step.template_step_id = uuid.uuid4()
    step.title = "Test Step"
    step.description = None
    step.owner_role = "member"
    step.required = required
    step.step_order = step_order
    step.status = status
    step.completed_by = None
    step.completed_at = None
    step.notes = None
    return step


def _make_template_step(step_order: int = 1, required: bool = True) -> MagicMock:
    s = MagicMock()
    s.id = uuid.uuid4()
    s.title = f"Template Step {step_order}"
    s.description = "desc"
    s.owner_role = "member"
    s.estimated_hours = Decimal("1.0")
    s.required = required
    s.step_order = step_order
    return s


@contextmanager
def _patch(ctx: MagicMock, redis: MagicMock):
    with (
        patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=redis,
        ),
    ):
        yield


# ── TestCacheKeys ─────────────────────────────────────────────────────────────


class TestCacheKeys:
    def test_run_list_key_format(self) -> None:
        key = svc_run_list_key(ORG_ID, WS_ID)
        assert key == f"t:{ORG_ID}:{WS_ID}:workflow_runs:list"

    def test_run_detail_key_format(self) -> None:
        key = svc_run_detail_key(ORG_ID, RUN_ID)
        assert key == f"t:{ORG_ID}:workflow_runs:detail:{RUN_ID}"


# ── TestSchemaValidation ──────────────────────────────────────────────────────


class TestSchemaValidation:
    def test_run_in_valid(self) -> None:
        data = WorkflowRunIn(
            workspace_id=WS_ID,
            workflow_template_id=TMPL_ID,
            title="My Run",
        )
        assert data.title == "My Run"

    def test_run_in_empty_title_raises(self) -> None:
        with pytest.raises(Exception):
            WorkflowRunIn(
                workspace_id=WS_ID,
                workflow_template_id=TMPL_ID,
                title="   ",
            )

    def test_run_in_long_title_raises(self) -> None:
        with pytest.raises(Exception):
            WorkflowRunIn(
                workspace_id=WS_ID,
                workflow_template_id=TMPL_ID,
                title="x" * 256,
            )

    def test_run_in_strips_title(self) -> None:
        data = WorkflowRunIn(
            workspace_id=WS_ID,
            workflow_template_id=TMPL_ID,
            title="  My Run  ",
        )
        assert data.title == "My Run"

    def test_run_in_assigned_to_optional(self) -> None:
        data = WorkflowRunIn(
            workspace_id=WS_ID,
            workflow_template_id=TMPL_ID,
            title="Run",
        )
        assert data.assigned_to is None

    def test_complete_step_in_valid(self) -> None:
        data = CompleteStepIn(notes="Done!")
        assert data.notes == "Done!"

    def test_complete_step_in_null_notes(self) -> None:
        data = CompleteStepIn()
        assert data.notes is None

    def test_block_step_in_valid(self) -> None:
        data = BlockStepIn(notes="Waiting on finance")
        assert data.notes == "Waiting on finance"

    def test_skip_step_in_valid(self) -> None:
        data = SkipStepIn(notes="Not applicable")
        assert data.notes == "Not applicable"

    def test_workflow_run_out_from_attributes(self) -> None:
        run = _make_run()
        out = WorkflowRunOut.model_validate(run)
        assert out.id == RUN_ID
        assert out.status == "active"
        assert out.run_steps == []


# ── TestPermissions ───────────────────────────────────────────────────────────


class TestPermissions:
    @pytest.mark.asyncio
    async def test_owner_can_start(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        run = _make_run()
        svc._run_repo.create = AsyncMock(return_value=run)
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            result = await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        assert isinstance(result, WorkflowRunOut)

    @pytest.mark.asyncio
    async def test_admin_can_start(self) -> None:
        ctx = _make_ctx("admin")
        redis = _make_redis()
        svc = _make_svc()
        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        run = _make_run()
        svc._run_repo.create = AsyncMock(return_value=run)
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            result = await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        assert isinstance(result, WorkflowRunOut)

    @pytest.mark.asyncio
    async def test_member_cannot_start(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.start_run(
                    WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
                )

    @pytest.mark.asyncio
    async def test_viewer_cannot_start(self) -> None:
        ctx = _make_ctx("viewer")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.start_run(
                    WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
                )

    @pytest.mark.asyncio
    async def test_member_can_complete_step(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run())
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step])
        with _patch(ctx, redis):
            result = await svc.complete_step(STEP_ID, CompleteStepIn())
        assert isinstance(result, WorkflowRunStepOut)

    @pytest.mark.asyncio
    async def test_viewer_cannot_complete_step(self) -> None:
        ctx = _make_ctx("viewer")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.complete_step(STEP_ID, CompleteStepIn())

    @pytest.mark.asyncio
    async def test_owner_can_cancel(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.cancel_run(RUN_ID)
        assert isinstance(result, WorkflowRunOut)

    @pytest.mark.asyncio
    async def test_member_cannot_cancel(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.cancel_run(RUN_ID)


# ── TestStartRun ──────────────────────────────────────────────────────────────


class TestStartRun:
    @pytest.mark.asyncio
    async def test_start_run_creates_run(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        run = _make_run()
        svc._run_repo.create = AsyncMock(return_value=run)
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            result = await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        assert isinstance(result, WorkflowRunOut)
        svc._run_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_run_creates_steps_from_template(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        s1 = _make_template_step(1)
        s2 = _make_template_step(2)
        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        svc._step_repo.find_by_template = AsyncMock(return_value=[s1, s2])
        run = _make_run()
        svc._run_repo.create = AsyncMock(return_value=run)
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        assert svc._run_step_repo.create.await_count == 2

    @pytest.mark.asyncio
    async def test_start_run_copies_step_fields(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        src = _make_template_step(1)
        src.title = "Review Contract"
        src.required = False
        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        svc._step_repo.find_by_template = AsyncMock(return_value=[src])
        captured: list = []

        async def capture_create(step):
            captured.append(step)
            return step

        svc._run_step_repo.create = capture_create
        run = _make_run()
        svc._run_repo.create = AsyncMock(return_value=run)
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        assert captured[0].title == "Review Contract"
        assert captured[0].required is False

    @pytest.mark.asyncio
    async def test_start_run_status_is_active(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        created_runs: list = []

        async def capture(run):
            created_runs.append(run)
            return run

        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        svc._run_repo.create = capture
        run = _make_run()
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        assert created_runs[0].status == "active"

    @pytest.mark.asyncio
    async def test_start_run_template_not_found(self) -> None:
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.start_run(
                    WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
                )

    @pytest.mark.asyncio
    async def test_start_run_invalidates_cache(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        run = _make_run()
        svc._run_repo.create = AsyncMock(return_value=run)
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_start_run_sets_started_by(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        captured: list = []

        async def capture(run):
            captured.append(run)
            return run

        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        svc._run_repo.create = capture
        run = _make_run()
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        assert captured[0].started_by == USER_ID

    @pytest.mark.asyncio
    async def test_start_run_assigned_to(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        captured: list = []

        async def capture(run):
            captured.append(run)
            return run

        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        svc._run_repo.create = capture
        run = _make_run()
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            await svc.start_run(
                WorkflowRunIn(
                    workspace_id=WS_ID,
                    workflow_template_id=TMPL_ID,
                    title="Run",
                    assigned_to=ASSIGNED_ID,
                )
            )
        assert captured[0].assigned_to == ASSIGNED_ID

    @pytest.mark.asyncio
    async def test_start_run_no_steps(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        run = _make_run()
        svc._run_repo.create = AsyncMock(return_value=run)
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            result = await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        assert isinstance(result, WorkflowRunOut)
        svc._run_step_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_start_run_preserves_step_order(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        s1 = _make_template_step(1)
        s2 = _make_template_step(2)
        s3 = _make_template_step(3)
        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        svc._step_repo.find_by_template = AsyncMock(return_value=[s1, s2, s3])
        captured: list = []

        async def capture(step):
            captured.append(step)
            return step

        svc._run_step_repo.create = capture
        run = _make_run()
        svc._run_repo.create = AsyncMock(return_value=run)
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        orders = [s.step_order for s in captured]
        assert orders == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_start_run_required_field_copied(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        s1 = _make_template_step(1, required=True)
        s2 = _make_template_step(2, required=False)
        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        svc._step_repo.find_by_template = AsyncMock(return_value=[s1, s2])
        captured: list = []

        async def capture(step):
            captured.append(step)
            return step

        svc._run_step_repo.create = capture
        run = _make_run()
        svc._run_repo.create = AsyncMock(return_value=run)
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        assert captured[0].required is True
        assert captured[1].required is False

    @pytest.mark.asyncio
    async def test_start_run_assigns_tenant_id(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        captured: list = []

        async def capture(run):
            captured.append(run)
            return run

        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        svc._run_repo.create = capture
        run = _make_run()
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        assert captured[0].tenant_id == ORG_ID


# ── TestCancelRun ─────────────────────────────────────────────────────────────


class TestCancelRun:
    @pytest.mark.asyncio
    async def test_cancel_active_run(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.cancel_run(RUN_ID)
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_run_not_found(self) -> None:
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.cancel_run(RUN_ID)

    @pytest.mark.asyncio
    async def test_cancel_completed_run_raises(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("completed"))
        with _patch(ctx, redis):
            with pytest.raises(WorkflowRunImmutableError):
                await svc.cancel_run(RUN_ID)

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_run_raises(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("cancelled"))
        with _patch(ctx, redis):
            with pytest.raises(WorkflowRunImmutableError):
                await svc.cancel_run(RUN_ID)

    @pytest.mark.asyncio
    async def test_cancel_sets_cancelled_at(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.cancel_run(RUN_ID)
        assert result.cancelled_at is not None

    @pytest.mark.asyncio
    async def test_cancel_sets_status(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.cancel_run(RUN_ID)
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_invalidates_cache(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            await svc.cancel_run(RUN_ID)
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_cancel_permission_denied_member(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.cancel_run(RUN_ID)

    @pytest.mark.asyncio
    async def test_cancel_permission_denied_viewer(self) -> None:
        ctx = _make_ctx("viewer")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.cancel_run(RUN_ID)

    @pytest.mark.asyncio
    async def test_cancel_calls_update_fields(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            await svc.cancel_run(RUN_ID)
        svc._run_repo.update_fields.assert_awaited_once()


# ── TestGetRun ────────────────────────────────────────────────────────────────


class TestGetRun:
    @pytest.mark.asyncio
    async def test_get_run_found(self) -> None:
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run())
        with _patch(ctx, redis):
            result = await svc.get_run(RUN_ID)
        assert result.id == RUN_ID

    @pytest.mark.asyncio
    async def test_get_run_not_found(self) -> None:
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx()
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.get_run(RUN_ID)

    @pytest.mark.asyncio
    async def test_get_run_from_cache(self) -> None:
        ctx = _make_ctx()
        run_out = WorkflowRunOut.model_validate(_make_run())
        redis = _make_redis(cached=run_out.model_dump_json())
        svc = _make_svc()
        with _patch(ctx, redis):
            result = await svc.get_run(RUN_ID)
        assert result.id == RUN_ID
        svc._run_repo.find_by_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_run_cache_miss_stores(self) -> None:
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run())
        with _patch(ctx, redis):
            await svc.get_run(RUN_ID)
        redis.set.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_run_cache_error_ignored(self) -> None:
        ctx = _make_ctx()
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        redis.set = AsyncMock()
        redis.delete = AsyncMock()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run())
        with _patch(ctx, redis):
            result = await svc.get_run(RUN_ID)
        assert result.id == RUN_ID


# ── TestListRuns ──────────────────────────────────────────────────────────────


class TestListRuns:
    @pytest.mark.asyncio
    async def test_list_runs_no_filter(self) -> None:
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.list_page = AsyncMock(return_value=([_make_run()], None))
        with _patch(ctx, redis):
            result = await svc.list_runs(WS_ID)
        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_list_runs_with_status_filter(self) -> None:
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            result = await svc.list_runs(WS_ID, status_filter="completed")
        assert result.items == []

    @pytest.mark.asyncio
    async def test_list_runs_first_page_cached(self) -> None:
        ctx = _make_ctx()
        page = WorkflowRunListPage(items=[], next_cursor=None, has_more=False)
        redis = _make_redis(cached=page.model_dump_json())
        svc = _make_svc()
        with _patch(ctx, redis):
            result = await svc.list_runs(WS_ID)
        assert result.has_more is False
        svc._run_repo.list_page.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_runs_with_cursor_skips_cache(self) -> None:
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            await svc.list_runs(WS_ID, cursor="abc")
        redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_runs_has_more(self) -> None:
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _make_svc()
        svc._run_repo.list_page = AsyncMock(return_value=([_make_run()], "cursor123"))
        with _patch(ctx, redis):
            result = await svc.list_runs(WS_ID)
        assert result.has_more is True
        assert result.next_cursor == "cursor123"

    @pytest.mark.asyncio
    async def test_list_runs_empty(self) -> None:
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            result = await svc.list_runs(WS_ID)
        assert result.items == []
        assert result.has_more is False


# ── TestCompleteStep ──────────────────────────────────────────────────────────


class TestCompleteStep:
    @pytest.mark.asyncio
    async def test_complete_step_basic(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step])
        with _patch(ctx, redis):
            result = await svc.complete_step(STEP_ID, CompleteStepIn())
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_complete_step_not_found(self) -> None:
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.complete_step(STEP_ID, CompleteStepIn())

    @pytest.mark.asyncio
    async def test_complete_step_run_not_found(self) -> None:
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step()
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.complete_step(STEP_ID, CompleteStepIn())

    @pytest.mark.asyncio
    async def test_complete_step_completed_run_raises(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step()
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("completed"))
        with _patch(ctx, redis):
            with pytest.raises(WorkflowRunImmutableError):
                await svc.complete_step(STEP_ID, CompleteStepIn())

    @pytest.mark.asyncio
    async def test_complete_step_cancelled_run_raises(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step()
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("cancelled"))
        with _patch(ctx, redis):
            with pytest.raises(WorkflowRunImmutableError):
                await svc.complete_step(STEP_ID, CompleteStepIn())

    @pytest.mark.asyncio
    async def test_complete_step_sets_completed_by(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step])
        with _patch(ctx, redis):
            result = await svc.complete_step(STEP_ID, CompleteStepIn())
        assert result.completed_by == USER_ID

    @pytest.mark.asyncio
    async def test_complete_step_sets_completed_at(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step])
        with _patch(ctx, redis):
            result = await svc.complete_step(STEP_ID, CompleteStepIn())
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_complete_step_notes_stored(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step])
        with _patch(ctx, redis):
            result = await svc.complete_step(STEP_ID, CompleteStepIn(notes="Done!"))
        assert result.notes == "Done!"

    @pytest.mark.asyncio
    async def test_complete_step_invalidates_cache(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step])
        with _patch(ctx, redis):
            await svc.complete_step(STEP_ID, CompleteStepIn())
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_complete_step_viewer_denied(self) -> None:
        ctx = _make_ctx("viewer")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.complete_step(STEP_ID, CompleteStepIn())


# ── TestReopenStep ────────────────────────────────────────────────────────────


class TestReopenStep:
    @pytest.mark.asyncio
    async def test_reopen_completed_step(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("completed")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.reopen_step(STEP_ID)
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_reopen_step_not_found(self) -> None:
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.reopen_step(STEP_ID)

    @pytest.mark.asyncio
    async def test_reopen_step_cancelled_run_raises(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("completed")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("cancelled"))
        with _patch(ctx, redis):
            with pytest.raises(WorkflowRunImmutableError):
                await svc.reopen_step(STEP_ID)

    @pytest.mark.asyncio
    async def test_reopen_step_clears_completed_by(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("completed")
        step.completed_by = USER_ID
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.reopen_step(STEP_ID)
        assert result.completed_by is None

    @pytest.mark.asyncio
    async def test_reopen_step_clears_completed_at(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("completed")
        step.completed_at = NOW
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.reopen_step(STEP_ID)
        assert result.completed_at is None

    @pytest.mark.asyncio
    async def test_reopen_step_status_pending(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("completed")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.reopen_step(STEP_ID)
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_reopen_step_invalidates_cache(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("completed")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            await svc.reopen_step(STEP_ID)
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_reopen_step_reverts_completed_run_to_active(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("completed")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("completed"))
        with _patch(ctx, redis):
            await svc.reopen_step(STEP_ID)
        svc._run_repo.update_fields.assert_awaited_once()


# ── TestSkipStep ──────────────────────────────────────────────────────────────


class TestSkipStep:
    @pytest.mark.asyncio
    async def test_skip_optional_step(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.skip_step(STEP_ID, SkipStepIn())
        assert result.status == "skipped"

    @pytest.mark.asyncio
    async def test_skip_required_step_raises(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=True)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        with _patch(ctx, redis):
            with pytest.raises(SkipRequiredStepError):
                await svc.skip_step(STEP_ID, SkipStepIn())

    @pytest.mark.asyncio
    async def test_skip_step_not_found(self) -> None:
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.skip_step(STEP_ID, SkipStepIn())

    @pytest.mark.asyncio
    async def test_skip_step_cancelled_run_raises(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("cancelled"))
        with _patch(ctx, redis):
            with pytest.raises(WorkflowRunImmutableError):
                await svc.skip_step(STEP_ID, SkipStepIn())

    @pytest.mark.asyncio
    async def test_skip_step_completed_run_raises(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("completed"))
        with _patch(ctx, redis):
            with pytest.raises(WorkflowRunImmutableError):
                await svc.skip_step(STEP_ID, SkipStepIn())

    @pytest.mark.asyncio
    async def test_skip_step_invalidates_cache(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            await svc.skip_step(STEP_ID, SkipStepIn())
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_skip_step_viewer_denied(self) -> None:
        ctx = _make_ctx("viewer")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.skip_step(STEP_ID, SkipStepIn())

    @pytest.mark.asyncio
    async def test_skip_step_with_notes(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.skip_step(STEP_ID, SkipStepIn(notes="N/A for this client"))
        assert result.notes == "N/A for this client"


# ── TestBlockStep ─────────────────────────────────────────────────────────────


class TestBlockStep:
    @pytest.mark.asyncio
    async def test_block_step(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.block_step(STEP_ID, BlockStepIn())
        assert result.status == "blocked"

    @pytest.mark.asyncio
    async def test_block_step_not_found(self) -> None:
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.block_step(STEP_ID, BlockStepIn())

    @pytest.mark.asyncio
    async def test_block_step_cancelled_run_raises(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("cancelled"))
        with _patch(ctx, redis):
            with pytest.raises(WorkflowRunImmutableError):
                await svc.block_step(STEP_ID, BlockStepIn())

    @pytest.mark.asyncio
    async def test_block_step_completed_run_raises(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("completed"))
        with _patch(ctx, redis):
            with pytest.raises(WorkflowRunImmutableError):
                await svc.block_step(STEP_ID, BlockStepIn())

    @pytest.mark.asyncio
    async def test_block_step_with_notes(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.block_step(STEP_ID, BlockStepIn(notes="Waiting on legal"))
        assert result.notes == "Waiting on legal"

    @pytest.mark.asyncio
    async def test_block_step_invalidates_cache(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            await svc.block_step(STEP_ID, BlockStepIn())
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_block_step_viewer_denied(self) -> None:
        ctx = _make_ctx("viewer")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.block_step(STEP_ID, BlockStepIn())


# ── TestResumeStep ────────────────────────────────────────────────────────────


class TestResumeStep:
    @pytest.mark.asyncio
    async def test_resume_blocked_step(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("blocked")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.resume_step(STEP_ID)
        assert result.status == "in_progress"

    @pytest.mark.asyncio
    async def test_resume_step_not_found(self) -> None:
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.resume_step(STEP_ID)

    @pytest.mark.asyncio
    async def test_resume_non_blocked_step_raises(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        with _patch(ctx, redis):
            with pytest.raises(StepStateError):
                await svc.resume_step(STEP_ID)

    @pytest.mark.asyncio
    async def test_resume_step_cancelled_run_raises(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("blocked")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("cancelled"))
        with _patch(ctx, redis):
            with pytest.raises(WorkflowRunImmutableError):
                await svc.resume_step(STEP_ID)

    @pytest.mark.asyncio
    async def test_resume_step_sets_in_progress(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("blocked")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.resume_step(STEP_ID)
        assert result.status == "in_progress"

    @pytest.mark.asyncio
    async def test_resume_step_invalidates_cache(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("blocked")
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            await svc.resume_step(STEP_ID)
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_resume_step_viewer_denied(self) -> None:
        ctx = _make_ctx("viewer")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.resume_step(STEP_ID)


# ── TestWorkflowCompletion ────────────────────────────────────────────────────


class TestWorkflowCompletion:
    @pytest.mark.asyncio
    async def test_all_required_steps_done_auto_completes(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=True)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        # After service mutates step.status → "completed", find_by_run returns it
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step])
        with _patch(ctx, redis):
            await svc.complete_step(STEP_ID, CompleteStepIn())
        svc._run_repo.update_fields.assert_awaited()

    @pytest.mark.asyncio
    async def test_partial_completion_stays_active(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step1 = _make_run_step("pending", required=True, step_id=STEP_ID)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step1)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        step2_pending = _make_run_step("pending", required=True, step_id=STEP2_ID)
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step1, step2_pending])
        with _patch(ctx, redis):
            await svc.complete_step(STEP_ID, CompleteStepIn())
        svc._run_repo.update_fields.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_required_steps_stays_active(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=False)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step])
        with _patch(ctx, redis):
            await svc.complete_step(STEP_ID, CompleteStepIn())
        svc._run_repo.update_fields.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_steps_stays_active(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=True)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[])
        with _patch(ctx, redis):
            await svc.complete_step(STEP_ID, CompleteStepIn())
        svc._run_repo.update_fields.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_blocked_required_step_prevents_completion(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step1 = _make_run_step("pending", required=True, step_id=STEP_ID)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step1)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        step2_blocked = _make_run_step("blocked", required=True, step_id=STEP2_ID)
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step1, step2_blocked])
        with _patch(ctx, redis):
            await svc.complete_step(STEP_ID, CompleteStepIn())
        svc._run_repo.update_fields.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_completion_sets_completed_at(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=True)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step])
        captured_kwargs: list = []

        async def capture_update(run_id, **kwargs):
            captured_kwargs.append(kwargs)

        svc._run_repo.update_fields = capture_update
        with _patch(ctx, redis):
            await svc.complete_step(STEP_ID, CompleteStepIn())
        assert any("completed_at" in kw for kw in captured_kwargs)

    @pytest.mark.asyncio
    async def test_completion_status_is_completed(self) -> None:
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        step = _make_run_step("pending", required=True)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        svc._run_step_repo.find_by_run = AsyncMock(return_value=[step])
        captured_kwargs: list = []

        async def capture_update(run_id, **kwargs):
            captured_kwargs.append(kwargs)

        svc._run_repo.update_fields = capture_update
        with _patch(ctx, redis):
            await svc.complete_step(STEP_ID, CompleteStepIn())
        assert any(kw.get("status") == "completed" for kw in captured_kwargs)

    @pytest.mark.asyncio
    async def test_skip_non_required_does_not_block_completion(self) -> None:
        """Required step done + optional skipped → run auto-completes."""
        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        req_step = _make_run_step("pending", required=True, step_id=STEP_ID)
        svc._run_step_repo.find_by_id = AsyncMock(return_value=req_step)
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        optional_skipped = _make_run_step("skipped", required=False, step_id=STEP2_ID)
        svc._run_step_repo.find_by_run = AsyncMock(
            return_value=[req_step, optional_skipped]
        )
        with _patch(ctx, redis):
            await svc.complete_step(STEP_ID, CompleteStepIn())
        svc._run_repo.update_fields.assert_awaited()


# ── TestCacheResilience ───────────────────────────────────────────────────────


class TestCacheResilience:
    @pytest.mark.asyncio
    async def test_list_cache_error_ignored(self) -> None:
        ctx = _make_ctx()
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        redis.set = AsyncMock()
        redis.delete = AsyncMock()
        svc = _make_svc()
        with _patch(ctx, redis):
            result = await svc.list_runs(WS_ID)
        assert result.items == []

    @pytest.mark.asyncio
    async def test_detail_cache_error_ignored(self) -> None:
        ctx = _make_ctx()
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        redis.set = AsyncMock()
        redis.delete = AsyncMock()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run())
        with _patch(ctx, redis):
            result = await svc.get_run(RUN_ID)
        assert result.id == RUN_ID

    @pytest.mark.asyncio
    async def test_invalidation_error_ignored(self) -> None:
        ctx = _make_ctx("owner")
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run("active"))
        with _patch(ctx, redis):
            result = await svc.cancel_run(RUN_ID)
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cache_set_error_ignored(self) -> None:
        ctx = _make_ctx()
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(side_effect=Exception("redis full"))
        redis.delete = AsyncMock()
        svc = _make_svc()
        svc._run_repo.find_by_id = AsyncMock(return_value=_make_run())
        with _patch(ctx, redis):
            result = await svc.get_run(RUN_ID)
        assert result.id == RUN_ID


# ── TestTenantIsolation ───────────────────────────────────────────────────────


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_start_run_uses_ctx_org_id(self) -> None:
        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        captured: list = []

        async def capture(run):
            captured.append(run)
            return run

        svc._template_repo.find_by_id = AsyncMock(return_value=MagicMock())
        svc._run_repo.create = capture
        run = _make_run()
        svc.get_run = AsyncMock(return_value=WorkflowRunOut.model_validate(run))
        with _patch(ctx, redis):
            await svc.start_run(
                WorkflowRunIn(workspace_id=WS_ID, workflow_template_id=TMPL_ID, title="Run")
            )
        assert captured[0].tenant_id == ORG_ID

    @pytest.mark.asyncio
    async def test_cancel_scoped_to_tenant(self) -> None:
        """Runs from another tenant appear as not-found (repo returns None)."""
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx("owner")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.cancel_run(RUN_ID)

    @pytest.mark.asyncio
    async def test_get_run_scoped_to_tenant(self) -> None:
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx()
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.get_run(RUN_ID)

    @pytest.mark.asyncio
    async def test_step_action_scoped_to_tenant(self) -> None:
        from corpmind.core.exceptions import NotFoundError

        ctx = _make_ctx("member")
        redis = _make_redis()
        svc = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.complete_step(STEP_ID, CompleteStepIn())
