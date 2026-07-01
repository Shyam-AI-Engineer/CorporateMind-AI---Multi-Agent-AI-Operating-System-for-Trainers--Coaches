"""Unit tests for Sprint 35 — Workflow Entity Integration.

Covers: attach_entity, detach_entity, list_entity_runs, find_active_run,
cache key helpers, DuplicateActiveEntityRunError, permissions, tenant isolation,
repo methods, schema validation, notification calls.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.workflows.schemas import (
    AttachEntityIn,
    EntityRunListPage,
    WorkflowRunOut,
    _VALID_ENTITY_TYPES,
)
from corpmind.modules.workflows.service import (
    DuplicateActiveEntityRunError,
    PermissionDeniedError,
    WorkflowExecutionService,
    _active_entity_key,
    _entity_runs_key,
)
from corpmind.core.exceptions import NotFoundError


# ── Test fixtures ─────────────────────────────────────────────────────────────

ORG_ID = uuid.uuid4()
WS_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
RUN_ID = uuid.uuid4()
ENTITY_ID = uuid.uuid4()


def _make_ctx(role: str = "owner") -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = ORG_ID
    ctx.user_id = USER_ID
    ctx.role = role
    return ctx


def _make_run(
    run_id: uuid.UUID = RUN_ID,
    status: str = "active",
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    entity_title: str | None = None,
) -> MagicMock:
    run = MagicMock()
    run.id = run_id
    run.tenant_id = ORG_ID
    run.workspace_id = WS_ID
    run.status = status
    run.entity_type = entity_type
    run.entity_id = entity_id
    run.entity_title = entity_title
    run.title = "Test Run"
    run.started_by = USER_ID
    run.assigned_to = None
    run.started_at = datetime.now(UTC)
    run.completed_at = None
    run.cancelled_at = None
    run.run_steps = []
    run.workflow_template_id = None
    return run


def _make_redis(cached_value: str | None = None) -> MagicMock:
    """Redis mock with all async methods properly typed as AsyncMock."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=cached_value)
    mock.set = AsyncMock()
    mock.delete = AsyncMock()
    return mock


def _make_svc() -> WorkflowExecutionService:
    svc = WorkflowExecutionService(MagicMock())
    svc._run_repo = MagicMock()
    svc._run_repo.find_by_id = AsyncMock(return_value=None)
    svc._run_repo.update_fields = AsyncMock()
    svc._run_repo.list_page = AsyncMock(return_value=([], None))
    svc._run_repo.find_by_entity = AsyncMock(return_value=([], None))
    svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)
    svc._run_step_repo = MagicMock()
    svc._run_step_repo.find_by_run = AsyncMock(return_value=[])
    svc._template_repo = MagicMock()
    svc._step_repo = MagicMock()
    svc._notify = AsyncMock()
    return svc


# ── Cache key helpers ─────────────────────────────────────────────────────────

class TestEntityCacheKeys:
    def test_entity_runs_key_format(self) -> None:
        key = _entity_runs_key(ORG_ID, WS_ID, "lead", ENTITY_ID)
        assert key == f"t:{ORG_ID}:{WS_ID}:workflow_entity_runs:lead:{ENTITY_ID}"

    def test_active_entity_key_format(self) -> None:
        key = _active_entity_key(ORG_ID, WS_ID, "proposal", ENTITY_ID)
        assert key == f"t:{ORG_ID}:{WS_ID}:workflow_active_entity:proposal:{ENTITY_ID}"

    def test_keys_are_tenant_scoped(self) -> None:
        other_org = uuid.uuid4()
        k1 = _entity_runs_key(ORG_ID, WS_ID, "lead", ENTITY_ID)
        k2 = _entity_runs_key(other_org, WS_ID, "lead", ENTITY_ID)
        assert k1 != k2

    def test_keys_differ_by_entity_type(self) -> None:
        k1 = _entity_runs_key(ORG_ID, WS_ID, "lead", ENTITY_ID)
        k2 = _entity_runs_key(ORG_ID, WS_ID, "proposal", ENTITY_ID)
        assert k1 != k2

    def test_keys_differ_by_entity_id(self) -> None:
        other_id = uuid.uuid4()
        k1 = _entity_runs_key(ORG_ID, WS_ID, "lead", ENTITY_ID)
        k2 = _entity_runs_key(ORG_ID, WS_ID, "lead", other_id)
        assert k1 != k2

    def test_active_and_runs_keys_differ(self) -> None:
        k1 = _entity_runs_key(ORG_ID, WS_ID, "lead", ENTITY_ID)
        k2 = _active_entity_key(ORG_ID, WS_ID, "lead", ENTITY_ID)
        assert k1 != k2

    def test_runs_key_contains_entity_type(self) -> None:
        key = _entity_runs_key(ORG_ID, WS_ID, "campaign", ENTITY_ID)
        assert "workflow_entity_runs" in key
        assert "campaign" in key

    def test_active_key_contains_entity_type(self) -> None:
        key = _active_entity_key(ORG_ID, WS_ID, "customer", ENTITY_ID)
        assert "workflow_active_entity" in key
        assert "customer" in key


# ── Schema validation — AttachEntityIn ───────────────────────────────────────

class TestAttachEntityInSchema:
    def test_valid_entity_types(self) -> None:
        for et in _VALID_ENTITY_TYPES:
            data = AttachEntityIn(
                entity_type=et,
                entity_id=ENTITY_ID,
                entity_title="Some Entity",
            )
            assert data.entity_type == et

    def test_invalid_entity_type_raises(self) -> None:
        with pytest.raises(Exception):
            AttachEntityIn(
                entity_type="invalid_type",
                entity_id=ENTITY_ID,
                entity_title="Title",
            )

    def test_empty_entity_title_raises(self) -> None:
        with pytest.raises(Exception):
            AttachEntityIn(
                entity_type="lead",
                entity_id=ENTITY_ID,
                entity_title="   ",
            )

    def test_entity_title_too_long_raises(self) -> None:
        with pytest.raises(Exception):
            AttachEntityIn(
                entity_type="lead",
                entity_id=ENTITY_ID,
                entity_title="x" * 256,
            )

    def test_entity_title_stripped(self) -> None:
        data = AttachEntityIn(
            entity_type="lead",
            entity_id=ENTITY_ID,
            entity_title="  My Lead  ",
        )
        assert data.entity_title == "My Lead"

    def test_all_six_entity_types_valid(self) -> None:
        for et in ("lead", "proposal", "campaign", "customer", "training", "other"):
            assert et in _VALID_ENTITY_TYPES

    def test_entity_title_exactly_255_chars_valid(self) -> None:
        data = AttachEntityIn(
            entity_type="other",
            entity_id=ENTITY_ID,
            entity_title="x" * 255,
        )
        assert len(data.entity_title) == 255


# ── attach_entity ─────────────────────────────────────────────────────────────

class TestAttachEntity:
    @pytest.mark.asyncio
    async def test_attaches_entity_to_run(self) -> None:
        svc = _make_svc()
        run = _make_run()
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)

        data = AttachEntityIn(
            entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme Corp"
        )
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            result = await svc.attach_entity(RUN_ID, data)

        svc._run_repo.update_fields.assert_awaited_once()  # type: ignore[attr-defined]
        assert result.entity_type == "lead"

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_run(self) -> None:
        svc = _make_svc()
        data = AttachEntityIn(
            entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme"
        )
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            with pytest.raises(NotFoundError):
                await svc.attach_entity(RUN_ID, data)

    @pytest.mark.asyncio
    async def test_raises_permission_denied_for_member(self) -> None:
        svc = _make_svc()
        data = AttachEntityIn(
            entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme"
        )
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("member"),
        ):
            with pytest.raises(PermissionDeniedError):
                await svc.attach_entity(RUN_ID, data)

    @pytest.mark.asyncio
    async def test_raises_permission_denied_for_viewer(self) -> None:
        svc = _make_svc()
        data = AttachEntityIn(
            entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme"
        )
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("viewer"),
        ):
            with pytest.raises(PermissionDeniedError):
                await svc.attach_entity(RUN_ID, data)

    @pytest.mark.asyncio
    async def test_raises_duplicate_active_when_other_run_active(self) -> None:
        svc = _make_svc()
        run = _make_run()
        other_run = _make_run(run_id=uuid.uuid4(), status="active")
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=other_run)

        data = AttachEntityIn(
            entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme"
        )
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            with pytest.raises(DuplicateActiveEntityRunError):
                await svc.attach_entity(RUN_ID, data)

    @pytest.mark.asyncio
    async def test_allows_reattach_to_same_run(self) -> None:
        """Re-attaching entity to the SAME run is allowed (not a conflict)."""
        svc = _make_svc()
        run = _make_run(entity_type="lead", entity_id=ENTITY_ID, entity_title="Old")
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=run)

        data = AttachEntityIn(
            entity_type="lead", entity_id=ENTITY_ID, entity_title="New Title"
        )
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.attach_entity(RUN_ID, data)

        svc._run_repo.update_fields.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_update_fields_called_with_entity_data(self) -> None:
        svc = _make_svc()
        run = _make_run()
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)

        data = AttachEntityIn(
            entity_type="proposal", entity_id=ENTITY_ID, entity_title="Q2 Proposal"
        )
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.attach_entity(RUN_ID, data)

        call_kwargs = svc._run_repo.update_fields.call_args.kwargs  # type: ignore[attr-defined]
        assert call_kwargs["entity_type"] == "proposal"
        assert call_kwargs["entity_id"] == ENTITY_ID
        assert call_kwargs["entity_title"] == "Q2 Proposal"

    @pytest.mark.asyncio
    async def test_notification_sent_on_attach(self) -> None:
        svc = _make_svc()
        run = _make_run()
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)

        data = AttachEntityIn(
            entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme"
        )
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.attach_entity(RUN_ID, data)

        svc._notify.assert_awaited_once()  # type: ignore[attr-defined]
        notify_kwargs = svc._notify.call_args.kwargs  # type: ignore[attr-defined]
        assert notify_kwargs["notification_type"] == "workflow_entity_attached"

    @pytest.mark.asyncio
    async def test_cache_invalidated_run_and_entity_on_attach(self) -> None:
        svc = _make_svc()
        run = _make_run()
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)

        data = AttachEntityIn(
            entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme"
        )
        mock_redis = _make_redis()
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            await svc.attach_entity(RUN_ID, data)

        # _invalidate_run calls delete once; _invalidate_entity calls delete once = 2
        assert mock_redis.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_completed_run_can_be_attached(self) -> None:
        """Entity fields are not immutable even after run completes."""
        svc = _make_svc()
        run = _make_run(status="completed")
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)

        data = AttachEntityIn(
            entity_type="training", entity_id=ENTITY_ID, entity_title="Corp Training"
        )
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("admin"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.attach_entity(RUN_ID, data)

        svc._run_repo.update_fields.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_admin_can_attach(self) -> None:
        svc = _make_svc()
        run = _make_run()
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)
        data = AttachEntityIn(
            entity_type="lead", entity_id=ENTITY_ID, entity_title="Lead"
        )
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("admin"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.attach_entity(RUN_ID, data)

        svc._run_repo.update_fields.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_entity_fields_reflected_in_return_value(self) -> None:
        svc = _make_svc()
        run = _make_run()
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)

        data = AttachEntityIn(
            entity_type="customer", entity_id=ENTITY_ID, entity_title="Tata Corp"
        )
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            result = await svc.attach_entity(RUN_ID, data)

        assert result.entity_type == "customer"
        assert result.entity_id == ENTITY_ID
        assert result.entity_title == "Tata Corp"


# ── detach_entity ─────────────────────────────────────────────────────────────

class TestDetachEntity:
    @pytest.mark.asyncio
    async def test_clears_entity_fields(self) -> None:
        svc = _make_svc()
        run = _make_run(entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme")
        svc._run_repo.find_by_id = AsyncMock(return_value=run)

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.detach_entity(RUN_ID)

        call_kwargs = svc._run_repo.update_fields.call_args.kwargs  # type: ignore[attr-defined]
        assert call_kwargs["entity_type"] is None
        assert call_kwargs["entity_id"] is None
        assert call_kwargs["entity_title"] is None

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_run(self) -> None:
        svc = _make_svc()
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ):
            with pytest.raises(NotFoundError):
                await svc.detach_entity(RUN_ID)

    @pytest.mark.asyncio
    async def test_raises_permission_denied_for_member(self) -> None:
        svc = _make_svc()
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("member"),
        ):
            with pytest.raises(PermissionDeniedError):
                await svc.detach_entity(RUN_ID)

    @pytest.mark.asyncio
    async def test_raises_permission_denied_for_viewer(self) -> None:
        svc = _make_svc()
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("viewer"),
        ):
            with pytest.raises(PermissionDeniedError):
                await svc.detach_entity(RUN_ID)

    @pytest.mark.asyncio
    async def test_notification_sent_on_detach(self) -> None:
        svc = _make_svc()
        run = _make_run(entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme")
        svc._run_repo.find_by_id = AsyncMock(return_value=run)

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.detach_entity(RUN_ID)

        svc._notify.assert_awaited_once()  # type: ignore[attr-defined]
        assert svc._notify.call_args.kwargs["notification_type"] == "workflow_entity_detached"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_entity_cache_invalidated_on_detach(self) -> None:
        svc = _make_svc()
        run = _make_run(entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme")
        svc._run_repo.find_by_id = AsyncMock(return_value=run)

        mock_redis = _make_redis()
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            await svc.detach_entity(RUN_ID)

        # _invalidate_run (1) + _invalidate_entity (1) = 2
        assert mock_redis.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_detach_run_with_no_entity_skips_entity_cache(self) -> None:
        """Only run cache is invalidated when run has no attached entity."""
        svc = _make_svc()
        run = _make_run()  # entity_type=None, entity_id=None
        svc._run_repo.find_by_id = AsyncMock(return_value=run)

        mock_redis = _make_redis()
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            await svc.detach_entity(RUN_ID)

        # Only _invalidate_run fires (1 delete call with 2 keys as *args)
        assert mock_redis.delete.await_count == 1

    @pytest.mark.asyncio
    async def test_completed_run_can_be_detached(self) -> None:
        svc = _make_svc()
        run = _make_run(
            status="completed",
            entity_type="lead",
            entity_id=ENTITY_ID,
            entity_title="X",
        )
        svc._run_repo.find_by_id = AsyncMock(return_value=run)

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("admin"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.detach_entity(RUN_ID)

        svc._run_repo.update_fields.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_cancelled_run_can_be_detached(self) -> None:
        svc = _make_svc()
        run = _make_run(
            status="cancelled",
            entity_type="proposal",
            entity_id=ENTITY_ID,
            entity_title="Y",
        )
        svc._run_repo.find_by_id = AsyncMock(return_value=run)

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.detach_entity(RUN_ID)

        svc._run_repo.update_fields.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_return_value_has_null_entity_fields(self) -> None:
        svc = _make_svc()
        run = _make_run(entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme")
        svc._run_repo.find_by_id = AsyncMock(return_value=run)

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            result = await svc.detach_entity(RUN_ID)

        assert result.entity_type is None
        assert result.entity_id is None
        assert result.entity_title is None


# ── list_entity_runs ──────────────────────────────────────────────────────────

class TestListEntityRuns:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none_found(self) -> None:
        svc = _make_svc()

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            result = await svc.list_entity_runs(WS_ID, "lead", ENTITY_ID)

        assert result.items == []
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_returns_runs_for_entity(self) -> None:
        svc = _make_svc()
        run = _make_run(entity_type="lead", entity_id=ENTITY_ID, entity_title="Acme")
        svc._run_repo.find_by_entity = AsyncMock(return_value=([run], None))

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            result = await svc.list_entity_runs(WS_ID, "lead", ENTITY_ID)

        assert len(result.items) == 1
        assert result.items[0].id == run.id

    @pytest.mark.asyncio
    async def test_uses_cache_on_first_page_hit(self) -> None:
        svc = _make_svc()
        cached_page = EntityRunListPage(items=[], next_cursor=None, has_more=False)
        mock_redis = _make_redis(cached_value=cached_page.model_dump_json())

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            result = await svc.list_entity_runs(WS_ID, "lead", ENTITY_ID)

        svc._run_repo.find_by_entity.assert_not_awaited()  # type: ignore[attr-defined]
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_writes_result_to_cache_on_first_page_miss(self) -> None:
        svc = _make_svc()
        mock_redis = _make_redis()

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            await svc.list_entity_runs(WS_ID, "lead", ENTITY_ID)

        mock_redis.set.assert_awaited_once()
        assert mock_redis.set.call_args.kwargs.get("ex") == 300

    @pytest.mark.asyncio
    async def test_cursor_page_skips_cache_read(self) -> None:
        svc = _make_svc()
        mock_redis = _make_redis()

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            await svc.list_entity_runs(WS_ID, "lead", ENTITY_ID, cursor="abc123")

        mock_redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cursor_page_skips_cache_write(self) -> None:
        svc = _make_svc()
        mock_redis = _make_redis()

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            await svc.list_entity_runs(WS_ID, "lead", ENTITY_ID, cursor="abc123")

        mock_redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_has_more_true_when_next_cursor_exists(self) -> None:
        svc = _make_svc()
        svc._run_repo.find_by_entity = AsyncMock(return_value=([], "next_cursor_val"))

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            result = await svc.list_entity_runs(WS_ID, "lead", ENTITY_ID)

        assert result.has_more is True
        assert result.next_cursor == "next_cursor_val"

    @pytest.mark.asyncio
    async def test_passes_correct_args_to_repo(self) -> None:
        svc = _make_svc()

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.list_entity_runs(WS_ID, "campaign", ENTITY_ID, limit=10)

        call_args = svc._run_repo.find_by_entity.call_args  # type: ignore[attr-defined]
        assert call_args.args[0] == WS_ID
        assert call_args.args[1] == "campaign"
        assert call_args.args[2] == ENTITY_ID

    @pytest.mark.asyncio
    async def test_result_is_entity_run_list_page(self) -> None:
        svc = _make_svc()

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            result = await svc.list_entity_runs(WS_ID, "proposal", ENTITY_ID)

        assert isinstance(result, EntityRunListPage)


# ── find_active_run ───────────────────────────────────────────────────────────

class TestFindActiveRun:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_active_run(self) -> None:
        svc = _make_svc()
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            result = await svc.find_active_run(WS_ID, "lead", ENTITY_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_active_run(self) -> None:
        svc = _make_svc()
        run = _make_run(status="active", entity_type="lead", entity_id=ENTITY_ID)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=run)

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            result = await svc.find_active_run(WS_ID, "lead", ENTITY_ID)

        assert result is not None
        assert result.id == RUN_ID

    @pytest.mark.asyncio
    async def test_returns_pending_run(self) -> None:
        svc = _make_svc()
        run = _make_run(status="pending", entity_type="lead", entity_id=ENTITY_ID)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=run)

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            result = await svc.find_active_run(WS_ID, "lead", ENTITY_ID)

        assert result is not None
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_uses_cache_on_hit(self) -> None:
        svc = _make_svc()
        run = _make_run(status="active", entity_type="lead", entity_id=ENTITY_ID)
        cached_out = WorkflowRunOut.model_validate(run)
        mock_redis = _make_redis(cached_value=cached_out.model_dump_json())

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            result = await svc.find_active_run(WS_ID, "lead", ENTITY_ID)

        svc._run_repo.find_active_entity_run.assert_not_awaited()  # type: ignore[attr-defined]
        assert result is not None

    @pytest.mark.asyncio
    async def test_writes_to_cache_when_run_found(self) -> None:
        svc = _make_svc()
        run = _make_run(status="active", entity_type="lead", entity_id=ENTITY_ID)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=run)
        mock_redis = _make_redis()

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            await svc.find_active_run(WS_ID, "lead", ENTITY_ID)

        mock_redis.set.assert_awaited_once()
        assert mock_redis.set.call_args.kwargs.get("ex") == 300

    @pytest.mark.asyncio
    async def test_does_not_write_cache_when_none(self) -> None:
        svc = _make_svc()
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)
        mock_redis = _make_redis()

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            result = await svc.find_active_run(WS_ID, "lead", ENTITY_ID)

        mock_redis.set.assert_not_awaited()
        assert result is None

    @pytest.mark.asyncio
    async def test_result_is_workflow_run_out(self) -> None:
        svc = _make_svc()
        run = _make_run(status="active")
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=run)

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            result = await svc.find_active_run(WS_ID, "lead", ENTITY_ID)

        assert isinstance(result, WorkflowRunOut)


# ── DuplicateActiveEntityRunError ─────────────────────────────────────────────

class TestDuplicateActiveEntityRunError:
    def test_is_exception(self) -> None:
        assert issubclass(DuplicateActiveEntityRunError, Exception)

    def test_error_carries_message(self) -> None:
        err = DuplicateActiveEntityRunError("Entity already has active run")
        assert "already" in str(err)

    @pytest.mark.asyncio
    async def test_raised_when_different_active_run_exists(self) -> None:
        svc = _make_svc()
        run = _make_run()
        conflict_run = _make_run(run_id=uuid.uuid4(), status="active")
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=conflict_run)

        data = AttachEntityIn(entity_type="lead", entity_id=ENTITY_ID, entity_title="X")
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            with pytest.raises(DuplicateActiveEntityRunError):
                await svc.attach_entity(RUN_ID, data)

    @pytest.mark.asyncio
    async def test_not_raised_when_existing_run_is_same(self) -> None:
        svc = _make_svc()
        run = _make_run()
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=run)

        data = AttachEntityIn(entity_type="lead", entity_id=ENTITY_ID, entity_title="X")
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.attach_entity(RUN_ID, data)

    @pytest.mark.asyncio
    async def test_not_raised_when_no_active_run_exists(self) -> None:
        svc = _make_svc()
        run = _make_run()
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)

        data = AttachEntityIn(entity_type="lead", entity_id=ENTITY_ID, entity_title="X")
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.attach_entity(RUN_ID, data)


# ── Tenant isolation ──────────────────────────────────────────────────────────

class TestEntityTenantIsolation:
    @pytest.mark.asyncio
    async def test_attach_raises_not_found_for_different_tenant_run(self) -> None:
        """RLS causes find_by_id to return None for cross-tenant runs."""
        svc = _make_svc()
        data = AttachEntityIn(entity_type="lead", entity_id=ENTITY_ID, entity_title="X")

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            with pytest.raises(NotFoundError):
                await svc.attach_entity(RUN_ID, data)

    @pytest.mark.asyncio
    async def test_detach_raises_not_found_for_different_tenant_run(self) -> None:
        svc = _make_svc()
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ):
            with pytest.raises(NotFoundError):
                await svc.detach_entity(RUN_ID)

    def test_entity_runs_cache_key_is_org_scoped(self) -> None:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        k1 = _entity_runs_key(org_a, WS_ID, "lead", ENTITY_ID)
        k2 = _entity_runs_key(org_b, WS_ID, "lead", ENTITY_ID)
        assert k1 != k2

    def test_active_entity_cache_key_is_org_scoped(self) -> None:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        k1 = _active_entity_key(org_a, WS_ID, "proposal", ENTITY_ID)
        k2 = _active_entity_key(org_b, WS_ID, "proposal", ENTITY_ID)
        assert k1 != k2

    def test_cache_keys_include_org_id(self) -> None:
        key = _entity_runs_key(ORG_ID, WS_ID, "lead", ENTITY_ID)
        assert str(ORG_ID) in key

    @pytest.mark.asyncio
    async def test_find_active_run_passes_workspace_to_repo(self) -> None:
        svc = _make_svc()
        other_ws = uuid.uuid4()

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=_make_redis(),
        ):
            await svc.find_active_run(other_ws, "lead", ENTITY_ID)

        call_args = svc._run_repo.find_active_entity_run.call_args  # type: ignore[attr-defined]
        assert call_args.args[0] == other_ws


# ── Redis error resilience ────────────────────────────────────────────────────

class TestRedisErrorResilience:
    @pytest.mark.asyncio
    async def test_attach_continues_if_cache_invalidation_fails(self) -> None:
        svc = _make_svc()
        run = _make_run()
        svc._run_repo.find_by_id = AsyncMock(return_value=run)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=None)

        failing_redis = _make_redis()
        failing_redis.delete = AsyncMock(side_effect=ConnectionError("Redis down"))

        data = AttachEntityIn(entity_type="lead", entity_id=ENTITY_ID, entity_title="X")
        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx("owner"),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=failing_redis,
        ):
            result = await svc.attach_entity(RUN_ID, data)

        assert result is not None
        svc._run_repo.update_fields.assert_awaited_once()  # type: ignore[attr-defined]  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_find_active_run_falls_back_to_repo_on_redis_error(self) -> None:
        svc = _make_svc()
        run = _make_run(status="active", entity_type="lead", entity_id=ENTITY_ID)
        svc._run_repo.find_active_entity_run = AsyncMock(return_value=run)

        failing_redis = _make_redis()
        failing_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=failing_redis,
        ):
            result = await svc.find_active_run(WS_ID, "lead", ENTITY_ID)

        svc._run_repo.find_active_entity_run.assert_awaited_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_list_entity_runs_continues_if_cache_read_fails(self) -> None:
        svc = _make_svc()
        run = _make_run(entity_type="lead", entity_id=ENTITY_ID)
        svc._run_repo.find_by_entity = AsyncMock(return_value=([run], None))

        failing_redis = _make_redis()
        failing_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))

        with patch(
            "corpmind.modules.workflows.service.get_tenant_context",
            return_value=_make_ctx(),
        ), patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=failing_redis,
        ):
            result = await svc.list_entity_runs(WS_ID, "lead", ENTITY_ID)

        assert len(result.items) == 1


# ── _invalidate_entity ────────────────────────────────────────────────────────

class TestInvalidateEntity:
    @pytest.mark.asyncio
    async def test_deletes_both_entity_cache_keys(self) -> None:
        svc = _make_svc()
        mock_redis = _make_redis()

        with patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            await svc._invalidate_entity(ORG_ID, WS_ID, "lead", ENTITY_ID)

        mock_redis.delete.assert_awaited_once()
        deleted_keys = mock_redis.delete.call_args.args
        assert len(deleted_keys) == 2
        assert any("workflow_entity_runs" in k for k in deleted_keys)
        assert any("workflow_active_entity" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_swallows_redis_error(self) -> None:
        svc = _make_svc()
        failing_redis = _make_redis()
        failing_redis.delete = AsyncMock(side_effect=Exception("Redis error"))

        with patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=failing_redis,
        ):
            await svc._invalidate_entity(ORG_ID, WS_ID, "lead", ENTITY_ID)

    @pytest.mark.asyncio
    async def test_deleted_keys_include_entity_type_and_id(self) -> None:
        svc = _make_svc()
        mock_redis = _make_redis()

        with patch(
            "corpmind.modules.workflows.service.get_redis",
            return_value=mock_redis,
        ):
            await svc._invalidate_entity(ORG_ID, WS_ID, "proposal", ENTITY_ID)

        deleted_keys = mock_redis.delete.call_args.args
        assert all("proposal" in k for k in deleted_keys)
        assert all(str(ENTITY_ID) in k for k in deleted_keys)


# ── Notification schema coverage ──────────────────────────────────────────────

class TestNotificationSchemaEntityTypes:
    def test_workflow_entity_attached_is_valid_notification_type(self) -> None:
        from corpmind.modules.notifications.schemas import _VALID_NOTIFICATION_TYPES

        assert "workflow_entity_attached" in _VALID_NOTIFICATION_TYPES

    def test_workflow_entity_detached_is_valid_notification_type(self) -> None:
        from corpmind.modules.notifications.schemas import _VALID_NOTIFICATION_TYPES

        assert "workflow_entity_detached" in _VALID_NOTIFICATION_TYPES
