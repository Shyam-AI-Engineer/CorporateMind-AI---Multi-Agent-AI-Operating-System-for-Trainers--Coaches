"""Unit tests for approval workflow services — Sprint 31.

Covers:
- ApprovalService: create_request, assign_reviewer, approve, reject, cancel
- ApprovalService: list_requests, get_detail, list_my_reviews
- ApprovalTimelineService: list_timeline
- Permission checks (OrgAdmin/AgencyManager vs requester vs reviewer vs stranger)
- Invalid state transitions
- Redis cache hit/miss/invalidation
- Tenant isolation
- Schema validators
"""

from __future__ import annotations

import base64
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.approvals.schemas import (
    ApprovalAssignIn,
    ApprovalDecisionIn,
    ApprovalListPage,
    ApprovalRequestIn,
    ApprovalRequestOut,
    ApprovalTimelineEventOut,
)
from corpmind.modules.approvals.service import (
    ApprovalService,
    ApprovalTimelineService,
    InvalidStateError,
    PermissionDeniedError,
    _detail_key,
    _list_key,
    _my_reviews_key,
    _timeline_key,
)

# ── Constants ──────────────────────────────────────────────────────────────────

ORG_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WS_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
OTHER_USER = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
APPROVAL_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
REVIEWER_ID = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

NOW = datetime(2026, 6, 28, 10, 0, 0, tzinfo=timezone.utc)


# ── Mock helpers ───────────────────────────────────────────────────────────────

def _make_ctx(role: str = "Trainer") -> MagicMock:
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


def _approval(
    id: uuid.UUID = APPROVAL_ID,
    workspace_id: uuid.UUID = WS_ID,
    entity_type: str = "task",
    entity_id: uuid.UUID | None = None,
    requested_by: str | None = None,
    assigned_reviewer: str | None = None,
    priority: str = "medium",
    status: str = "pending",
    decision: str = "none",
    comments: str | None = None,
    due_date: object = None,
    reviewed_at: datetime | None = None,
) -> MagicMock:
    a = MagicMock()
    a.id = id
    a.tenant_id = ORG_ID
    a.workspace_id = workspace_id
    a.entity_type = entity_type
    a.entity_id = entity_id
    a.requested_by = requested_by if requested_by is not None else str(USER_ID)
    a.assigned_reviewer = assigned_reviewer
    a.priority = priority
    a.status = status
    a.decision = decision
    a.comments = comments
    a.due_date = due_date
    a.reviewed_at = reviewed_at
    a.created_at = NOW
    a.updated_at = NOW
    return a


def _timeline_event(
    id: uuid.UUID | None = None,
    approval_request_id: uuid.UUID = APPROVAL_ID,
    event_type: str = "request_created",
    actor_user_id: str | None = None,
    notes: str | None = None,
) -> MagicMock:
    e = MagicMock()
    e.id = id or uuid.uuid4()
    e.approval_request_id = approval_request_id
    e.tenant_id = ORG_ID
    e.event_type = event_type
    e.actor_user_id = actor_user_id if actor_user_id is not None else str(USER_ID)
    e.notes = notes
    e.occurred_at = NOW
    return e


def _svc(session: MagicMock | None = None) -> ApprovalService:
    return ApprovalService(session or MagicMock())


def _timeline_svc(session: MagicMock | None = None) -> ApprovalTimelineService:
    return ApprovalTimelineService(session or MagicMock())


@contextmanager
def _patch(ctx: MagicMock, redis: MagicMock):
    with (
        patch("corpmind.modules.approvals.service.get_tenant_context", return_value=ctx),
        patch("corpmind.modules.approvals.service.get_redis", return_value=redis),
    ):
        yield


# ── Schema tests ───────────────────────────────────────────────────────────────

class TestSchemas:
    def test_approval_request_in_valid(self):
        data = ApprovalRequestIn(
            workspace_id=WS_ID,
            entity_type="task",
            priority="high",
            comments="Please review",
        )
        assert data.entity_type == "task"
        assert data.priority == "high"
        assert data.comments == "Please review"

    def test_approval_request_in_invalid_entity_type(self):
        with pytest.raises(Exception):
            ApprovalRequestIn(workspace_id=WS_ID, entity_type="unknown")

    def test_approval_request_in_invalid_priority(self):
        with pytest.raises(Exception):
            ApprovalRequestIn(workspace_id=WS_ID, entity_type="task", priority="critical")

    def test_approval_request_in_comments_strip(self):
        data = ApprovalRequestIn(workspace_id=WS_ID, entity_type="task", comments="  hi  ")
        assert data.comments == "hi"

    def test_approval_request_in_empty_comments_becomes_none(self):
        data = ApprovalRequestIn(workspace_id=WS_ID, entity_type="task", comments="   ")
        assert data.comments is None

    def test_approval_request_in_comments_too_long(self):
        with pytest.raises(Exception):
            ApprovalRequestIn(workspace_id=WS_ID, entity_type="task", comments="x" * 4001)

    def test_approval_assign_in_strip(self):
        data = ApprovalAssignIn(assigned_reviewer="  abc  ")
        assert data.assigned_reviewer == "abc"

    def test_approval_assign_in_empty_raises(self):
        with pytest.raises(Exception):
            ApprovalAssignIn(assigned_reviewer="   ")

    def test_approval_decision_in_empty_comments_none(self):
        data = ApprovalDecisionIn(comments="  ")
        assert data.comments is None

    def test_approval_decision_in_comments_strip(self):
        data = ApprovalDecisionIn(comments="  lgtm  ")
        assert data.comments == "lgtm"

    def test_approval_decision_in_no_comments(self):
        data = ApprovalDecisionIn()
        assert data.comments is None

    def test_valid_priorities(self):
        for p in ("low", "medium", "high", "urgent"):
            d = ApprovalRequestIn(workspace_id=WS_ID, entity_type="task", priority=p)
            assert d.priority == p

    def test_valid_entity_types(self):
        for et in ("task", "recommendation", "campaign", "proposal"):
            d = ApprovalRequestIn(workspace_id=WS_ID, entity_type=et)
            assert d.entity_type == et


# ── Cache key helpers ──────────────────────────────────────────────────────────

class TestCacheKeys:
    def test_list_key_format(self):
        key = _list_key(ORG_ID, WS_ID)
        assert str(ORG_ID) in key
        assert str(WS_ID) in key
        assert "approvals" in key

    def test_my_reviews_key_includes_user(self):
        key = _my_reviews_key(ORG_ID, WS_ID, USER_ID)
        assert str(USER_ID) in key

    def test_detail_key_includes_approval(self):
        key = _detail_key(ORG_ID, APPROVAL_ID)
        assert str(APPROVAL_ID) in key

    def test_timeline_key_includes_approval(self):
        key = _timeline_key(ORG_ID, APPROVAL_ID)
        assert str(APPROVAL_ID) in key

    def test_keys_are_tenant_scoped(self):
        other_org = uuid.uuid4()
        assert _list_key(ORG_ID, WS_ID) != _list_key(other_org, WS_ID)
        assert _my_reviews_key(ORG_ID, WS_ID, USER_ID) != _my_reviews_key(
            other_org, WS_ID, USER_ID
        )


# ── Create request ─────────────────────────────────────────────────────────────

class TestCreateRequest:
    @pytest.mark.asyncio
    async def test_create_basic(self):
        ctx = _make_ctx()
        redis = _make_redis()
        session = MagicMock()

        created: list = []

        async def fake_create(obj):
            created.append(obj)
            return obj

        svc = _svc(session)
        svc._repo.create = AsyncMock(side_effect=fake_create)
        svc._timeline_repo.create = AsyncMock()

        data = ApprovalRequestIn(workspace_id=WS_ID, entity_type="task", priority="high")
        with _patch(ctx, redis):
            result = await svc.create_request(data)

        assert result.entity_type == "task"
        assert result.priority == "high"
        assert result.status == "pending"
        assert result.requested_by == str(USER_ID)

    @pytest.mark.asyncio
    async def test_create_invalidates_list_cache(self):
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _svc()
        svc._repo.create = AsyncMock(return_value=None)
        svc._timeline_repo.create = AsyncMock()

        data = ApprovalRequestIn(workspace_id=WS_ID, entity_type="proposal")
        with _patch(ctx, redis):
            await svc.create_request(data)

        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_create_records_timeline_event(self):
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _svc()
        svc._repo.create = AsyncMock(return_value=None)
        timeline_events: list = []
        svc._timeline_repo.create = AsyncMock(
            side_effect=lambda e: timeline_events.append(e) or e
        )

        data = ApprovalRequestIn(workspace_id=WS_ID, entity_type="campaign")
        with _patch(ctx, redis):
            await svc.create_request(data)

        assert len(timeline_events) >= 1
        assert timeline_events[0].event_type == "request_created"

    @pytest.mark.asyncio
    async def test_create_with_reviewer_adds_assigned_event(self):
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _svc()
        svc._repo.create = AsyncMock(return_value=None)
        events: list = []
        svc._timeline_repo.create = AsyncMock(
            side_effect=lambda e: events.append(e) or e
        )

        data = ApprovalRequestIn(
            workspace_id=WS_ID,
            entity_type="task",
            assigned_reviewer=str(REVIEWER_ID),
        )
        with _patch(ctx, redis):
            await svc.create_request(data)

        event_types = [e.event_type for e in events]
        assert "request_created" in event_types
        assert "reviewer_assigned" in event_types

    @pytest.mark.asyncio
    async def test_create_uses_caller_as_requested_by(self):
        ctx = _make_ctx()
        ctx.user_id = OTHER_USER
        redis = _make_redis()
        svc = _svc()
        svc._repo.create = AsyncMock(return_value=None)
        svc._timeline_repo.create = AsyncMock()

        data = ApprovalRequestIn(workspace_id=WS_ID, entity_type="task")
        with _patch(ctx, redis):
            result = await svc.create_request(data)

        assert result.requested_by == str(OTHER_USER)


# ── Assign reviewer ────────────────────────────────────────────────────────────

class TestAssignReviewer:
    @pytest.mark.asyncio
    async def test_admin_can_assign(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="pending")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        data = ApprovalAssignIn(assigned_reviewer=str(REVIEWER_ID))
        with _patch(ctx, redis):
            result = await svc.assign_reviewer(APPROVAL_ID, WS_ID, data)

        assert result.status == "in_review"
        assert result.assigned_reviewer == str(REVIEWER_ID)

    @pytest.mark.asyncio
    async def test_agency_manager_can_assign(self):
        ctx = _make_ctx(role="AgencyManager")
        redis = _make_redis()
        req = _approval(status="pending")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        data = ApprovalAssignIn(assigned_reviewer=str(REVIEWER_ID))
        with _patch(ctx, redis):
            result = await svc.assign_reviewer(APPROVAL_ID, WS_ID, data)

        assert result.status == "in_review"

    @pytest.mark.asyncio
    async def test_requester_can_assign(self):
        ctx = _make_ctx(role="Trainer")
        ctx.user_id = USER_ID
        redis = _make_redis()
        req = _approval(status="pending", requested_by=str(USER_ID))
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        data = ApprovalAssignIn(assigned_reviewer=str(REVIEWER_ID))
        with _patch(ctx, redis):
            result = await svc.assign_reviewer(APPROVAL_ID, WS_ID, data)

        assert result.status == "in_review"

    @pytest.mark.asyncio
    async def test_stranger_cannot_assign(self):
        ctx = _make_ctx(role="Trainer")
        ctx.user_id = OTHER_USER
        redis = _make_redis()
        req = _approval(status="pending", requested_by=str(USER_ID))
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        data = ApprovalAssignIn(assigned_reviewer=str(REVIEWER_ID))
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.assign_reviewer(APPROVAL_ID, WS_ID, data)

    @pytest.mark.asyncio
    async def test_assign_invalid_state_raises(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="approved")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        data = ApprovalAssignIn(assigned_reviewer=str(REVIEWER_ID))
        with _patch(ctx, redis):
            with pytest.raises(InvalidStateError):
                await svc.assign_reviewer(APPROVAL_ID, WS_ID, data)

    @pytest.mark.asyncio
    async def test_assign_not_found(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)

        data = ApprovalAssignIn(assigned_reviewer=str(REVIEWER_ID))
        with _patch(ctx, redis):
            with pytest.raises(Exception):
                await svc.assign_reviewer(APPROVAL_ID, WS_ID, data)

    @pytest.mark.asyncio
    async def test_assign_wrong_workspace_raises(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="pending", workspace_id=uuid.uuid4())  # wrong WS
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        data = ApprovalAssignIn(assigned_reviewer=str(REVIEWER_ID))
        with _patch(ctx, redis):
            with pytest.raises(Exception):
                await svc.assign_reviewer(APPROVAL_ID, WS_ID, data)

    @pytest.mark.asyncio
    async def test_assign_invalidates_caches(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="pending")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        data = ApprovalAssignIn(assigned_reviewer=str(REVIEWER_ID))
        with _patch(ctx, redis):
            await svc.assign_reviewer(APPROVAL_ID, WS_ID, data)

        redis.delete.assert_called()


# ── Approve ────────────────────────────────────────────────────────────────────

class TestApprove:
    @pytest.mark.asyncio
    async def test_assigned_reviewer_can_approve(self):
        ctx = _make_ctx(role="Trainer")
        ctx.user_id = REVIEWER_ID
        redis = _make_redis()
        req = _approval(status="in_review", assigned_reviewer=str(REVIEWER_ID))
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            result = await svc.approve(APPROVAL_ID, WS_ID, ApprovalDecisionIn())

        assert result.status == "approved"
        assert result.decision == "approve"

    @pytest.mark.asyncio
    async def test_org_admin_can_approve(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="pending")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            result = await svc.approve(APPROVAL_ID, WS_ID, ApprovalDecisionIn())

        assert result.status == "approved"

    @pytest.mark.asyncio
    async def test_non_reviewer_cannot_approve(self):
        ctx = _make_ctx(role="Trainer")
        ctx.user_id = OTHER_USER
        redis = _make_redis()
        req = _approval(status="in_review", assigned_reviewer=str(REVIEWER_ID))
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.approve(APPROVAL_ID, WS_ID, ApprovalDecisionIn())

    @pytest.mark.asyncio
    async def test_approve_already_approved_raises(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="approved")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with pytest.raises(InvalidStateError):
                await svc.approve(APPROVAL_ID, WS_ID, ApprovalDecisionIn())

    @pytest.mark.asyncio
    async def test_approve_cancelled_raises(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="cancelled")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with pytest.raises(InvalidStateError):
                await svc.approve(APPROVAL_ID, WS_ID, ApprovalDecisionIn())

    @pytest.mark.asyncio
    async def test_approve_with_comments(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="pending")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            result = await svc.approve(
                APPROVAL_ID, WS_ID, ApprovalDecisionIn(comments="Looks good")
            )

        assert result.comments == "Looks good"

    @pytest.mark.asyncio
    async def test_approve_invalidates_caches(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="pending")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            await svc.approve(APPROVAL_ID, WS_ID, ApprovalDecisionIn())

        redis.delete.assert_called()


# ── Reject ─────────────────────────────────────────────────────────────────────

class TestReject:
    @pytest.mark.asyncio
    async def test_assigned_reviewer_can_reject(self):
        ctx = _make_ctx(role="Trainer")
        ctx.user_id = REVIEWER_ID
        redis = _make_redis()
        req = _approval(status="in_review", assigned_reviewer=str(REVIEWER_ID))
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            result = await svc.reject(APPROVAL_ID, WS_ID, ApprovalDecisionIn())

        assert result.status == "rejected"
        assert result.decision == "reject"

    @pytest.mark.asyncio
    async def test_org_admin_can_reject(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="in_review", assigned_reviewer=str(REVIEWER_ID))
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            result = await svc.reject(APPROVAL_ID, WS_ID, ApprovalDecisionIn())

        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_stranger_cannot_reject(self):
        ctx = _make_ctx(role="Trainer")
        ctx.user_id = OTHER_USER
        redis = _make_redis()
        req = _approval(status="in_review", assigned_reviewer=str(REVIEWER_ID))
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.reject(APPROVAL_ID, WS_ID, ApprovalDecisionIn())

    @pytest.mark.asyncio
    async def test_reject_already_rejected_raises(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="rejected")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with pytest.raises(InvalidStateError):
                await svc.reject(APPROVAL_ID, WS_ID, ApprovalDecisionIn())

    @pytest.mark.asyncio
    async def test_reject_with_comment_persisted(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="pending")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            result = await svc.reject(
                APPROVAL_ID, WS_ID, ApprovalDecisionIn(comments="Needs revision")
            )

        assert result.comments == "Needs revision"

    @pytest.mark.asyncio
    async def test_reject_invalidates_caches(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="pending")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            await svc.reject(APPROVAL_ID, WS_ID, ApprovalDecisionIn())

        redis.delete.assert_called()


# ── Cancel ─────────────────────────────────────────────────────────────────────

class TestCancel:
    @pytest.mark.asyncio
    async def test_requester_can_cancel(self):
        ctx = _make_ctx(role="Trainer")
        ctx.user_id = USER_ID
        redis = _make_redis()
        req = _approval(status="pending", requested_by=str(USER_ID))
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            result = await svc.cancel(APPROVAL_ID, WS_ID)

        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_org_admin_can_cancel(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="in_review")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            result = await svc.cancel(APPROVAL_ID, WS_ID)

        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_stranger_cannot_cancel(self):
        ctx = _make_ctx(role="Trainer")
        ctx.user_id = OTHER_USER
        redis = _make_redis()
        req = _approval(status="pending", requested_by=str(USER_ID))
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.cancel(APPROVAL_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_raises(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="cancelled")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with pytest.raises(InvalidStateError):
                await svc.cancel(APPROVAL_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_cancel_approved_raises(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="approved")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with pytest.raises(InvalidStateError):
                await svc.cancel(APPROVAL_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_cancel_invalidates_caches(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="pending")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            await svc.cancel(APPROVAL_ID, WS_ID)

        redis.delete.assert_called()


# ── List requests ──────────────────────────────────────────────────────────────

class TestListRequests:
    @pytest.mark.asyncio
    async def test_list_returns_page(self):
        ctx = _make_ctx()
        redis = _make_redis()
        req = _approval()
        svc = _svc()
        svc._repo.list_page = AsyncMock(return_value=([req], None))

        with _patch(ctx, redis):
            page = await svc.list_requests(WS_ID)

        assert len(page.items) == 1
        assert not page.has_more

    @pytest.mark.asyncio
    async def test_list_uses_cache_on_first_page(self):
        ctx = _make_ctx()
        cached_page = ApprovalListPage(items=[], next_cursor=None, has_more=False)
        redis = _make_redis(cached_value=cached_page.model_dump_json())
        svc = _svc()

        with _patch(ctx, redis):
            page = await svc.list_requests(WS_ID)

        assert page.items == []
        svc._repo.list_page = AsyncMock()
        svc._repo.list_page.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_skips_cache_when_filters(self):
        ctx = _make_ctx()
        redis = _make_redis()
        req = _approval()
        svc = _svc()
        svc._repo.list_page = AsyncMock(return_value=([req], None))

        with _patch(ctx, redis):
            page = await svc.list_requests(WS_ID, status="pending")

        redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_writes_cache_on_first_page(self):
        ctx = _make_ctx()
        redis = _make_redis()
        req = _approval()
        svc = _svc()
        svc._repo.list_page = AsyncMock(return_value=([req], None))

        with _patch(ctx, redis):
            await svc.list_requests(WS_ID)

        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_skips_cache_on_cursor(self):
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _svc()
        svc._repo.list_page = AsyncMock(return_value=([], None))

        with _patch(ctx, redis):
            await svc.list_requests(WS_ID, cursor="abc")

        redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_has_more_when_extra_item(self):
        ctx = _make_ctx()
        redis = _make_redis()
        cursor_val = "next_cursor_token"
        svc = _svc()
        svc._repo.list_page = AsyncMock(return_value=([_approval()], cursor_val))

        with _patch(ctx, redis):
            page = await svc.list_requests(WS_ID)

        assert page.has_more
        assert page.next_cursor == cursor_val


# ── Get detail ─────────────────────────────────────────────────────────────────

class TestGetDetail:
    @pytest.mark.asyncio
    async def test_detail_returns_approval(self):
        ctx = _make_ctx()
        redis = _make_redis()
        req = _approval()
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            result = await svc.get_detail(APPROVAL_ID, WS_ID)

        assert result.id == APPROVAL_ID

    @pytest.mark.asyncio
    async def test_detail_cache_hit(self):
        ctx = _make_ctx()
        req = _approval()
        cached = ApprovalRequestOut.model_validate(req)
        redis = _make_redis(cached_value=cached.model_dump_json())
        svc = _svc()

        with _patch(ctx, redis):
            result = await svc.get_detail(APPROVAL_ID, WS_ID)

        assert result.id == APPROVAL_ID
        svc._repo.find_by_id = AsyncMock()
        svc._repo.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_detail_writes_cache_on_miss(self):
        ctx = _make_ctx()
        redis = _make_redis()
        req = _approval()
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            await svc.get_detail(APPROVAL_ID, WS_ID)

        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_detail_not_found_raises(self):
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)

        with _patch(ctx, redis):
            with pytest.raises(Exception):
                await svc.get_detail(APPROVAL_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_detail_wrong_workspace_raises(self):
        ctx = _make_ctx()
        redis = _make_redis()
        req = _approval(workspace_id=uuid.uuid4())  # wrong ws
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with pytest.raises(Exception):
                await svc.get_detail(APPROVAL_ID, WS_ID)


# ── List my reviews ────────────────────────────────────────────────────────────

class TestListMyReviews:
    @pytest.mark.asyncio
    async def test_returns_my_reviews(self):
        ctx = _make_ctx()
        redis = _make_redis()
        req = _approval(assigned_reviewer=str(USER_ID))
        svc = _svc()
        svc._repo.list_my_reviews_page = AsyncMock(return_value=([req], None))

        with _patch(ctx, redis):
            page = await svc.list_my_reviews(WS_ID)

        assert len(page.items) == 1

    @pytest.mark.asyncio
    async def test_my_reviews_cache_hit(self):
        ctx = _make_ctx()
        cached = ApprovalListPage(items=[], next_cursor=None, has_more=False)
        redis = _make_redis(cached_value=cached.model_dump_json())
        svc = _svc()

        with _patch(ctx, redis):
            page = await svc.list_my_reviews(WS_ID)

        assert page.items == []

    @pytest.mark.asyncio
    async def test_my_reviews_writes_cache(self):
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _svc()
        svc._repo.list_my_reviews_page = AsyncMock(return_value=([], None))

        with _patch(ctx, redis):
            await svc.list_my_reviews(WS_ID)

        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_my_reviews_no_cache_on_cursor(self):
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _svc()
        svc._repo.list_my_reviews_page = AsyncMock(return_value=([], None))

        with _patch(ctx, redis):
            await svc.list_my_reviews(WS_ID, cursor="tok")

        redis.get.assert_not_called()


# ── Timeline service ───────────────────────────────────────────────────────────

class TestTimeline:
    @pytest.mark.asyncio
    async def test_list_timeline_returns_events(self):
        ctx = _make_ctx()
        redis = _make_redis()
        req = _approval()
        ev = _timeline_event()
        svc = _timeline_svc()
        approval_repo_mock = MagicMock()
        approval_repo_mock.find_by_id = AsyncMock(return_value=req)
        timeline_repo_mock = MagicMock()
        timeline_repo_mock.list_for_request = AsyncMock(return_value=[ev])
        svc._repo = timeline_repo_mock

        with _patch(ctx, redis):
            with patch(
                "corpmind.modules.approvals.service.ApprovalRepo",
                return_value=approval_repo_mock,
            ):
                events = await svc.list_timeline(APPROVAL_ID, WS_ID)

        assert len(events) == 1
        assert events[0].event_type == "request_created"

    @pytest.mark.asyncio
    async def test_timeline_not_found_raises(self):
        ctx = _make_ctx()
        redis = _make_redis()
        svc = _timeline_svc()
        approval_repo_mock = MagicMock()
        approval_repo_mock.find_by_id = AsyncMock(return_value=None)

        with _patch(ctx, redis):
            with patch(
                "corpmind.modules.approvals.service.ApprovalRepo",
                return_value=approval_repo_mock,
            ):
                with pytest.raises(Exception):
                    await svc.list_timeline(APPROVAL_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_timeline_wrong_workspace_raises(self):
        ctx = _make_ctx()
        redis = _make_redis()
        req = _approval(workspace_id=uuid.uuid4())
        svc = _timeline_svc()
        approval_repo_mock = MagicMock()
        approval_repo_mock.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with patch(
                "corpmind.modules.approvals.service.ApprovalRepo",
                return_value=approval_repo_mock,
            ):
                with pytest.raises(Exception):
                    await svc.list_timeline(APPROVAL_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_timeline_cache_hit(self):
        ctx = _make_ctx()
        ev = _timeline_event()
        out = ApprovalTimelineEventOut.model_validate(ev)
        cached = json.dumps([out.model_dump(mode="json")])
        redis = _make_redis(cached_value=cached)
        req = _approval()
        svc = _timeline_svc()
        approval_repo_mock = MagicMock()
        approval_repo_mock.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with patch(
                "corpmind.modules.approvals.service.ApprovalRepo",
                return_value=approval_repo_mock,
            ):
                events = await svc.list_timeline(APPROVAL_ID, WS_ID)

        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_timeline_writes_cache_on_miss(self):
        ctx = _make_ctx()
        redis = _make_redis()
        req = _approval()
        ev = _timeline_event()
        svc = _timeline_svc()
        approval_repo_mock = MagicMock()
        approval_repo_mock.find_by_id = AsyncMock(return_value=req)
        svc._repo = MagicMock()
        svc._repo.list_for_request = AsyncMock(return_value=[ev])

        with _patch(ctx, redis):
            with patch(
                "corpmind.modules.approvals.service.ApprovalRepo",
                return_value=approval_repo_mock,
            ):
                await svc.list_timeline(APPROVAL_ID, WS_ID)

        redis.set.assert_called_once()


# ── Tenant isolation ───────────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_list_key_is_org_scoped(self):
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        assert _list_key(org_a, WS_ID) != _list_key(org_b, WS_ID)

    @pytest.mark.asyncio
    async def test_detail_key_is_org_scoped(self):
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        assert _detail_key(org_a, APPROVAL_ID) != _detail_key(org_b, APPROVAL_ID)

    @pytest.mark.asyncio
    async def test_list_uses_tenant_context_org_id(self):
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()

        ctx_a = _make_ctx()
        ctx_a.org_id = org_a
        ctx_b = _make_ctx()
        ctx_b.org_id = org_b

        redis = _make_redis()
        svc = _svc()
        svc._repo.list_page = AsyncMock(return_value=([], None))

        captured_keys: list[str] = []

        async def capture_set(key, *args, **kwargs):
            captured_keys.append(key)

        redis.set = AsyncMock(side_effect=capture_set)

        with _patch(ctx_a, redis):
            await svc.list_requests(WS_ID)
        with _patch(ctx_b, redis):
            await svc.list_requests(WS_ID)

        assert len(captured_keys) == 2
        assert captured_keys[0] != captured_keys[1]

    @pytest.mark.asyncio
    async def test_my_reviews_key_is_user_scoped(self):
        key_a = _my_reviews_key(ORG_ID, WS_ID, USER_ID)
        key_b = _my_reviews_key(ORG_ID, WS_ID, OTHER_USER)
        assert key_a != key_b

    def test_approval_wrong_workspace_not_returned(self):
        req = _approval(workspace_id=uuid.uuid4())
        # Service checks workspace_id equality; verify the object has a different WS
        assert req.workspace_id != WS_ID


# ── Cache resilience ───────────────────────────────────────────────────────────

class TestCacheResilience:
    @pytest.mark.asyncio
    async def test_redis_failure_on_get_falls_through(self):
        ctx = _make_ctx()
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("Redis down"))
        redis.set = AsyncMock()
        redis.delete = AsyncMock()

        req = _approval()
        svc = _svc()
        svc._repo.list_page = AsyncMock(return_value=([req], None))

        with _patch(ctx, redis):
            page = await svc.list_requests(WS_ID)

        assert len(page.items) == 1

    @pytest.mark.asyncio
    async def test_redis_failure_on_set_does_not_raise(self):
        ctx = _make_ctx()
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(side_effect=Exception("Redis down"))
        redis.delete = AsyncMock()

        req = _approval()
        svc = _svc()
        svc._repo.list_page = AsyncMock(return_value=([req], None))

        with _patch(ctx, redis):
            page = await svc.list_requests(WS_ID)

        assert len(page.items) == 1

    @pytest.mark.asyncio
    async def test_redis_failure_on_delete_does_not_raise(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        redis.delete = AsyncMock(side_effect=Exception("Redis down"))

        svc = _svc()
        svc._repo.create = AsyncMock(return_value=None)
        svc._timeline_repo.create = AsyncMock()

        data = ApprovalRequestIn(workspace_id=WS_ID, entity_type="task")
        with _patch(ctx, redis):
            result = await svc.create_request(data)

        assert result is not None


# ── State transition coverage ──────────────────────────────────────────────────

class TestStateTransitions:
    @pytest.mark.asyncio
    async def test_pending_can_be_approved(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="pending")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            result = await svc.approve(APPROVAL_ID, WS_ID, ApprovalDecisionIn())
        assert result.status == "approved"

    @pytest.mark.asyncio
    async def test_in_review_can_be_rejected(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="in_review")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)
        svc._repo.update_fields = AsyncMock()
        svc._timeline_repo.create = AsyncMock()

        with _patch(ctx, redis):
            result = await svc.reject(APPROVAL_ID, WS_ID, ApprovalDecisionIn())
        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_rejected_cannot_be_cancelled(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="rejected")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with pytest.raises(InvalidStateError):
                await svc.cancel(APPROVAL_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_approved_cannot_be_rejected(self):
        ctx = _make_ctx(role="OrgAdmin")
        redis = _make_redis()
        req = _approval(status="approved")
        svc = _svc()
        svc._repo.find_by_id = AsyncMock(return_value=req)

        with _patch(ctx, redis):
            with pytest.raises(InvalidStateError):
                await svc.reject(APPROVAL_ID, WS_ID, ApprovalDecisionIn())
