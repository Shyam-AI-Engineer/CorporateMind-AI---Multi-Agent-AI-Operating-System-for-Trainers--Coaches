"""Unit tests for team module services — Sprint 30.

Covers:
- WorkspaceMemberService: invite, accept, remove, change_role, list_members
- CommentService: create, delete_own, list
- ActivityFeedService: log_event, list_page
- Permission checks (owner/admin/member/viewer)
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
from corpmind.modules.team.service import (
    ActivityFeedService,
    CommentService,
    PermissionDeniedError,
    WorkspaceMemberService,
)

# ── Constants ──────────────────────────────────────────────────────────────────

ORG_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WS_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
OTHER_USER = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
MEMBER_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
TASK_ID = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
COMMENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

NOW = datetime(2026, 6, 28, 10, 0, 0, tzinfo=timezone.utc)


# ── Mock helpers ───────────────────────────────────────────────────────────────

def _make_ctx(role: str = "viewer") -> MagicMock:
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


def _member(
    id: uuid.UUID = MEMBER_ID,
    user_id: uuid.UUID = USER_ID,
    role: str = "member",
    accepted_at: datetime | None = NOW,
    removed_at: datetime | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = id
    m.tenant_id = ORG_ID
    m.workspace_id = WS_ID
    m.user_id = user_id
    m.role = role
    m.invited_by = str(USER_ID)
    m.invited_at = NOW
    m.accepted_at = accepted_at
    m.removed_at = removed_at
    return m


def _comment(
    id: uuid.UUID = COMMENT_ID,
    task_id: uuid.UUID = TASK_ID,
    author_user_id: str | None = None,
    body: str = "Hello",
) -> MagicMock:
    c = MagicMock()
    c.id = id
    c.tenant_id = ORG_ID
    c.workspace_id = WS_ID
    c.task_id = task_id
    c.author_user_id = author_user_id or str(USER_ID)
    c.body = body
    c.created_at = NOW
    return c


def _feed_entry(id: uuid.UUID | None = None) -> MagicMock:
    e = MagicMock()
    e.id = id or uuid.uuid4()
    e.tenant_id = ORG_ID
    e.workspace_id = WS_ID
    e.actor_user_id = str(USER_ID)
    e.entity_type = "task"
    e.entity_id = TASK_ID
    e.action = "task.created"
    e.feed_metadata = None
    e.created_at = NOW
    return e


@contextmanager
def _patch(ctx: MagicMock, redis: MagicMock):
    with patch("corpmind.modules.team.service.get_tenant_context", return_value=ctx):
        with patch("corpmind.modules.team.service.get_redis", return_value=redis):
            yield


def _member_svc(actor_role: str = "admin") -> tuple[WorkspaceMemberService, MagicMock, MagicMock]:
    session = MagicMock()
    svc = WorkspaceMemberService(session=session)
    member_repo = MagicMock()
    activity_repo = MagicMock()
    activity_repo.create = AsyncMock()
    svc._repo = member_repo
    svc._activity_repo = activity_repo
    # Default: actor is the current user with actor_role
    actor_member = _member(role=actor_role)
    member_repo.find_active_by_user = AsyncMock(return_value=actor_member)
    return svc, member_repo, activity_repo


def _comment_svc() -> tuple[CommentService, MagicMock, MagicMock]:
    session = MagicMock()
    svc = CommentService(session=session)
    comment_repo = MagicMock()
    activity_repo = MagicMock()
    activity_repo.create = AsyncMock()
    svc._repo = comment_repo
    svc._activity_repo = activity_repo
    return svc, comment_repo, activity_repo


def _activity_svc() -> tuple[ActivityFeedService, MagicMock]:
    session = MagicMock()
    svc = ActivityFeedService(session=session)
    feed_repo = MagicMock()
    svc._repo = feed_repo
    return svc, feed_repo


# ── TestSchemas ───────────────────────────────────────────────────────────────

class TestSchemas:
    def test_member_invite_valid_roles(self):
        for role in ("owner", "admin", "member", "viewer"):
            data = MemberInviteIn(workspace_id=WS_ID, user_id=USER_ID, role=role)
            assert data.role == role

    def test_member_invite_invalid_role(self):
        with pytest.raises(Exception):
            MemberInviteIn(workspace_id=WS_ID, user_id=USER_ID, role="superuser")

    def test_member_invite_default_role(self):
        data = MemberInviteIn(workspace_id=WS_ID, user_id=USER_ID)
        assert data.role == "member"

    def test_role_update_valid(self):
        for role in ("owner", "admin", "member", "viewer"):
            data = MemberRoleUpdate(role=role)
            assert data.role == role

    def test_role_update_invalid(self):
        with pytest.raises(Exception):
            MemberRoleUpdate(role="god")

    def test_comment_in_valid(self):
        data = CommentIn(body="  hello  ")
        assert data.body == "hello"

    def test_comment_in_empty(self):
        with pytest.raises(Exception):
            CommentIn(body="   ")

    def test_comment_in_too_long(self):
        with pytest.raises(Exception):
            CommentIn(body="x" * 2001)

    def test_comment_in_max_length(self):
        data = CommentIn(body="x" * 2000)
        assert len(data.body) == 2000

    def test_member_out_from_attributes(self):
        m = _member()
        out = WorkspaceMemberOut.model_validate(m)
        assert out.id == MEMBER_ID
        assert out.role == "member"
        assert out.accepted_at == NOW

    def test_comment_out_from_attributes(self):
        c = _comment()
        out = CommentOut.model_validate(c)
        assert out.id == COMMENT_ID
        assert out.body == "Hello"


# ── TestCacheKeys ─────────────────────────────────────────────────────────────

class TestCacheKeys:
    def test_members_key_format(self):
        svc, _, _ = _member_svc()
        key = svc._members_key(ORG_ID, WS_ID)
        assert key == f"t:{ORG_ID}:{WS_ID}:team:members"

    def test_activity_key_format(self):
        svc, _, _ = _member_svc()
        key = svc._activity_key(ORG_ID, WS_ID)
        assert key == f"t:{ORG_ID}:{WS_ID}:team:activity:first"

    def test_comments_key_format(self):
        svc, _, _ = _comment_svc()
        key = svc._comments_key(ORG_ID, WS_ID, TASK_ID)
        assert key == f"t:{ORG_ID}:{WS_ID}:team:comments:{TASK_ID}"

    def test_activity_svc_first_page_key_format(self):
        svc, _ = _activity_svc()
        key = svc._first_page_key(ORG_ID, WS_ID)
        assert key == f"t:{ORG_ID}:{WS_ID}:team:activity:first"


# ── TestInvite ────────────────────────────────────────────────────────────────

class TestInvite:
    @pytest.mark.asyncio
    async def test_invite_success_as_admin(self):
        svc, member_repo, activity_repo = _member_svc(actor_role="admin")
        redis = _make_redis()
        ctx = _make_ctx()

        # First call: actor lookup; second call: existing member check (None = no existing)
        member_repo.find_active_by_user = AsyncMock(side_effect=[
            _member(role="admin"),  # actor
            None,                   # target user not yet a member
        ])

        async def fake_create(m):
            m.invited_at = NOW
            return m
        member_repo.create = AsyncMock(side_effect=fake_create)

        data = MemberInviteIn(workspace_id=WS_ID, user_id=OTHER_USER, role="member")
        with _patch(ctx, redis):
            result = await svc.invite(data)

        assert result.user_id == OTHER_USER
        assert result.role == "member"
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_invite_denied_for_member_role(self):
        svc, member_repo, _ = _member_svc(actor_role="member")
        redis = _make_redis()
        ctx = _make_ctx()

        data = MemberInviteIn(workspace_id=WS_ID, user_id=OTHER_USER, role="viewer")
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.invite(data)

    @pytest.mark.asyncio
    async def test_invite_denied_for_viewer_role(self):
        svc, member_repo, _ = _member_svc(actor_role="viewer")
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="viewer"))

        data = MemberInviteIn(workspace_id=WS_ID, user_id=OTHER_USER, role="viewer")
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.invite(data)

    @pytest.mark.asyncio
    async def test_invite_owner_promotion_requires_owner_role(self):
        svc, member_repo, _ = _member_svc(actor_role="admin")
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="admin"))

        data = MemberInviteIn(workspace_id=WS_ID, user_id=OTHER_USER, role="owner")
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.invite(data)

    @pytest.mark.asyncio
    async def test_invite_owner_can_promote_to_owner(self):
        svc, member_repo, activity_repo = _member_svc(actor_role="owner")
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.find_active_by_user = AsyncMock(side_effect=[
            _member(role="owner"),
            None,
        ])

        async def fake_create(m):
            m.invited_at = NOW
            return m
        member_repo.create = AsyncMock(side_effect=fake_create)

        data = MemberInviteIn(workspace_id=WS_ID, user_id=OTHER_USER, role="owner")
        with _patch(ctx, redis):
            result = await svc.invite(data)
        assert result.role == "owner"

    @pytest.mark.asyncio
    async def test_invite_duplicate_raises_value_error(self):
        svc, member_repo, _ = _member_svc(actor_role="admin")
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.find_active_by_user = AsyncMock(side_effect=[
            _member(role="admin"),
            _member(),  # already exists
        ])

        data = MemberInviteIn(workspace_id=WS_ID, user_id=OTHER_USER, role="member")
        with _patch(ctx, redis):
            with pytest.raises(ValueError, match="already an active member"):
                await svc.invite(data)


# ── TestAcceptInvitation ───────────────────────────────────────────────────────

class TestAcceptInvitation:
    @pytest.mark.asyncio
    async def test_accept_success(self):
        svc, member_repo, _ = _member_svc()
        redis = _make_redis()
        ctx = _make_ctx()
        ctx.user_id = USER_ID

        pending = _member(accepted_at=None)
        pending.user_id = USER_ID
        member_repo.find_by_id = AsyncMock(return_value=pending)
        member_repo.update_fields = AsyncMock()

        with _patch(ctx, redis):
            result = await svc.accept_invitation(MEMBER_ID, WS_ID)

        assert result.id == MEMBER_ID
        member_repo.update_fields.assert_called_once()
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_accept_wrong_user_raises_permission(self):
        svc, member_repo, _ = _member_svc()
        redis = _make_redis()
        ctx = _make_ctx()
        ctx.user_id = USER_ID

        pending = _member(accepted_at=None)
        pending.user_id = OTHER_USER  # different user
        member_repo.find_by_id = AsyncMock(return_value=pending)

        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.accept_invitation(MEMBER_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_accept_not_found(self):
        svc, member_repo, _ = _member_svc()
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.find_by_id = AsyncMock(return_value=None)

        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.accept_invitation(MEMBER_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_accept_already_accepted_raises(self):
        svc, member_repo, _ = _member_svc()
        redis = _make_redis()
        ctx = _make_ctx()
        ctx.user_id = USER_ID

        already = _member(accepted_at=NOW)
        already.user_id = USER_ID
        member_repo.find_by_id = AsyncMock(return_value=already)

        with _patch(ctx, redis):
            with pytest.raises(ValueError, match="already accepted"):
                await svc.accept_invitation(MEMBER_ID, WS_ID)


# ── TestRemoveMember ──────────────────────────────────────────────────────────

class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_remove_success_as_admin(self):
        svc, member_repo, _ = _member_svc(actor_role="admin")
        redis = _make_redis()
        ctx = _make_ctx()

        target = _member(id=MEMBER_ID, user_id=OTHER_USER, role="member")
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="admin"))
        member_repo.find_by_id = AsyncMock(return_value=target)
        member_repo.update_fields = AsyncMock()

        with _patch(ctx, redis):
            await svc.remove(MEMBER_ID, WS_ID)

        member_repo.update_fields.assert_called_once()
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_remove_denied_for_member(self):
        svc, member_repo, _ = _member_svc(actor_role="member")
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="member"))

        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.remove(MEMBER_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_remove_owner_requires_owner_actor(self):
        svc, member_repo, _ = _member_svc(actor_role="admin")
        redis = _make_redis()
        ctx = _make_ctx()

        target_owner = _member(id=MEMBER_ID, user_id=OTHER_USER, role="owner")
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="admin"))
        member_repo.find_by_id = AsyncMock(return_value=target_owner)

        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.remove(MEMBER_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_remove_owner_by_owner_allowed(self):
        svc, member_repo, _ = _member_svc(actor_role="owner")
        redis = _make_redis()
        ctx = _make_ctx()

        target_owner = _member(id=MEMBER_ID, user_id=OTHER_USER, role="owner")
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="owner"))
        member_repo.find_by_id = AsyncMock(return_value=target_owner)
        member_repo.update_fields = AsyncMock()

        with _patch(ctx, redis):
            await svc.remove(MEMBER_ID, WS_ID)

        member_repo.update_fields.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_not_found(self):
        svc, member_repo, _ = _member_svc(actor_role="admin")
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="admin"))
        member_repo.find_by_id = AsyncMock(return_value=None)

        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.remove(MEMBER_ID, WS_ID)


# ── TestChangeRole ────────────────────────────────────────────────────────────

class TestChangeRole:
    @pytest.mark.asyncio
    async def test_change_role_success(self):
        svc, member_repo, _ = _member_svc(actor_role="admin")
        redis = _make_redis()
        ctx = _make_ctx()

        target = _member(id=MEMBER_ID, user_id=OTHER_USER, role="viewer")
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="admin"))
        member_repo.find_by_id = AsyncMock(return_value=target)
        member_repo.update_fields = AsyncMock()

        data = MemberRoleUpdate(role="member")
        with _patch(ctx, redis):
            result = await svc.change_role(MEMBER_ID, WS_ID, data)

        assert result.role == "member"
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_change_role_denied_for_member(self):
        svc, member_repo, _ = _member_svc(actor_role="member")
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="member"))

        data = MemberRoleUpdate(role="admin")
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.change_role(MEMBER_ID, WS_ID, data)

    @pytest.mark.asyncio
    async def test_promote_to_owner_requires_owner_actor(self):
        svc, member_repo, _ = _member_svc(actor_role="admin")
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="admin"))

        data = MemberRoleUpdate(role="owner")
        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.change_role(MEMBER_ID, WS_ID, data)

    @pytest.mark.asyncio
    async def test_change_role_not_found(self):
        svc, member_repo, _ = _member_svc(actor_role="admin")
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="admin"))
        member_repo.find_by_id = AsyncMock(return_value=None)

        from corpmind.core.exceptions import NotFoundError
        data = MemberRoleUpdate(role="member")
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.change_role(MEMBER_ID, WS_ID, data)


# ── TestListMembers ───────────────────────────────────────────────────────────

class TestListMembers:
    @pytest.mark.asyncio
    async def test_list_from_db(self):
        svc, member_repo, _ = _member_svc()
        redis = _make_redis()
        ctx = _make_ctx()
        members = [_member(id=uuid.uuid4(), user_id=uuid.uuid4()) for _ in range(3)]
        member_repo.list_active = AsyncMock(return_value=members)

        with _patch(ctx, redis):
            result = await svc.list_members(WS_ID)

        assert result.total == 3
        assert len(result.items) == 3
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_from_cache(self):
        svc, member_repo, _ = _member_svc()
        cached = MemberListOut(items=[], total=0).model_dump_json()
        redis = _make_redis(cached_value=cached)
        ctx = _make_ctx()

        with _patch(ctx, redis):
            result = await svc.list_members(WS_ID)

        assert result.total == 0
        member_repo.list_active.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_redis_error_falls_back_to_db(self):
        svc, member_repo, _ = _member_svc()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        ctx = _make_ctx()
        member_repo.list_active = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            result = await svc.list_members(WS_ID)

        assert result.total == 0
        member_repo.list_active.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_empty_workspace(self):
        svc, member_repo, _ = _member_svc()
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.list_active = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            result = await svc.list_members(WS_ID)

        assert result.total == 0
        assert result.items == []


# ── TestCommentCreate ─────────────────────────────────────────────────────────

class TestCommentCreate:
    @pytest.mark.asyncio
    async def test_create_comment_success(self):
        svc, comment_repo, activity_repo = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        # member_repo inside comment service — needs to be patched too
        member_repo_mock = MagicMock()
        member_repo_mock.find_active_by_user = AsyncMock(return_value=_member(role="member"))

        async def fake_create(c):
            c.created_at = NOW
            return c
        comment_repo.create = AsyncMock(side_effect=fake_create)

        data = CommentIn(body="Great task!")
        with _patch(ctx, redis):
            with patch("corpmind.modules.team.service.WorkspaceMemberRepo", return_value=member_repo_mock):
                result = await svc.create(TASK_ID, WS_ID, data)

        assert result.body == "Great task!"
        assert result.author_user_id == str(USER_ID)
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_create_comment_denied_for_viewer(self):
        svc, comment_repo, _ = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        member_repo_mock = MagicMock()
        member_repo_mock.find_active_by_user = AsyncMock(return_value=_member(role="viewer"))

        data = CommentIn(body="I want to comment")
        with _patch(ctx, redis):
            with patch("corpmind.modules.team.service.WorkspaceMemberRepo", return_value=member_repo_mock):
                with pytest.raises(PermissionDeniedError):
                    await svc.create(TASK_ID, WS_ID, data)

    @pytest.mark.asyncio
    async def test_create_comment_no_membership_is_viewer(self):
        svc, comment_repo, _ = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        member_repo_mock = MagicMock()
        member_repo_mock.find_active_by_user = AsyncMock(return_value=None)  # no membership

        data = CommentIn(body="Test")
        with _patch(ctx, redis):
            with patch("corpmind.modules.team.service.WorkspaceMemberRepo", return_value=member_repo_mock):
                with pytest.raises(PermissionDeniedError):
                    await svc.create(TASK_ID, WS_ID, data)

    @pytest.mark.asyncio
    async def test_create_comment_owner_allowed(self):
        svc, comment_repo, activity_repo = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        member_repo_mock = MagicMock()
        member_repo_mock.find_active_by_user = AsyncMock(return_value=_member(role="owner"))

        async def fake_create(c):
            c.created_at = NOW
            return c
        comment_repo.create = AsyncMock(side_effect=fake_create)

        data = CommentIn(body="LGTM")
        with _patch(ctx, redis):
            with patch("corpmind.modules.team.service.WorkspaceMemberRepo", return_value=member_repo_mock):
                result = await svc.create(TASK_ID, WS_ID, data)

        assert result.body == "LGTM"


# ── TestCommentDeleteOwn ──────────────────────────────────────────────────────

class TestCommentDeleteOwn:
    @pytest.mark.asyncio
    async def test_delete_own_comment_success(self):
        svc, comment_repo, _ = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        own_comment = _comment(author_user_id=str(USER_ID))
        comment_repo.find_by_id = AsyncMock(return_value=own_comment)
        comment_repo.delete = AsyncMock()

        with _patch(ctx, redis):
            await svc.delete_own(COMMENT_ID, WS_ID)

        comment_repo.delete.assert_called_once_with(COMMENT_ID)
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_delete_other_comment_denied(self):
        svc, comment_repo, _ = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        other_comment = _comment(author_user_id=str(OTHER_USER))
        comment_repo.find_by_id = AsyncMock(return_value=other_comment)

        with _patch(ctx, redis):
            with pytest.raises(PermissionDeniedError):
                await svc.delete_own(COMMENT_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        svc, comment_repo, _ = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()
        comment_repo.find_by_id = AsyncMock(return_value=None)

        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.delete_own(COMMENT_ID, WS_ID)

    @pytest.mark.asyncio
    async def test_delete_wrong_workspace(self):
        svc, comment_repo, _ = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        wrong_ws = _comment()
        wrong_ws.workspace_id = uuid.uuid4()  # different workspace
        wrong_ws.author_user_id = str(USER_ID)
        comment_repo.find_by_id = AsyncMock(return_value=wrong_ws)

        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.delete_own(COMMENT_ID, WS_ID)


# ── TestListComments ──────────────────────────────────────────────────────────

class TestListComments:
    @pytest.mark.asyncio
    async def test_list_from_db(self):
        svc, comment_repo, _ = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        comments = [_comment(id=uuid.uuid4()) for _ in range(3)]
        comment_repo.list_for_task = AsyncMock(return_value=comments)

        with _patch(ctx, redis):
            result = await svc.list(TASK_ID, WS_ID)

        assert len(result) == 3
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_from_cache(self):
        svc, comment_repo, _ = _comment_svc()

        cached_items = [
            {
                "id": str(COMMENT_ID),
                "task_id": str(TASK_ID),
                "workspace_id": str(WS_ID),
                "author_user_id": str(USER_ID),
                "body": "Cached",
                "created_at": NOW.isoformat(),
            }
        ]
        redis = _make_redis(cached_value=json.dumps(cached_items))
        ctx = _make_ctx()

        with _patch(ctx, redis):
            result = await svc.list(TASK_ID, WS_ID)

        assert len(result) == 1
        assert result[0].body == "Cached"
        comment_repo.list_for_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_empty(self):
        svc, comment_repo, _ = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()
        comment_repo.list_for_task = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            result = await svc.list(TASK_ID, WS_ID)

        assert result == []


# ── TestActivityFeedService ───────────────────────────────────────────────────

class TestActivityLogEvent:
    @pytest.mark.asyncio
    async def test_log_creates_entry(self):
        svc, feed_repo = _activity_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        async def fake_create(e):
            e.created_at = NOW
            return e
        feed_repo.create = AsyncMock(side_effect=fake_create)

        with _patch(ctx, redis):
            await svc.log_event(
                workspace_id=WS_ID,
                entity_type="task",
                entity_id=TASK_ID,
                action="task.created",
                meta={"title": "Test"},
            )

        feed_repo.create.assert_called_once()
        redis.delete.assert_called()  # invalidates first page cache

    @pytest.mark.asyncio
    async def test_log_redis_failure_silent(self):
        svc, feed_repo = _activity_svc()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))
        ctx = _make_ctx()

        async def fake_create(e):
            e.created_at = NOW
            return e
        feed_repo.create = AsyncMock(side_effect=fake_create)

        with _patch(ctx, redis):
            # Should not raise even if Redis fails
            await svc.log_event(WS_ID, "task", None, "task.completed")

        feed_repo.create.assert_called_once()


class TestActivityListPage:
    @pytest.mark.asyncio
    async def test_first_page_from_db(self):
        svc, feed_repo = _activity_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        entries = [_feed_entry() for _ in range(5)]
        feed_repo.list_page = AsyncMock(return_value=(entries, None))

        with _patch(ctx, redis):
            result = await svc.list_page(WS_ID)

        assert len(result.items) == 5
        assert result.has_more is False
        assert result.next_cursor is None
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_first_page_from_cache(self):
        svc, feed_repo = _activity_svc()
        page = ActivityFeedPage(items=[], next_cursor=None, has_more=False)
        redis = _make_redis(cached_value=page.model_dump_json())
        ctx = _make_ctx()

        with _patch(ctx, redis):
            result = await svc.list_page(WS_ID)

        assert result.has_more is False
        feed_repo.list_page.assert_not_called()

    @pytest.mark.asyncio
    async def test_subsequent_page_skips_cache(self):
        svc, feed_repo = _activity_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        entries = [_feed_entry() for _ in range(3)]
        feed_repo.list_page = AsyncMock(return_value=(entries, None))

        with _patch(ctx, redis):
            result = await svc.list_page(WS_ID, cursor="some-cursor")

        # Not cached for non-first pages
        redis.set.assert_not_called()
        assert len(result.items) == 3

    @pytest.mark.asyncio
    async def test_has_more_when_next_cursor_present(self):
        svc, feed_repo = _activity_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        entries = [_feed_entry() for _ in range(50)]
        fake_cursor = "abc123"
        feed_repo.list_page = AsyncMock(return_value=(entries, fake_cursor))

        with _patch(ctx, redis):
            result = await svc.list_page(WS_ID)

        assert result.has_more is True
        assert result.next_cursor == fake_cursor

    @pytest.mark.asyncio
    async def test_empty_activity_feed(self):
        svc, feed_repo = _activity_svc()
        redis = _make_redis()
        ctx = _make_ctx()
        feed_repo.list_page = AsyncMock(return_value=([], None))

        with _patch(ctx, redis):
            result = await svc.list_page(WS_ID)

        assert result.items == []
        assert result.has_more is False


# ── TestCursorPagination ──────────────────────────────────────────────────────

class TestCursorPagination:
    def test_cursor_encode_decode(self):
        """Cursor round-trips correctly through base64 encoding."""
        ts = NOW
        entry_id = uuid.uuid4()
        raw = f"{ts.isoformat()}|{entry_id}"
        cursor = base64.b64encode(raw.encode()).decode()
        decoded = base64.b64decode(cursor.encode()).decode()
        ts_str, id_str = decoded.split("|", 1)
        assert datetime.fromisoformat(ts_str) == ts
        assert uuid.UUID(id_str) == entry_id

    def test_cursor_is_opaque_string(self):
        ts = NOW
        entry_id = uuid.uuid4()
        raw = f"{ts.isoformat()}|{entry_id}"
        cursor = base64.b64encode(raw.encode()).decode()
        # Cursor should look like base64, not raw timestamp
        assert "|" not in cursor
        assert " " not in cursor


# ── TestTenantIsolation ───────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_list_members_uses_org_id_in_cache_key(self):
        """Cache key must include org_id to prevent cross-tenant cache hits."""
        svc, member_repo, _ = _member_svc()
        redis = _make_redis()
        ctx = _make_ctx()
        member_repo.list_active = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            await svc.list_members(WS_ID)

        call_args = redis.set.call_args
        cache_key = call_args[0][0]
        assert str(ORG_ID) in cache_key

    @pytest.mark.asyncio
    async def test_different_org_different_cache_key(self):
        """Two tenants with the same workspace_id get different cache keys."""
        svc, _, _ = _member_svc()

        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        key_a = svc._members_key(org_a, WS_ID)
        key_b = svc._members_key(org_b, WS_ID)
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_comments_key_includes_task_id(self):
        """Comment cache key is scoped to both workspace and task."""
        svc, _, _ = _comment_svc()
        task_a = uuid.uuid4()
        task_b = uuid.uuid4()
        key_a = svc._comments_key(ORG_ID, WS_ID, task_a)
        key_b = svc._comments_key(ORG_ID, WS_ID, task_b)
        assert key_a != key_b

    def test_member_out_model_has_tenant_scoped_fields(self):
        m = _member()
        out = WorkspaceMemberOut.model_validate(m)
        assert out.workspace_id == WS_ID

    @pytest.mark.asyncio
    async def test_comment_delete_rejects_wrong_workspace(self):
        svc, comment_repo, _ = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        wrong_ws = _comment()
        wrong_ws.workspace_id = uuid.uuid4()
        wrong_ws.author_user_id = str(USER_ID)
        comment_repo.find_by_id = AsyncMock(return_value=wrong_ws)

        from corpmind.core.exceptions import NotFoundError
        with _patch(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.delete_own(COMMENT_ID, WS_ID)


# ── TestInvalidation ──────────────────────────────────────────────────────────

class TestInvalidation:
    @pytest.mark.asyncio
    async def test_invite_invalidates_members_cache(self):
        svc, member_repo, activity_repo = _member_svc(actor_role="admin")
        redis = _make_redis()
        ctx = _make_ctx()

        member_repo.find_active_by_user = AsyncMock(side_effect=[
            _member(role="admin"),
            None,
        ])

        async def fake_create(m):
            m.invited_at = NOW
            return m
        member_repo.create = AsyncMock(side_effect=fake_create)

        with _patch(ctx, redis):
            await svc.invite(MemberInviteIn(workspace_id=WS_ID, user_id=OTHER_USER))

        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_remove_invalidates_cache(self):
        svc, member_repo, _ = _member_svc(actor_role="admin")
        redis = _make_redis()
        ctx = _make_ctx()

        target = _member(user_id=OTHER_USER, role="member")
        member_repo.find_active_by_user = AsyncMock(return_value=_member(role="admin"))
        member_repo.find_by_id = AsyncMock(return_value=target)
        member_repo.update_fields = AsyncMock()

        with _patch(ctx, redis):
            await svc.remove(MEMBER_ID, WS_ID)

        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_create_comment_invalidates_comments_cache(self):
        svc, comment_repo, activity_repo = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        member_repo_mock = MagicMock()
        member_repo_mock.find_active_by_user = AsyncMock(return_value=_member(role="member"))

        async def fake_create(c):
            c.created_at = NOW
            return c
        comment_repo.create = AsyncMock(side_effect=fake_create)

        with _patch(ctx, redis):
            with patch("corpmind.modules.team.service.WorkspaceMemberRepo", return_value=member_repo_mock):
                await svc.create(TASK_ID, WS_ID, CommentIn(body="Hello"))

        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_delete_comment_invalidates_cache(self):
        svc, comment_repo, _ = _comment_svc()
        redis = _make_redis()
        ctx = _make_ctx()

        own = _comment(author_user_id=str(USER_ID))
        comment_repo.find_by_id = AsyncMock(return_value=own)
        comment_repo.delete = AsyncMock()

        with _patch(ctx, redis):
            await svc.delete_own(COMMENT_ID, WS_ID)

        redis.delete.assert_called()
