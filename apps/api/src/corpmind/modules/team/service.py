"""Team module services — Sprint 30.

Design constraints:
- No AI.  No LLM calls.  No Celery.  No background jobs.
- All actions are human-triggered via explicit API calls.
- Permission checks are workspace-role-based (owner/admin/member/viewer).
- Redis cache: members=600s, activity_first_page=300s, comments=300s.
- No cross-module repo/model imports — team data flows through this module only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.team.models import ActivityFeedEntry, TaskComment, WorkspaceMember
from corpmind.modules.team.repo import ActivityFeedRepo, CommentRepo, WorkspaceMemberRepo
from corpmind.modules.team.schemas import (
    ActivityFeedEntryOut,
    ActivityFeedPage,
    CommentIn,
    CommentOut,
    MemberInviteIn,
    MemberListOut,
    MemberRoleUpdate,
    WorkspaceMemberOut,
)

log = structlog.get_logger(__name__)

_MEMBERS_TTL = 600    # 10 minutes
_ACTIVITY_TTL = 300   # 5 minutes
_COMMENTS_TTL = 300   # 5 minutes

_ADMIN_ROLES: frozenset[str] = frozenset({"owner", "admin"})
_WRITE_ROLES: frozenset[str] = frozenset({"owner", "admin", "member"})


class PermissionDeniedError(Exception):
    """Raised when the current user lacks the required workspace role."""


def _log_event(event: object) -> None:
    log.info("team.domain_event", event_type=type(event).__name__, payload=repr(event))


# ── WorkspaceMemberService ────────────────────────────────────────────────────

class WorkspaceMemberService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = WorkspaceMemberRepo(session)
        self._activity_repo = ActivityFeedRepo(session)

    def _members_key(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
        return f"t:{org_id}:{workspace_id}:team:members"

    def _activity_key(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
        return f"t:{org_id}:{workspace_id}:team:activity:first"

    async def _invalidate_members(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        try:
            await get_redis().delete(
                self._members_key(org_id, workspace_id),
                self._activity_key(org_id, workspace_id),
            )
        except Exception:
            pass

    async def _get_actor_role(self, workspace_id: uuid.UUID) -> str:
        ctx = get_tenant_context()
        member = await self._repo.find_active_by_user(workspace_id, ctx.user_id)
        return member.role if member else "viewer"

    async def invite(self, data: MemberInviteIn) -> WorkspaceMemberOut:
        ctx = get_tenant_context()
        actor_role = await self._get_actor_role(data.workspace_id)
        if actor_role not in _ADMIN_ROLES:
            raise PermissionDeniedError("Only owners and admins can invite members")
        if data.role == "owner" and actor_role != "owner":
            raise PermissionDeniedError("Only owners can promote others to owner")

        existing = await self._repo.find_active_by_user(data.workspace_id, data.user_id)
        if existing:
            raise ValueError("User is already an active member of this workspace")

        member = WorkspaceMember(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=data.workspace_id,
            user_id=data.user_id,
            role=data.role,
            invited_by=str(ctx.user_id),
        )
        await self._repo.create(member)
        await self._invalidate_members(ctx.org_id, data.workspace_id)
        await self._log_activity(
            workspace_id=data.workspace_id,
            entity_type="member",
            entity_id=member.id,
            action="member.invited",
            meta={"role": data.role, "user_id": str(data.user_id)},
        )
        log.info("team.member.invited", member_id=str(member.id), role=data.role)
        return WorkspaceMemberOut.model_validate(member)

    async def accept_invitation(self, member_id: uuid.UUID, workspace_id: uuid.UUID) -> WorkspaceMemberOut:
        ctx = get_tenant_context()
        member = await self._repo.find_by_id(member_id)
        if (
            member is None
            or member.workspace_id != workspace_id
            or member.removed_at is not None
        ):
            raise NotFoundError(f"Invitation {member_id} not found")
        if member.user_id != ctx.user_id:
            raise PermissionDeniedError("You can only accept your own invitation")
        if member.accepted_at is not None:
            raise ValueError("Invitation already accepted")

        now = datetime.now(UTC)
        await self._repo.update_fields(member_id, accepted_at=now)
        member.accepted_at = now
        await self._invalidate_members(ctx.org_id, workspace_id)
        await self._log_activity(
            workspace_id=workspace_id,
            entity_type="member",
            entity_id=member_id,
            action="member.accepted",
            meta={"user_id": str(ctx.user_id)},
        )
        log.info("team.member.accepted", member_id=str(member_id))
        return WorkspaceMemberOut.model_validate(member)

    async def remove(self, member_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        actor_role = await self._get_actor_role(workspace_id)
        if actor_role not in _ADMIN_ROLES:
            raise PermissionDeniedError("Only owners and admins can remove members")

        member = await self._repo.find_by_id(member_id)
        if (
            member is None
            or member.workspace_id != workspace_id
            or member.removed_at is not None
        ):
            raise NotFoundError(f"Member {member_id} not found")
        if member.role == "owner" and actor_role != "owner":
            raise PermissionDeniedError("Only owners can remove other owners")

        now = datetime.now(UTC)
        await self._repo.update_fields(member_id, removed_at=now)
        await self._invalidate_members(ctx.org_id, workspace_id)
        await self._log_activity(
            workspace_id=workspace_id,
            entity_type="member",
            entity_id=member_id,
            action="member.removed",
            meta={"removed_by": str(ctx.user_id), "role": member.role},
        )
        log.info("team.member.removed", member_id=str(member_id))

    async def change_role(
        self, member_id: uuid.UUID, workspace_id: uuid.UUID, data: MemberRoleUpdate
    ) -> WorkspaceMemberOut:
        ctx = get_tenant_context()
        actor_role = await self._get_actor_role(workspace_id)
        if actor_role not in _ADMIN_ROLES:
            raise PermissionDeniedError("Only owners and admins can change roles")
        if data.role == "owner" and actor_role != "owner":
            raise PermissionDeniedError("Only owners can promote others to owner")

        member = await self._repo.find_by_id(member_id)
        if (
            member is None
            or member.workspace_id != workspace_id
            or member.removed_at is not None
        ):
            raise NotFoundError(f"Member {member_id} not found")

        old_role = member.role
        await self._repo.update_fields(member_id, role=data.role)
        member.role = data.role
        await self._invalidate_members(ctx.org_id, workspace_id)
        await self._log_activity(
            workspace_id=workspace_id,
            entity_type="member",
            entity_id=member_id,
            action="member.role_changed",
            meta={"old_role": old_role, "new_role": data.role},
        )
        log.info("team.member.role_changed", member_id=str(member_id), old=old_role, new=data.role)
        return WorkspaceMemberOut.model_validate(member)

    async def list_members(self, workspace_id: uuid.UUID) -> MemberListOut:
        ctx = get_tenant_context()
        key = self._members_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return MemberListOut.model_validate_json(cached)
        except Exception:
            pass

        members = await self._repo.list_active(workspace_id)
        result = MemberListOut(
            items=[WorkspaceMemberOut.model_validate(m) for m in members],
            total=len(members),
        )
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_MEMBERS_TTL)
        except Exception:
            pass
        return result

    async def _log_activity(
        self,
        workspace_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID | None,
        action: str,
        meta: dict | None = None,
    ) -> None:
        ctx = get_tenant_context()
        entry = ActivityFeedEntry(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            actor_user_id=str(ctx.user_id),
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            feed_metadata=meta,
        )
        await self._activity_repo.create(entry)
        # Invalidate first-page activity cache
        try:
            await get_redis().delete(self._activity_key(ctx.org_id, workspace_id))
        except Exception:
            pass


# ── ActivityFeedService ───────────────────────────────────────────────────────

class ActivityFeedService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ActivityFeedRepo(session)

    def _first_page_key(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
        return f"t:{org_id}:{workspace_id}:team:activity:first"

    async def log_event(
        self,
        workspace_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID | None,
        action: str,
        meta: dict | None = None,
    ) -> None:
        ctx = get_tenant_context()
        entry = ActivityFeedEntry(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            actor_user_id=str(ctx.user_id),
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            feed_metadata=meta,
        )
        await self._repo.create(entry)
        try:
            await get_redis().delete(self._first_page_key(ctx.org_id, workspace_id))
        except Exception:
            pass

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ActivityFeedPage:
        ctx = get_tenant_context()
        # Cache only the first page (no cursor) to keep invalidation simple
        if cursor is None:
            key = self._first_page_key(ctx.org_id, workspace_id)
            try:
                cached = await get_redis().get(key)
                if cached:
                    return ActivityFeedPage.model_validate_json(cached)
            except Exception:
                pass

        items, next_cursor = await self._repo.list_page(workspace_id, limit, cursor)
        result = ActivityFeedPage(
            items=[ActivityFeedEntryOut.model_validate(e) for e in items],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
        )
        if cursor is None:
            try:
                await get_redis().set(
                    self._first_page_key(ctx.org_id, workspace_id),
                    result.model_dump_json(),
                    ex=_ACTIVITY_TTL,
                )
            except Exception:
                pass
        return result


# ── CommentService ────────────────────────────────────────────────────────────

class CommentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CommentRepo(session)
        self._activity_repo = ActivityFeedRepo(session)

    def _comments_key(self, org_id: uuid.UUID, workspace_id: uuid.UUID, task_id: uuid.UUID) -> str:
        return f"t:{org_id}:{workspace_id}:team:comments:{task_id}"

    async def _invalidate(self, org_id: uuid.UUID, workspace_id: uuid.UUID, task_id: uuid.UUID) -> None:
        try:
            await get_redis().delete(self._comments_key(org_id, workspace_id, task_id))
        except Exception:
            pass

    async def _check_write_permission(self, workspace_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        member_repo = WorkspaceMemberRepo(self._session)
        member = await member_repo.find_active_by_user(workspace_id, ctx.user_id)
        role = member.role if member else "viewer"
        if role not in _WRITE_ROLES:
            raise PermissionDeniedError("Viewers cannot post comments")

    async def create(
        self, task_id: uuid.UUID, workspace_id: uuid.UUID, data: CommentIn
    ) -> CommentOut:
        ctx = get_tenant_context()
        await self._check_write_permission(workspace_id)

        comment = TaskComment(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            task_id=task_id,
            author_user_id=str(ctx.user_id),
            body=data.body,
        )
        await self._repo.create(comment)
        await self._invalidate(ctx.org_id, workspace_id, task_id)

        # Log activity
        activity = ActivityFeedEntry(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            actor_user_id=str(ctx.user_id),
            entity_type="task",
            entity_id=task_id,
            action="task.commented",
            feed_metadata={"comment_id": str(comment.id)},
        )
        await self._activity_repo.create(activity)
        try:
            first_key = f"t:{ctx.org_id}:{workspace_id}:team:activity:first"
            await get_redis().delete(first_key)
        except Exception:
            pass

        log.info("team.comment.created", comment_id=str(comment.id), task_id=str(task_id))
        return CommentOut.model_validate(comment)

    async def delete_own(self, comment_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        comment = await self._repo.find_by_id(comment_id)
        if comment is None or comment.workspace_id != workspace_id:
            raise NotFoundError(f"Comment {comment_id} not found")
        if comment.author_user_id != str(ctx.user_id):
            raise PermissionDeniedError("You can only delete your own comments")

        task_id = comment.task_id
        await self._repo.delete(comment_id)
        await self._invalidate(ctx.org_id, workspace_id, task_id)
        log.info("team.comment.deleted", comment_id=str(comment_id))

    async def list(
        self, task_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[CommentOut]:
        ctx = get_tenant_context()
        key = self._comments_key(ctx.org_id, workspace_id, task_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                import json
                raw = json.loads(cached)
                return [CommentOut.model_validate(item) for item in raw]
        except Exception:
            pass

        comments = await self._repo.list_for_task(task_id, workspace_id)
        result = [CommentOut.model_validate(c) for c in comments]
        try:
            import json
            await get_redis().set(
                key,
                json.dumps([c.model_dump(mode="json") for c in result]),
                ex=_COMMENTS_TTL,
            )
        except Exception:
            pass
        return result
