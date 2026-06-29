"""Approval workflow services — Sprint 31.

Design constraints:
- No AI.  No LLM.  No Celery.  No background jobs.
- All actions are human-triggered.
- Permissions: org-level role (OrgAdmin/AgencyManager = full access) +
  ownership-based checks (requester can cancel, assigned reviewer can decide).
- No cross-module repo imports — permissions rely only on TenantContext and
  request field values.
- Redis cache: list/detail/timeline all TTL 300s.
- Cursor pagination (newest-first) on all list endpoints.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.approvals.models import ApprovalRequest, ApprovalTimelineEvent
from corpmind.modules.approvals.repo import ApprovalRepo, ApprovalTimelineRepo
from corpmind.modules.approvals.schemas import (
    ApprovalAssignIn,
    ApprovalDecisionIn,
    ApprovalListPage,
    ApprovalRequestIn,
    ApprovalRequestOut,
    ApprovalTimelineEventOut,
)

log = structlog.get_logger(__name__)

_APPROVAL_TTL = 300  # 5 minutes for all approval caches

# Org-level roles that have unrestricted access to all approval operations
_ORG_ADMIN_ROLES: frozenset[str] = frozenset({"OrgAdmin", "AgencyManager"})

# Statuses from which state transitions are valid
_ACTIVE_STATUSES: frozenset[str] = frozenset({"pending", "in_review"})


class PermissionDeniedError(Exception):
    """Raised when the current user lacks the required role for this operation."""


class InvalidStateError(Exception):
    """Raised when a state transition is not valid from the current status."""


def _log_event(event: object) -> None:
    log.info("approvals.domain_event", event_type=type(event).__name__, payload=repr(event))


# ── Cache key helpers ─────────────────────────────────────────────────────────

def _list_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:approvals:list"


def _my_reviews_key(org_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:approvals:my-reviews:{user_id}"


def _detail_key(org_id: uuid.UUID, approval_id: uuid.UUID) -> str:
    return f"t:{org_id}:approvals:detail:{approval_id}"


def _timeline_key(org_id: uuid.UUID, approval_id: uuid.UUID) -> str:
    return f"t:{org_id}:approvals:timeline:{approval_id}"


# ── ApprovalService ───────────────────────────────────────────────────────────

class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ApprovalRepo(session)
        self._timeline_repo = ApprovalTimelineRepo(session)

    async def _invalidate_all(
        self, org_id: uuid.UUID, workspace_id: uuid.UUID, approval_id: uuid.UUID
    ) -> None:
        """Invalidate list, detail, and timeline caches for this approval."""
        try:
            await get_redis().delete(
                _list_key(org_id, workspace_id),
                _detail_key(org_id, approval_id),
                _timeline_key(org_id, approval_id),
            )
        except Exception:
            pass

    async def _invalidate_my_reviews(
        self, org_id: uuid.UUID, workspace_id: uuid.UUID, reviewer: str | None
    ) -> None:
        if not reviewer:
            return
        try:
            # reviewer is stored as a string user_id; approximate UUID parse
            reviewer_uuid = uuid.UUID(reviewer)
            await get_redis().delete(_my_reviews_key(org_id, workspace_id, reviewer_uuid))
        except Exception:
            pass

    async def _record_timeline(
        self,
        approval_id: uuid.UUID,
        event_type: str,
        notes: str | None = None,
    ) -> None:
        ctx = get_tenant_context()
        event = ApprovalTimelineEvent(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            approval_request_id=approval_id,
            event_type=event_type,
            actor_user_id=str(ctx.user_id),
            notes=notes,
        )
        await self._timeline_repo.create(event)
        try:
            await get_redis().delete(_timeline_key(ctx.org_id, approval_id))
        except Exception:
            pass

    async def create_request(self, data: ApprovalRequestIn) -> ApprovalRequestOut:
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        request = ApprovalRequest(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=data.workspace_id,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            requested_by=str(ctx.user_id),
            assigned_reviewer=data.assigned_reviewer,
            priority=data.priority,
            status="pending",
            decision="none",
            comments=data.comments,
            due_date=data.due_date,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(request)

        # Invalidate the list cache (new item appeared)
        try:
            await get_redis().delete(_list_key(ctx.org_id, data.workspace_id))
        except Exception:
            pass

        await self._record_timeline(request.id, "request_created", data.comments)

        # If a reviewer was assigned at creation, record that too
        if data.assigned_reviewer:
            await self._record_timeline(
                request.id, "reviewer_assigned", f"Assigned to {data.assigned_reviewer}"
            )
            await self._invalidate_my_reviews(ctx.org_id, data.workspace_id, data.assigned_reviewer)

        log.info(
            "approvals.created",
            approval_id=str(request.id),
            entity_type=data.entity_type,
            priority=data.priority,
        )
        return ApprovalRequestOut.model_validate(request)

    async def assign_reviewer(
        self, approval_id: uuid.UUID, workspace_id: uuid.UUID, data: ApprovalAssignIn
    ) -> ApprovalRequestOut:
        ctx = get_tenant_context()
        request = await self._repo.find_by_id(approval_id)
        if request is None or request.workspace_id != workspace_id:
            raise NotFoundError(f"ApprovalRequest {approval_id} not found")
        if request.status not in _ACTIVE_STATUSES:
            raise InvalidStateError(
                f"Cannot assign reviewer: request is already {request.status}"
            )

        # Only OrgAdmin/AgencyManager or the requester can assign reviewers
        is_admin = ctx.role in _ORG_ADMIN_ROLES
        is_requester = request.requested_by == str(ctx.user_id)
        if not (is_admin or is_requester):
            raise PermissionDeniedError("Only the requester or an admin can assign a reviewer")

        old_reviewer = request.assigned_reviewer
        now = datetime.now(UTC)
        await self._repo.update_fields(
            approval_id,
            assigned_reviewer=data.assigned_reviewer,
            status="in_review",
            updated_at=now,
        )
        request.assigned_reviewer = data.assigned_reviewer
        request.status = "in_review"
        request.updated_at = now

        await self._invalidate_all(ctx.org_id, workspace_id, approval_id)
        await self._invalidate_my_reviews(ctx.org_id, workspace_id, old_reviewer)
        await self._invalidate_my_reviews(ctx.org_id, workspace_id, data.assigned_reviewer)

        await self._record_timeline(
            approval_id,
            "reviewer_assigned",
            f"Assigned to {data.assigned_reviewer}",
        )
        log.info("approvals.assigned", approval_id=str(approval_id), reviewer=data.assigned_reviewer)
        return ApprovalRequestOut.model_validate(request)

    async def approve(
        self, approval_id: uuid.UUID, workspace_id: uuid.UUID, data: ApprovalDecisionIn
    ) -> ApprovalRequestOut:
        ctx = get_tenant_context()
        request = await self._repo.find_by_id(approval_id)
        if request is None or request.workspace_id != workspace_id:
            raise NotFoundError(f"ApprovalRequest {approval_id} not found")
        if request.status not in _ACTIVE_STATUSES:
            raise InvalidStateError(
                f"Cannot approve: request is already {request.status}"
            )

        is_admin = ctx.role in _ORG_ADMIN_ROLES
        is_reviewer = request.assigned_reviewer == str(ctx.user_id)
        if not (is_admin or is_reviewer):
            raise PermissionDeniedError(
                "Only the assigned reviewer or an admin can approve this request"
            )

        now = datetime.now(UTC)
        await self._repo.update_fields(
            approval_id,
            status="approved",
            decision="approve",
            reviewed_at=now,
            updated_at=now,
            comments=data.comments or request.comments,
        )
        request.status = "approved"
        request.decision = "approve"
        request.reviewed_at = now
        request.updated_at = now
        if data.comments:
            request.comments = data.comments

        await self._invalidate_all(ctx.org_id, workspace_id, approval_id)
        await self._invalidate_my_reviews(ctx.org_id, workspace_id, request.assigned_reviewer)
        await self._record_timeline(approval_id, "approved", data.comments)

        log.info("approvals.approved", approval_id=str(approval_id))
        return ApprovalRequestOut.model_validate(request)

    async def reject(
        self, approval_id: uuid.UUID, workspace_id: uuid.UUID, data: ApprovalDecisionIn
    ) -> ApprovalRequestOut:
        ctx = get_tenant_context()
        request = await self._repo.find_by_id(approval_id)
        if request is None or request.workspace_id != workspace_id:
            raise NotFoundError(f"ApprovalRequest {approval_id} not found")
        if request.status not in _ACTIVE_STATUSES:
            raise InvalidStateError(
                f"Cannot reject: request is already {request.status}"
            )

        is_admin = ctx.role in _ORG_ADMIN_ROLES
        is_reviewer = request.assigned_reviewer == str(ctx.user_id)
        if not (is_admin or is_reviewer):
            raise PermissionDeniedError(
                "Only the assigned reviewer or an admin can reject this request"
            )

        now = datetime.now(UTC)
        await self._repo.update_fields(
            approval_id,
            status="rejected",
            decision="reject",
            reviewed_at=now,
            updated_at=now,
            comments=data.comments or request.comments,
        )
        request.status = "rejected"
        request.decision = "reject"
        request.reviewed_at = now
        request.updated_at = now
        if data.comments:
            request.comments = data.comments

        await self._invalidate_all(ctx.org_id, workspace_id, approval_id)
        await self._invalidate_my_reviews(ctx.org_id, workspace_id, request.assigned_reviewer)
        await self._record_timeline(approval_id, "rejected", data.comments)

        log.info("approvals.rejected", approval_id=str(approval_id))
        return ApprovalRequestOut.model_validate(request)

    async def cancel(
        self, approval_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> ApprovalRequestOut:
        ctx = get_tenant_context()
        request = await self._repo.find_by_id(approval_id)
        if request is None or request.workspace_id != workspace_id:
            raise NotFoundError(f"ApprovalRequest {approval_id} not found")
        if request.status not in _ACTIVE_STATUSES:
            raise InvalidStateError(
                f"Cannot cancel: request is already {request.status}"
            )

        is_admin = ctx.role in _ORG_ADMIN_ROLES
        is_requester = request.requested_by == str(ctx.user_id)
        if not (is_admin or is_requester):
            raise PermissionDeniedError(
                "Only the requester or an admin can cancel this request"
            )

        now = datetime.now(UTC)
        await self._repo.update_fields(
            approval_id, status="cancelled", updated_at=now
        )
        request.status = "cancelled"
        request.updated_at = now

        await self._invalidate_all(ctx.org_id, workspace_id, approval_id)
        await self._invalidate_my_reviews(ctx.org_id, workspace_id, request.assigned_reviewer)
        await self._record_timeline(approval_id, "cancelled")

        log.info("approvals.cancelled", approval_id=str(approval_id))
        return ApprovalRequestOut.model_validate(request)

    async def list_requests(
        self,
        workspace_id: uuid.UUID,
        cursor: str | None = None,
        limit: int = 50,
        status: str | None = None,
        priority: str | None = None,
        assigned_reviewer: str | None = None,
    ) -> ApprovalListPage:
        ctx = get_tenant_context()
        # Cache only unfiltered first page
        is_first_page = cursor is None and not any([status, priority, assigned_reviewer])
        if is_first_page:
            key = _list_key(ctx.org_id, workspace_id)
            try:
                cached = await get_redis().get(key)
                if cached:
                    return ApprovalListPage.model_validate_json(cached)
            except Exception:
                pass

        items, next_cursor = await self._repo.list_page(
            workspace_id, limit, cursor, status, priority, assigned_reviewer
        )
        result = ApprovalListPage(
            items=[ApprovalRequestOut.model_validate(r) for r in items],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
        )
        if is_first_page:
            try:
                await get_redis().set(
                    _list_key(ctx.org_id, workspace_id),
                    result.model_dump_json(),
                    ex=_APPROVAL_TTL,
                )
            except Exception:
                pass
        return result

    async def get_detail(
        self, approval_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> ApprovalRequestOut:
        ctx = get_tenant_context()
        key = _detail_key(ctx.org_id, approval_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return ApprovalRequestOut.model_validate_json(cached)
        except Exception:
            pass

        request = await self._repo.find_by_id(approval_id)
        if request is None or request.workspace_id != workspace_id:
            raise NotFoundError(f"ApprovalRequest {approval_id} not found")

        result = ApprovalRequestOut.model_validate(request)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_APPROVAL_TTL)
        except Exception:
            pass
        return result

    async def list_my_reviews(
        self,
        workspace_id: uuid.UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ApprovalListPage:
        ctx = get_tenant_context()
        is_first_page = cursor is None
        if is_first_page:
            key = _my_reviews_key(ctx.org_id, workspace_id, ctx.user_id)
            try:
                cached = await get_redis().get(key)
                if cached:
                    return ApprovalListPage.model_validate_json(cached)
            except Exception:
                pass

        items, next_cursor = await self._repo.list_my_reviews_page(
            str(ctx.user_id), workspace_id, limit, cursor
        )
        result = ApprovalListPage(
            items=[ApprovalRequestOut.model_validate(r) for r in items],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
        )
        if is_first_page:
            try:
                await get_redis().set(
                    _my_reviews_key(ctx.org_id, workspace_id, ctx.user_id),
                    result.model_dump_json(),
                    ex=_APPROVAL_TTL,
                )
            except Exception:
                pass
        return result


# ── ApprovalTimelineService ───────────────────────────────────────────────────

class ApprovalTimelineService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ApprovalTimelineRepo(session)

    def _cache_key(self, org_id: uuid.UUID, approval_id: uuid.UUID) -> str:
        return _timeline_key(org_id, approval_id)

    async def list_timeline(
        self, approval_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[ApprovalTimelineEventOut]:
        ctx = get_tenant_context()
        # Verify the request belongs to this workspace (basic scope check)
        approval_repo = ApprovalRepo(self._session)
        request = await approval_repo.find_by_id(approval_id)
        if request is None or request.workspace_id != workspace_id:
            raise NotFoundError(f"ApprovalRequest {approval_id} not found")

        key = self._cache_key(ctx.org_id, approval_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                import json
                raw = json.loads(cached)
                return [ApprovalTimelineEventOut.model_validate(item) for item in raw]
        except Exception:
            pass

        events = await self._repo.list_for_request(approval_id)
        result = [ApprovalTimelineEventOut.model_validate(e) for e in events]
        try:
            import json
            await get_redis().set(
                key,
                json.dumps([e.model_dump(mode="json") for e in result]),
                ex=_APPROVAL_TTL,
            )
        except Exception:
            pass
        return result
