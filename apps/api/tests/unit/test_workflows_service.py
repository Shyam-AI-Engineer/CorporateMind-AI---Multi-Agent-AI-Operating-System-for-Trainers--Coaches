"""Unit tests for Workflow Templates & Playbooks service — Sprint 33.

Covers:
- WorkflowService: create_template, get_template, update_template, delete_template
- WorkflowService: duplicate_template, list_templates
- WorkflowService: add_step, update_step, delete_step, reorder_steps
- Permission checks (owner/admin vs member/viewer)
- Redis cache hit / miss / invalidation
- Tenant isolation
- Schema validators
- Cache resilience (Redis errors)
- StepOrderConflictError on bad reorder
- Pagination cursor logic
"""

from __future__ import annotations

import base64
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.workflows.schemas import (
    ReorderStepsIn,
    WorkflowStepIn,
    WorkflowStepOut,
    WorkflowStepUpdate,
    WorkflowTemplateIn,
    WorkflowTemplateListPage,
    WorkflowTemplateOut,
    WorkflowTemplateUpdate,
)
from corpmind.modules.workflows.service import (
    PermissionDeniedError,
    StepOrderConflictError,
    WorkflowService,
    _detail_key,
    _list_key,
)

# ── Constants ──────────────────────────────────────────────────────────────────

ORG_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WS_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
TMPL_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
TMPL_ID_2 = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
STEP_ID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
STEP_ID_2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
STEP_ID_3 = uuid.UUID("33333333-3333-3333-3333-333333333333")

NOW = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)


# ── Mock helpers ───────────────────────────────────────────────────────────────

def _make_ctx(role: str = "admin") -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = ORG_ID
    ctx.workspace_id = WS_ID
    ctx.user_id = USER_ID
    ctx.role = role
    return ctx


def _make_redis(cached_value: str | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached_value)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _template(
    id: uuid.UUID = TMPL_ID,
    workspace_id: uuid.UUID = WS_ID,
    name: str = "New Corporate Lead",
    description: str | None = "Standard onboarding",
    category: str = "new_corporate_lead",
    is_active: bool = True,
    created_by: uuid.UUID = USER_ID,
    created_at: datetime = NOW,
    steps: list[Any] | None = None,
) -> MagicMock:
    t = MagicMock()
    t.id = id
    t.tenant_id = ORG_ID
    t.workspace_id = workspace_id
    t.name = name
    t.description = description
    t.category = category
    t.is_active = is_active
    t.created_by = created_by
    t.created_at = created_at
    t.steps = steps or []
    return t


def _step(
    id: uuid.UUID = STEP_ID_1,
    workspace_id: uuid.UUID = WS_ID,
    workflow_template_id: uuid.UUID = TMPL_ID,
    step_order: int = 1,
    title: str = "Initial Contact",
    description: str | None = None,
    owner_role: str = "member",
    estimated_hours: Decimal = Decimal("2.0"),
    required: bool = True,
) -> MagicMock:
    s = MagicMock()
    s.id = id
    s.tenant_id = ORG_ID
    s.workspace_id = workspace_id
    s.workflow_template_id = workflow_template_id
    s.step_order = step_order
    s.title = title
    s.description = description
    s.owner_role = owner_role
    s.estimated_hours = estimated_hours
    s.required = required
    s.created_at = NOW
    return s


def _step_out(step: MagicMock) -> WorkflowStepOut:
    return WorkflowStepOut(
        id=step.id,
        tenant_id=ORG_ID,
        workspace_id=step.workspace_id,
        workflow_template_id=step.workflow_template_id,
        step_order=step.step_order,
        title=step.title,
        description=step.description,
        owner_role=step.owner_role,
        estimated_hours=step.estimated_hours,
        required=step.required,
        created_at=step.created_at,
    )


def _template_out(t: MagicMock) -> WorkflowTemplateOut:
    return WorkflowTemplateOut(
        id=t.id,
        tenant_id=ORG_ID,
        workspace_id=t.workspace_id,
        name=t.name,
        description=t.description,
        category=t.category,
        is_active=t.is_active,
        created_by=t.created_by,
        created_at=t.created_at,
        steps=[_step_out(s) for s in t.steps],
    )


@contextmanager
def _patch(ctx: MagicMock, redis: MagicMock):
    with (
        patch("corpmind.modules.workflows.service.get_tenant_context", return_value=ctx),
        patch("corpmind.modules.workflows.repo.get_tenant_context", return_value=ctx),
        patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
    ):
        yield


def _make_svc(
    template_repo: MagicMock | None = None,
    step_repo: MagicMock | None = None,
) -> tuple[WorkflowService, MagicMock, MagicMock]:
    session = MagicMock()
    svc = WorkflowService(session)
    if template_repo is not None:
        svc._template_repo = template_repo
    if step_repo is not None:
        svc._step_repo = step_repo
    return svc, svc._template_repo, svc._step_repo


# ── Cache key tests ────────────────────────────────────────────────────────────

class TestCacheKeys:
    def test_list_key_format(self):
        key = _list_key(ORG_ID, WS_ID)
        assert key.startswith(f"t:{ORG_ID}:{WS_ID}:")
        assert "workflow_templates:list" in key

    def test_detail_key_format(self):
        key = _detail_key(ORG_ID, TMPL_ID)
        assert str(ORG_ID) in key
        assert str(TMPL_ID) in key
        assert "detail" in key

    def test_list_key_workspace_scoped(self):
        ws2 = uuid.uuid4()
        assert _list_key(ORG_ID, WS_ID) != _list_key(ORG_ID, ws2)

    def test_detail_key_template_scoped(self):
        tmpl2 = uuid.uuid4()
        assert _detail_key(ORG_ID, TMPL_ID) != _detail_key(ORG_ID, tmpl2)


# ── Schema validation tests ────────────────────────────────────────────────────

class TestSchemaValidation:
    def test_template_in_valid(self):
        d = WorkflowTemplateIn(
            workspace_id=WS_ID,
            name="Enterprise Sales",
            category="enterprise_sales",
        )
        assert d.name == "Enterprise Sales"

    def test_template_in_invalid_category(self):
        with pytest.raises(Exception):
            WorkflowTemplateIn(
                workspace_id=WS_ID,
                name="X",
                category="invalid_category",
            )

    def test_template_in_empty_name(self):
        with pytest.raises(Exception):
            WorkflowTemplateIn(workspace_id=WS_ID, name="  ", category="other")

    def test_template_in_name_too_long(self):
        with pytest.raises(Exception):
            WorkflowTemplateIn(workspace_id=WS_ID, name="x" * 256, category="other")

    def test_step_in_valid(self):
        s = WorkflowStepIn(title="Step 1", owner_role="admin", estimated_hours=Decimal("1.5"))
        assert s.owner_role == "admin"

    def test_step_in_invalid_owner_role(self):
        with pytest.raises(Exception):
            WorkflowStepIn(title="Step", owner_role="superuser")

    def test_step_in_negative_hours(self):
        with pytest.raises(Exception):
            WorkflowStepIn(title="Step", estimated_hours=Decimal("-1"))

    def test_step_in_empty_title(self):
        with pytest.raises(Exception):
            WorkflowStepIn(title="   ")

    def test_step_in_title_too_long(self):
        with pytest.raises(Exception):
            WorkflowStepIn(title="x" * 256)

    def test_step_in_zero_hours_ok(self):
        s = WorkflowStepIn(title="Step", estimated_hours=Decimal("0"))
        assert s.estimated_hours == Decimal("0")

    def test_template_update_partial(self):
        u = WorkflowTemplateUpdate(name="Updated")
        assert u.name == "Updated"
        assert u.category is None

    def test_template_update_invalid_category(self):
        with pytest.raises(Exception):
            WorkflowTemplateUpdate(category="bad")

    def test_step_update_partial(self):
        u = WorkflowStepUpdate(owner_role="owner")
        assert u.owner_role == "owner"
        assert u.title is None

    def test_step_update_negative_hours(self):
        with pytest.raises(Exception):
            WorkflowStepUpdate(estimated_hours=Decimal("-5"))

    def test_all_valid_categories(self):
        for cat in [
            "new_corporate_lead", "proposal_review", "enterprise_sales",
            "training_delivery", "customer_followup", "renewal_process",
            "onboarding", "other",
        ]:
            d = WorkflowTemplateIn(workspace_id=WS_ID, name="T", category=cat)
            assert d.category == cat

    def test_all_valid_owner_roles(self):
        for role in ["owner", "admin", "member", "viewer"]:
            s = WorkflowStepIn(title="S", owner_role=role)
            assert s.owner_role == role


# ── Permission tests ───────────────────────────────────────────────────────────

class TestPermissions:
    @pytest.mark.asyncio
    async def test_member_cannot_create(self):
        ctx = _make_ctx(role="member")
        redis = _make_redis()
        svc, _, _ = _make_svc()
        data = WorkflowTemplateIn(workspace_id=WS_ID, name="X", category="other")
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.create_template(data)

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self):
        ctx = _make_ctx(role="viewer")
        redis = _make_redis()
        svc, _, _ = _make_svc()
        data = WorkflowTemplateIn(workspace_id=WS_ID, name="X", category="other")
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.create_template(data)

    @pytest.mark.asyncio
    async def test_owner_can_create(self):
        ctx = _make_ctx(role="owner")
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.create = AsyncMock(return_value=tmpl)
        svc, _, _ = _make_svc(template_repo=template_repo)
        data = WorkflowTemplateIn(workspace_id=WS_ID, name="X", category="other")
        with _patch(ctx, redis):
            result = await svc.create_template(data)
        # service creates its own UUID; assert type and key fields
        assert isinstance(result, WorkflowTemplateOut)
        assert result.name == "X"
        assert result.category == "other"

    @pytest.mark.asyncio
    async def test_admin_can_delete(self):
        ctx = _make_ctx(role="admin")
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        template_repo.delete_by_id = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            await svc.delete_template(TMPL_ID)
        template_repo.delete_by_id.assert_awaited_once_with(TMPL_ID)

    @pytest.mark.asyncio
    async def test_member_cannot_delete(self):
        ctx = _make_ctx(role="member")
        redis = _make_redis()
        svc, _, _ = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.delete_template(TMPL_ID)

    @pytest.mark.asyncio
    async def test_viewer_cannot_add_step(self):
        ctx = _make_ctx(role="viewer")
        redis = _make_redis()
        svc, _, _ = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.add_step(TMPL_ID, WorkflowStepIn(title="S"))

    @pytest.mark.asyncio
    async def test_member_cannot_reorder(self):
        ctx = _make_ctx(role="member")
        redis = _make_redis()
        svc, _, _ = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.reorder_steps(TMPL_ID, ReorderStepsIn(step_ids=[STEP_ID_1]))


# ── create_template tests ──────────────────────────────────────────────────────

class TestCreateTemplate:
    @pytest.mark.asyncio
    async def test_create_returns_out(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.create = AsyncMock(return_value=tmpl)
        svc, _, _ = _make_svc(template_repo=template_repo)
        data = WorkflowTemplateIn(workspace_id=WS_ID, name="New Corporate Lead", category="new_corporate_lead")
        with _patch(ctx, redis):
            result = await svc.create_template(data)
        assert isinstance(result, WorkflowTemplateOut)
        assert result.name == "New Corporate Lead"

    @pytest.mark.asyncio
    async def test_create_invalidates_list_cache(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.create = AsyncMock(return_value=tmpl)
        svc, _, _ = _make_svc(template_repo=template_repo)
        data = WorkflowTemplateIn(workspace_id=WS_ID, name="T", category="other")
        with _patch(ctx, redis):
            await svc.create_template(data)
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_sets_created_by_from_ctx(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template(created_by=USER_ID)
        template_repo = MagicMock()
        template_repo.create = AsyncMock(return_value=tmpl)
        svc, _, _ = _make_svc(template_repo=template_repo)
        data = WorkflowTemplateIn(workspace_id=WS_ID, name="T", category="other")
        with _patch(ctx, redis):
            result = await svc.create_template(data)
        assert result.created_by == USER_ID


# ── get_template tests ─────────────────────────────────────────────────────────

class TestGetTemplate:
    @pytest.mark.asyncio
    async def test_get_cache_hit(self):
        ctx = _make_ctx()
        tmpl_out = _template_out(_template())
        redis = _make_redis(cached_value=tmpl_out.model_dump_json())
        svc, template_repo, _ = _make_svc()
        template_repo.find_by_id = AsyncMock()
        with _patch(ctx, redis):
            result = await svc.get_template(TMPL_ID)
        template_repo.find_by_id.assert_not_awaited()
        assert result.id == TMPL_ID

    @pytest.mark.asyncio
    async def test_get_cache_miss_hits_db(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            result = await svc.get_template(TMPL_ID)
        template_repo.find_by_id.assert_awaited_once_with(TMPL_ID)
        assert result.name == "New Corporate Lead"

    @pytest.mark.asyncio
    async def test_get_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        ctx = _make_ctx()
        redis = _make_redis()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=None)
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.get_template(TMPL_ID)

    @pytest.mark.asyncio
    async def test_get_cache_miss_stores_result(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            await svc.get_template(TMPL_ID)
        redis.set.assert_awaited()


# ── update_template tests ──────────────────────────────────────────────────────

class TestUpdateTemplate:
    @pytest.mark.asyncio
    async def test_update_name(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        template_repo.update_fields = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            result = await svc.update_template(TMPL_ID, WorkflowTemplateUpdate(name="Updated Name"))
        assert result.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_is_active(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template(is_active=True)
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        template_repo.update_fields = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            result = await svc.update_template(TMPL_ID, WorkflowTemplateUpdate(is_active=False))
        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        ctx = _make_ctx()
        redis = _make_redis()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=None)
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update_template(TMPL_ID, WorkflowTemplateUpdate(name="X"))

    @pytest.mark.asyncio
    async def test_update_invalidates_list_and_detail_cache(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        template_repo.update_fields = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            await svc.update_template(TMPL_ID, WorkflowTemplateUpdate(name="X"))
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_no_fields_is_noop(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        template_repo.update_fields = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            await svc.update_template(TMPL_ID, WorkflowTemplateUpdate())
        template_repo.update_fields.assert_not_awaited()


# ── delete_template tests ──────────────────────────────────────────────────────

class TestDeleteTemplate:
    @pytest.mark.asyncio
    async def test_delete_calls_repo(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        template_repo.delete_by_id = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            await svc.delete_template(TMPL_ID)
        template_repo.delete_by_id.assert_awaited_once_with(TMPL_ID)

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        ctx = _make_ctx()
        redis = _make_redis()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=None)
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.delete_template(TMPL_ID)

    @pytest.mark.asyncio
    async def test_delete_invalidates_cache(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        template_repo.delete_by_id = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            await svc.delete_template(TMPL_ID)
        redis.delete.assert_awaited()


# ── duplicate_template tests ───────────────────────────────────────────────────

class TestDuplicateTemplate:
    @pytest.mark.asyncio
    async def test_duplicate_creates_new_template(self):
        ctx = _make_ctx()
        redis = _make_redis()
        source = _template(steps=[_step()])
        new_tmpl = _template(id=TMPL_ID_2, name="Copy of New Corporate Lead")
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(side_effect=[source, new_tmpl])
        template_repo.create = AsyncMock(return_value=new_tmpl)
        step_repo = MagicMock()
        step_repo.find_by_template = AsyncMock(return_value=[_step()])
        step_repo.create = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo, step_repo=step_repo)
        with _patch(ctx, redis):
            result = await svc.duplicate_template(TMPL_ID, WS_ID)
        assert result.name == "Copy of New Corporate Lead"

    @pytest.mark.asyncio
    async def test_duplicate_copies_steps(self):
        ctx = _make_ctx()
        redis = _make_redis()
        source = _template(steps=[_step(id=STEP_ID_1, step_order=1), _step(id=STEP_ID_2, step_order=2)])
        new_tmpl = _template(id=TMPL_ID_2)
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(side_effect=[source, new_tmpl])
        template_repo.create = AsyncMock(return_value=new_tmpl)
        step_repo = MagicMock()
        captured: list[Any] = []

        async def _capture_create(step: Any) -> Any:
            captured.append(step)
            return step

        step_repo.find_by_template = AsyncMock(return_value=[_step(id=STEP_ID_1, step_order=1), _step(id=STEP_ID_2, step_order=2)])
        step_repo.create = _capture_create
        svc, _, _ = _make_svc(template_repo=template_repo, step_repo=step_repo)
        with _patch(ctx, redis):
            await svc.duplicate_template(TMPL_ID, WS_ID)
        assert len(captured) == 2

    @pytest.mark.asyncio
    async def test_duplicate_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        ctx = _make_ctx()
        redis = _make_redis()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=None)
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.duplicate_template(TMPL_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_duplicate_member_denied(self):
        ctx = _make_ctx(role="member")
        redis = _make_redis()
        svc, _, _ = _make_svc()
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.duplicate_template(TMPL_ID, WS_ID)


# ── list_templates tests ───────────────────────────────────────────────────────

class TestListTemplates:
    @pytest.mark.asyncio
    async def test_list_cache_hit(self):
        ctx = _make_ctx()
        page = WorkflowTemplateListPage(items=[], next_cursor=None, has_more=False)
        redis = _make_redis(cached_value=page.model_dump_json())
        template_repo = MagicMock()
        template_repo.list_page = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            result = await svc.list_templates(WS_ID)
        template_repo.list_page.assert_not_awaited()
        assert result.items == []

    @pytest.mark.asyncio
    async def test_list_cache_miss_hits_db(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.list_page = AsyncMock(return_value=([tmpl], None))
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            result = await svc.list_templates(WS_ID)
        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_list_with_filter_skips_cache(self):
        ctx = _make_ctx()
        redis = _make_redis()
        template_repo = MagicMock()
        template_repo.list_page = AsyncMock(return_value=([], None))
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            await svc.list_templates(WS_ID, category="other")
        redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_has_more_flag(self):
        ctx = _make_ctx()
        redis = _make_redis()
        raw = f"{NOW.isoformat()}|{TMPL_ID}"
        cursor = base64.b64encode(raw.encode()).decode()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.list_page = AsyncMock(return_value=([tmpl], cursor))
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            result = await svc.list_templates(WS_ID)
        assert result.has_more is True
        assert result.next_cursor == cursor

    @pytest.mark.asyncio
    async def test_list_empty_result(self):
        ctx = _make_ctx()
        redis = _make_redis()
        template_repo = MagicMock()
        template_repo.list_page = AsyncMock(return_value=([], None))
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            result = await svc.list_templates(WS_ID)
        assert result.items == []
        assert result.has_more is False


# ── add_step tests ─────────────────────────────────────────────────────────────

class TestAddStep:
    @pytest.mark.asyncio
    async def test_add_step_returns_out(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        step = _step()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        step_repo = MagicMock()
        step_repo.max_step_order = AsyncMock(return_value=0)
        step_repo.create = AsyncMock(return_value=step)
        svc, _, _ = _make_svc(template_repo=template_repo, step_repo=step_repo)
        data = WorkflowStepIn(title="Initial Contact")
        with _patch(ctx, redis):
            result = await svc.add_step(TMPL_ID, data)
        assert isinstance(result, WorkflowStepOut)

    @pytest.mark.asyncio
    async def test_add_step_increments_order(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        step_repo = MagicMock()
        step_repo.max_step_order = AsyncMock(return_value=3)
        captured: list[Any] = []

        async def _cap(step: Any) -> Any:
            captured.append(step)
            return step

        step_repo.create = _cap
        svc, _, _ = _make_svc(template_repo=template_repo, step_repo=step_repo)
        with _patch(ctx, redis):
            await svc.add_step(TMPL_ID, WorkflowStepIn(title="Step 4"))
        assert captured[0].step_order == 4

    @pytest.mark.asyncio
    async def test_add_step_template_not_found(self):
        from corpmind.core.exceptions import NotFoundError
        ctx = _make_ctx()
        redis = _make_redis()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=None)
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.add_step(TMPL_ID, WorkflowStepIn(title="S"))

    @pytest.mark.asyncio
    async def test_add_step_invalidates_cache(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        step = _step()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        step_repo = MagicMock()
        step_repo.max_step_order = AsyncMock(return_value=0)
        step_repo.create = AsyncMock(return_value=step)
        svc, _, _ = _make_svc(template_repo=template_repo, step_repo=step_repo)
        with _patch(ctx, redis):
            await svc.add_step(TMPL_ID, WorkflowStepIn(title="S"))
        redis.delete.assert_awaited()


# ── update_step tests ──────────────────────────────────────────────────────────

class TestUpdateStep:
    @pytest.mark.asyncio
    async def test_update_step_title(self):
        ctx = _make_ctx()
        redis = _make_redis()
        step = _step(title="Old")
        step_repo = MagicMock()
        step_repo.find_by_id = AsyncMock(return_value=step)
        step_repo.update_fields = AsyncMock()
        svc, _, _ = _make_svc(step_repo=step_repo)
        with _patch(ctx, redis):
            result = await svc.update_step(STEP_ID_1, WorkflowStepUpdate(title="New"))
        assert result.title == "New"

    @pytest.mark.asyncio
    async def test_update_step_not_found(self):
        from corpmind.core.exceptions import NotFoundError
        ctx = _make_ctx()
        redis = _make_redis()
        step_repo = MagicMock()
        step_repo.find_by_id = AsyncMock(return_value=None)
        svc, _, _ = _make_svc(step_repo=step_repo)
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update_step(STEP_ID_1, WorkflowStepUpdate(title="X"))

    @pytest.mark.asyncio
    async def test_update_step_no_fields_noop(self):
        ctx = _make_ctx()
        redis = _make_redis()
        step = _step()
        step_repo = MagicMock()
        step_repo.find_by_id = AsyncMock(return_value=step)
        step_repo.update_fields = AsyncMock()
        svc, _, _ = _make_svc(step_repo=step_repo)
        with _patch(ctx, redis):
            await svc.update_step(STEP_ID_1, WorkflowStepUpdate())
        step_repo.update_fields.assert_not_awaited()


# ── delete_step tests ──────────────────────────────────────────────────────────

class TestDeleteStep:
    @pytest.mark.asyncio
    async def test_delete_step_calls_repo(self):
        ctx = _make_ctx()
        redis = _make_redis()
        step = _step()
        step_repo = MagicMock()
        step_repo.find_by_id = AsyncMock(return_value=step)
        step_repo.delete_by_id = AsyncMock()
        svc, _, _ = _make_svc(step_repo=step_repo)
        with _patch(ctx, redis):
            await svc.delete_step(STEP_ID_1)
        step_repo.delete_by_id.assert_awaited_once_with(STEP_ID_1)

    @pytest.mark.asyncio
    async def test_delete_step_not_found(self):
        from corpmind.core.exceptions import NotFoundError
        ctx = _make_ctx()
        redis = _make_redis()
        step_repo = MagicMock()
        step_repo.find_by_id = AsyncMock(return_value=None)
        svc, _, _ = _make_svc(step_repo=step_repo)
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.delete_step(STEP_ID_1)

    @pytest.mark.asyncio
    async def test_delete_step_invalidates_cache(self):
        ctx = _make_ctx()
        redis = _make_redis()
        step = _step()
        step_repo = MagicMock()
        step_repo.find_by_id = AsyncMock(return_value=step)
        step_repo.delete_by_id = AsyncMock()
        svc, _, _ = _make_svc(step_repo=step_repo)
        with _patch(ctx, redis):
            await svc.delete_step(STEP_ID_1)
        redis.delete.assert_awaited()


# ── reorder_steps tests ────────────────────────────────────────────────────────

class TestReorderSteps:
    @pytest.mark.asyncio
    async def test_reorder_valid(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        s1 = _step(id=STEP_ID_1, step_order=1)
        s2 = _step(id=STEP_ID_2, step_order=2)
        s3 = _step(id=STEP_ID_3, step_order=3)
        new_tmpl = _template(steps=[s2, s1, s3])
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(side_effect=[tmpl, new_tmpl])
        step_repo = MagicMock()
        step_repo.find_by_template = AsyncMock(return_value=[s1, s2, s3])
        step_repo.bulk_update_order = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo, step_repo=step_repo)
        with _patch(ctx, redis):
            result = await svc.reorder_steps(
                TMPL_ID,
                ReorderStepsIn(step_ids=[STEP_ID_2, STEP_ID_1, STEP_ID_3]),
            )
        step_repo.bulk_update_order.assert_awaited_once_with(
            [(STEP_ID_2, 1), (STEP_ID_1, 2), (STEP_ID_3, 3)]
        )

    @pytest.mark.asyncio
    async def test_reorder_missing_step_raises_conflict(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        s1 = _step(id=STEP_ID_1)
        s2 = _step(id=STEP_ID_2)
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        step_repo = MagicMock()
        step_repo.find_by_template = AsyncMock(return_value=[s1, s2])
        svc, _, _ = _make_svc(template_repo=template_repo, step_repo=step_repo)
        # Only send one step_id when there are two
        with _patch(ctx, redis):
            with pytest.raises(StepOrderConflictError):
                await svc.reorder_steps(TMPL_ID, ReorderStepsIn(step_ids=[STEP_ID_1]))

    @pytest.mark.asyncio
    async def test_reorder_extra_step_raises_conflict(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        s1 = _step(id=STEP_ID_1)
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        step_repo = MagicMock()
        step_repo.find_by_template = AsyncMock(return_value=[s1])
        svc, _, _ = _make_svc(template_repo=template_repo, step_repo=step_repo)
        with _patch(ctx, redis):
            with pytest.raises(StepOrderConflictError):
                await svc.reorder_steps(TMPL_ID, ReorderStepsIn(step_ids=[STEP_ID_1, STEP_ID_2]))

    @pytest.mark.asyncio
    async def test_reorder_template_not_found(self):
        from corpmind.core.exceptions import NotFoundError
        ctx = _make_ctx()
        redis = _make_redis()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=None)
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.reorder_steps(TMPL_ID, ReorderStepsIn(step_ids=[STEP_ID_1]))

    @pytest.mark.asyncio
    async def test_reorder_invalidates_cache(self):
        ctx = _make_ctx()
        redis = _make_redis()
        tmpl = _template()
        s1 = _step(id=STEP_ID_1)
        new_tmpl = _template(steps=[s1])
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(side_effect=[tmpl, new_tmpl])
        step_repo = MagicMock()
        step_repo.find_by_template = AsyncMock(return_value=[s1])
        step_repo.bulk_update_order = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo, step_repo=step_repo)
        with _patch(ctx, redis):
            await svc.reorder_steps(TMPL_ID, ReorderStepsIn(step_ids=[STEP_ID_1]))
        redis.delete.assert_awaited()


# ── Cache resilience tests ─────────────────────────────────────────────────────

class TestCacheResilience:
    @pytest.mark.asyncio
    async def test_get_template_redis_error_falls_through(self):
        ctx = _make_ctx()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("Redis down"))
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            result = await svc.get_template(TMPL_ID)
        assert result.id == TMPL_ID

    @pytest.mark.asyncio
    async def test_list_templates_redis_error_falls_through(self):
        ctx = _make_ctx()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("Redis down"))
        template_repo = MagicMock()
        template_repo.list_page = AsyncMock(return_value=([], None))
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            result = await svc.list_templates(WS_ID)
        assert result.items == []

    @pytest.mark.asyncio
    async def test_invalidate_redis_error_does_not_raise(self):
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("Redis down"))
        tmpl = _template()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=tmpl)
        template_repo.delete_by_id = AsyncMock()
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            await svc.delete_template(TMPL_ID)  # should not raise


# ── Tenant isolation tests ─────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_get_uses_tenant_id_from_ctx(self):
        ctx = _make_ctx()
        redis = _make_redis()
        template_repo = MagicMock()
        template_repo.find_by_id = AsyncMock(return_value=None)
        svc, _, _ = _make_svc(template_repo=template_repo)
        with _patch(ctx, redis):
            from corpmind.core.exceptions import NotFoundError
            with pytest.raises(NotFoundError):
                await svc.get_template(TMPL_ID)
        # repo was queried (tenant filtering is in repo.find_by_id via ctx)
        template_repo.find_by_id.assert_awaited_once_with(TMPL_ID)

    @pytest.mark.asyncio
    async def test_different_org_gets_separate_cache_keys(self):
        org2 = uuid.uuid4()
        ctx1 = _make_ctx()
        ctx2 = _make_ctx()
        ctx2.org_id = org2
        key1 = _list_key(ctx1.org_id, WS_ID)
        key2 = _list_key(ctx2.org_id, WS_ID)
        assert key1 != key2
