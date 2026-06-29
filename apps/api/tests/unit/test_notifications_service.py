"""Unit tests for notification center services — Sprint 32.

Covers:
- NotificationService: create, mark_read, mark_all_read, delete
- NotificationService: unread_count, list_notifications
- Permission checks (own vs other user's notifications)
- Redis cache hit / miss / invalidation
- Tenant isolation
- Schema validators
- Cache resilience (Redis errors)
- State transitions and idempotency
"""

from __future__ import annotations

import base64
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.notifications.schemas import (
    NotificationIn,
    NotificationListPage,
    NotificationOut,
    UnreadCountOut,
)
from corpmind.modules.notifications.service import (
    NotificationService,
    PermissionDeniedError,
    _count_key,
    _list_key,
)

# ── Constants ──────────────────────────────────────────────────────────────────

ORG_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WS_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
OTHER_USER = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
NOTIF_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
NOTIF_ID_2 = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
ENTITY_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

NOW = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)


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


def _notification(
    id: uuid.UUID = NOTIF_ID,
    workspace_id: uuid.UUID = WS_ID,
    user_id: uuid.UUID = USER_ID,
    notification_type: str = "approval_assigned",
    title: str = "Test notification",
    message: str = "You have a new approval request",
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    priority: str = "medium",
    is_read: bool = False,
    read_at: datetime | None = None,
    extra_data: dict[str, Any] | None = None,
) -> MagicMock:
    n = MagicMock()
    n.id = id
    n.tenant_id = ORG_ID
    n.workspace_id = workspace_id
    n.user_id = user_id
    n.notification_type = notification_type
    n.title = title
    n.message = message
    n.entity_type = entity_type
    n.entity_id = entity_id
    n.priority = priority
    n.is_read = is_read
    n.read_at = read_at
    n.extra_data = extra_data
    n.created_at = NOW
    return n


def _svc(session: MagicMock) -> NotificationService:
    return NotificationService(session)


@contextmanager
def _patch(ctx: MagicMock, redis: MagicMock):
    with (
        patch(
            "corpmind.modules.notifications.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.notifications.repo.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.notifications.service.get_redis",
            return_value=redis,
        ),
    ):
        yield


# ── Schema tests ───────────────────────────────────────────────────────────────

class TestSchemas:
    def test_valid_notification_type_accepted(self) -> None:
        data = NotificationIn(
            workspace_id=WS_ID,
            user_id=USER_ID,
            notification_type="approval_assigned",
            title="Title",
            message="Body",
        )
        assert data.notification_type == "approval_assigned"

    def test_invalid_notification_type_raises(self) -> None:
        with pytest.raises(Exception, match="notification_type"):
            NotificationIn(
                workspace_id=WS_ID,
                user_id=USER_ID,
                notification_type="bogus_type",
                title="Title",
                message="Body",
            )

    @pytest.mark.parametrize(
        "ntype",
        [
            "approval_assigned",
            "approval_completed",
            "task_assigned",
            "task_completed",
            "recommendation_created",
            "recommendation_accepted",
            "recommendation_completed",
            "campaign_launched",
            "proposal_accepted",
            "team_invited",
            "comment_added",
        ],
    )
    def test_all_valid_notification_types(self, ntype: str) -> None:
        data = NotificationIn(
            workspace_id=WS_ID,
            user_id=USER_ID,
            notification_type=ntype,
            title="Title",
            message="Body",
        )
        assert data.notification_type == ntype

    def test_invalid_priority_raises(self) -> None:
        with pytest.raises(Exception, match="priority"):
            NotificationIn(
                workspace_id=WS_ID,
                user_id=USER_ID,
                notification_type="task_assigned",
                title="Title",
                message="Body",
                priority="critical",
            )

    def test_valid_priorities_accepted(self) -> None:
        for p in ("low", "medium", "high", "urgent"):
            data = NotificationIn(
                workspace_id=WS_ID,
                user_id=USER_ID,
                notification_type="task_assigned",
                title="Title",
                message="Body",
                priority=p,
            )
            assert data.priority == p

    def test_empty_title_raises(self) -> None:
        with pytest.raises(Exception, match="title"):
            NotificationIn(
                workspace_id=WS_ID,
                user_id=USER_ID,
                notification_type="task_assigned",
                title="   ",
                message="Body",
            )

    def test_title_too_long_raises(self) -> None:
        with pytest.raises(Exception, match="255"):
            NotificationIn(
                workspace_id=WS_ID,
                user_id=USER_ID,
                notification_type="task_assigned",
                title="x" * 256,
                message="Body",
            )

    def test_empty_message_raises(self) -> None:
        with pytest.raises(Exception, match="message"):
            NotificationIn(
                workspace_id=WS_ID,
                user_id=USER_ID,
                notification_type="task_assigned",
                title="Title",
                message="   ",
            )

    def test_title_stripped(self) -> None:
        data = NotificationIn(
            workspace_id=WS_ID,
            user_id=USER_ID,
            notification_type="task_assigned",
            title="  Hello  ",
            message="Body",
        )
        assert data.title == "Hello"

    def test_notification_out_from_attributes(self) -> None:
        n = _notification()
        out = NotificationOut.model_validate(n)
        assert out.id == NOTIF_ID
        assert out.is_read is False
        assert out.priority == "medium"

    def test_unread_count_out(self) -> None:
        uc = UnreadCountOut(count=7)
        assert uc.count == 7

    def test_notification_list_page(self) -> None:
        page = NotificationListPage(items=[], next_cursor=None, has_more=False)
        assert page.has_more is False

    def test_default_priority_is_medium(self) -> None:
        data = NotificationIn(
            workspace_id=WS_ID,
            user_id=USER_ID,
            notification_type="task_assigned",
            title="Title",
            message="Body",
        )
        assert data.priority == "medium"


# ── Cache key tests ────────────────────────────────────────────────────────────

class TestCacheKeys:
    def test_list_key_format(self) -> None:
        key = _list_key(ORG_ID, WS_ID, USER_ID)
        assert f"t:{ORG_ID}:{WS_ID}:notifications:list:{USER_ID}" == key

    def test_count_key_format(self) -> None:
        key = _count_key(ORG_ID, WS_ID, USER_ID)
        assert f"t:{ORG_ID}:{WS_ID}:notifications:count:{USER_ID}" == key

    def test_different_users_produce_different_list_keys(self) -> None:
        k1 = _list_key(ORG_ID, WS_ID, USER_ID)
        k2 = _list_key(ORG_ID, WS_ID, OTHER_USER)
        assert k1 != k2

    def test_different_users_produce_different_count_keys(self) -> None:
        k1 = _count_key(ORG_ID, WS_ID, USER_ID)
        k2 = _count_key(ORG_ID, WS_ID, OTHER_USER)
        assert k1 != k2

    def test_different_workspaces_produce_different_keys(self) -> None:
        ws2 = uuid.uuid4()
        k1 = _list_key(ORG_ID, WS_ID, USER_ID)
        k2 = _list_key(ORG_ID, ws2, USER_ID)
        assert k1 != k2


# ── Create tests ───────────────────────────────────────────────────────────────

class TestCreate:
    @pytest.mark.asyncio
    async def test_create_returns_notification_out(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        created_notif = _notification()
        repo_mock = AsyncMock()
        repo_mock.create = AsyncMock(return_value=created_notif)

        svc = _svc(session)
        with _patch(ctx, redis):
            with patch.object(svc._repo, "create", repo_mock.create):
                data = NotificationIn(
                    workspace_id=WS_ID,
                    user_id=USER_ID,
                    notification_type="approval_assigned",
                    title="Test",
                    message="Body",
                )
                result = await svc.create(data)

        assert isinstance(result, NotificationOut)
        assert result.notification_type == "approval_assigned"

    @pytest.mark.asyncio
    async def test_create_sets_is_read_false(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            with patch.object(svc._repo, "create", AsyncMock(return_value=_notification(is_read=False))):
                data = NotificationIn(
                    workspace_id=WS_ID,
                    user_id=USER_ID,
                    notification_type="task_assigned",
                    title="Task",
                    message="You have a task",
                )
                result = await svc.create(data)

        assert result.is_read is False

    @pytest.mark.asyncio
    async def test_create_uses_tenant_id_from_context(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        captured: list[Any] = []

        async def _capture(n: Any) -> Any:
            captured.append(n)
            return n

        svc = _svc(session)
        with _patch(ctx, redis):
            notif = _notification()
            notif.tenant_id = ORG_ID
            with patch.object(svc._repo, "create", AsyncMock(return_value=notif)):
                data = NotificationIn(
                    workspace_id=WS_ID,
                    user_id=USER_ID,
                    notification_type="task_assigned",
                    title="Task",
                    message="Body",
                )
                result = await svc.create(data)

        assert result.tenant_id == ORG_ID

    @pytest.mark.asyncio
    async def test_create_invalidates_list_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            with patch.object(svc._repo, "create", AsyncMock(return_value=_notification())):
                data = NotificationIn(
                    workspace_id=WS_ID,
                    user_id=USER_ID,
                    notification_type="task_assigned",
                    title="T",
                    message="M",
                )
                await svc.create(data)

        redis.delete.assert_called_once()
        deleted_keys = redis.delete.call_args[0]
        assert _list_key(ORG_ID, WS_ID, USER_ID) in deleted_keys

    @pytest.mark.asyncio
    async def test_create_invalidates_count_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            with patch.object(svc._repo, "create", AsyncMock(return_value=_notification())):
                data = NotificationIn(
                    workspace_id=WS_ID,
                    user_id=USER_ID,
                    notification_type="task_assigned",
                    title="T",
                    message="M",
                )
                await svc.create(data)

        deleted_keys = redis.delete.call_args[0]
        assert _count_key(ORG_ID, WS_ID, USER_ID) in deleted_keys

    @pytest.mark.asyncio
    async def test_create_with_entity_type_and_id(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        notif = _notification(entity_type="task", entity_id=ENTITY_ID)
        svc = _svc(session)
        with _patch(ctx, redis):
            with patch.object(svc._repo, "create", AsyncMock(return_value=notif)):
                data = NotificationIn(
                    workspace_id=WS_ID,
                    user_id=USER_ID,
                    notification_type="task_assigned",
                    title="T",
                    message="M",
                    entity_type="task",
                    entity_id=ENTITY_ID,
                )
                result = await svc.create(data)

        assert result.entity_type == "task"
        assert result.entity_id == ENTITY_ID

    @pytest.mark.asyncio
    async def test_create_with_metadata(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        meta = {"campaign_id": "abc", "count": 5}
        notif = _notification(extra_data=meta)

        svc = _svc(session)
        with _patch(ctx, redis):
            with patch.object(svc._repo, "create", AsyncMock(return_value=notif)):
                data = NotificationIn(
                    workspace_id=WS_ID,
                    user_id=USER_ID,
                    notification_type="campaign_launched",
                    title="Campaign launched",
                    message="Your campaign is live",
                    extra_data=meta,
                )
                result = await svc.create(data)

        assert result.extra_data == meta

    @pytest.mark.asyncio
    async def test_create_with_urgent_priority(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(priority="urgent")

        svc = _svc(session)
        with _patch(ctx, redis):
            with patch.object(svc._repo, "create", AsyncMock(return_value=notif)):
                data = NotificationIn(
                    workspace_id=WS_ID,
                    user_id=USER_ID,
                    notification_type="approval_assigned",
                    title="T",
                    message="M",
                    priority="urgent",
                )
                result = await svc.create(data)

        assert result.priority == "urgent"


# ── Mark read tests ────────────────────────────────────────────────────────────

class TestMarkRead:
    @pytest.mark.asyncio
    async def test_mark_read_sets_is_read(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(is_read=False)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.update_fields = AsyncMock()
            result = await svc.mark_read(NOTIF_ID)

        assert result.is_read is True

    @pytest.mark.asyncio
    async def test_mark_read_sets_read_at(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(is_read=False)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.update_fields = AsyncMock()
            result = await svc.mark_read(NOTIF_ID)

        assert result.read_at is not None

    @pytest.mark.asyncio
    async def test_mark_read_not_found_raises(self) -> None:
        from corpmind.core.exceptions import NotFoundError
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=None)
            with pytest.raises(NotFoundError):
                await svc.mark_read(NOTIF_ID)

    @pytest.mark.asyncio
    async def test_mark_read_wrong_user_raises_permission_error(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(user_id=OTHER_USER)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            with pytest.raises(PermissionDeniedError):
                await svc.mark_read(NOTIF_ID)

    @pytest.mark.asyncio
    async def test_mark_read_already_read_returns_idempotent(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(is_read=True, read_at=NOW)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.update_fields = AsyncMock()
            result = await svc.mark_read(NOTIF_ID)

        assert result.is_read is True
        svc._repo.update_fields.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_read_invalidates_list_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(is_read=False)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.update_fields = AsyncMock()
            await svc.mark_read(NOTIF_ID)

        redis.delete.assert_called_once()
        keys = redis.delete.call_args[0]
        assert _list_key(ORG_ID, WS_ID, USER_ID) in keys

    @pytest.mark.asyncio
    async def test_mark_read_invalidates_count_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(is_read=False)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.update_fields = AsyncMock()
            await svc.mark_read(NOTIF_ID)

        keys = redis.delete.call_args[0]
        assert _count_key(ORG_ID, WS_ID, USER_ID) in keys


# ── Mark all read tests ────────────────────────────────────────────────────────

class TestMarkAllRead:
    @pytest.mark.asyncio
    async def test_mark_all_read_returns_count(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.mark_all_read_for_user = AsyncMock(return_value=5)
            count = await svc.mark_all_read(WS_ID)

        assert count == 5

    @pytest.mark.asyncio
    async def test_mark_all_read_returns_zero_when_none_unread(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.mark_all_read_for_user = AsyncMock(return_value=0)
            count = await svc.mark_all_read(WS_ID)

        assert count == 0

    @pytest.mark.asyncio
    async def test_mark_all_read_invalidates_list_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.mark_all_read_for_user = AsyncMock(return_value=3)
            await svc.mark_all_read(WS_ID)

        redis.delete.assert_called_once()
        keys = redis.delete.call_args[0]
        assert _list_key(ORG_ID, WS_ID, USER_ID) in keys

    @pytest.mark.asyncio
    async def test_mark_all_read_invalidates_count_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.mark_all_read_for_user = AsyncMock(return_value=3)
            await svc.mark_all_read(WS_ID)

        keys = redis.delete.call_args[0]
        assert _count_key(ORG_ID, WS_ID, USER_ID) in keys

    @pytest.mark.asyncio
    async def test_mark_all_read_passes_user_id_from_context(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        captured: list[Any] = []

        async def _cap(ws: Any, uid: Any, read_at: Any) -> int:
            captured.append((ws, uid))
            return 0

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.mark_all_read_for_user = _cap
            await svc.mark_all_read(WS_ID)

        assert captured[0][1] == USER_ID


# ── Delete tests ───────────────────────────────────────────────────────────────

class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_own_notification(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.delete_by_id = AsyncMock()
            await svc.delete(NOTIF_ID)

        svc._repo.delete_by_id.assert_called_once_with(NOTIF_ID)

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self) -> None:
        from corpmind.core.exceptions import NotFoundError
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=None)
            with pytest.raises(NotFoundError):
                await svc.delete(NOTIF_ID)

    @pytest.mark.asyncio
    async def test_delete_other_users_notification_raises(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(user_id=OTHER_USER)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            with pytest.raises(PermissionDeniedError):
                await svc.delete(NOTIF_ID)

    @pytest.mark.asyncio
    async def test_delete_invalidates_list_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.delete_by_id = AsyncMock()
            await svc.delete(NOTIF_ID)

        redis.delete.assert_called_once()
        keys = redis.delete.call_args[0]
        assert _list_key(ORG_ID, WS_ID, USER_ID) in keys

    @pytest.mark.asyncio
    async def test_delete_invalidates_count_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.delete_by_id = AsyncMock()
            await svc.delete(NOTIF_ID)

        keys = redis.delete.call_args[0]
        assert _count_key(ORG_ID, WS_ID, USER_ID) in keys


# ── Unread count tests ─────────────────────────────────────────────────────────

class TestUnreadCount:
    @pytest.mark.asyncio
    async def test_unread_count_fetches_from_db_when_no_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.unread_count = AsyncMock(return_value=3)
            result = await svc.unread_count(WS_ID)

        assert result.count == 3

    @pytest.mark.asyncio
    async def test_unread_count_uses_cache_when_present(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value="7")

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.unread_count = AsyncMock(return_value=999)
            result = await svc.unread_count(WS_ID)

        assert result.count == 7
        svc._repo.unread_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_unread_count_sets_cache_after_db_fetch(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.unread_count = AsyncMock(return_value=4)
            await svc.unread_count(WS_ID)

        redis.set.assert_called_once()
        call_args = redis.set.call_args
        assert call_args[0][0] == _count_key(ORG_ID, WS_ID, USER_ID)
        assert call_args[0][1] == "4"

    @pytest.mark.asyncio
    async def test_unread_count_uses_shorter_ttl(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.unread_count = AsyncMock(return_value=2)
            await svc.unread_count(WS_ID)

        call_args = redis.set.call_args
        assert call_args[1].get("ex") == 60  # _COUNT_TTL

    @pytest.mark.asyncio
    async def test_unread_count_returns_zero_when_none(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.unread_count = AsyncMock(return_value=0)
            result = await svc.unread_count(WS_ID)

        assert result.count == 0

    @pytest.mark.asyncio
    async def test_unread_count_handles_redis_get_failure(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("connection error"))

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.unread_count = AsyncMock(return_value=5)
            result = await svc.unread_count(WS_ID)

        assert result.count == 5

    @pytest.mark.asyncio
    async def test_unread_count_handles_redis_set_failure(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)
        redis.set = AsyncMock(side_effect=Exception("timeout"))

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.unread_count = AsyncMock(return_value=3)
            result = await svc.unread_count(WS_ID)

        assert result.count == 3

    @pytest.mark.asyncio
    async def test_unread_count_key_is_user_specific(self) -> None:
        ctx_a = _make_ctx()
        ctx_a.user_id = USER_ID
        ctx_b = _make_ctx()
        ctx_b.user_id = OTHER_USER

        key_a = _count_key(ORG_ID, WS_ID, ctx_a.user_id)
        key_b = _count_key(ORG_ID, WS_ID, ctx_b.user_id)
        assert key_a != key_b


# ── List notifications tests ───────────────────────────────────────────────────

class TestListNotifications:
    @pytest.mark.asyncio
    async def test_list_returns_page(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)
        items = [_notification()]

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=(items, None))
            result = await svc.list_notifications(WS_ID)

        assert len(result.items) == 1
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_list_first_page_is_cached(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)
        items = [_notification()]

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=(items, None))
            await svc.list_notifications(WS_ID)

        redis.set.assert_called_once()
        assert redis.set.call_args[0][0] == _list_key(ORG_ID, WS_ID, USER_ID)

    @pytest.mark.asyncio
    async def test_list_first_page_uses_list_ttl(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=([], None))
            await svc.list_notifications(WS_ID)

        assert redis.set.call_args[1].get("ex") == 300  # _LIST_TTL

    @pytest.mark.asyncio
    async def test_list_cache_hit_skips_db(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        page = NotificationListPage(items=[], next_cursor=None, has_more=False)
        redis = _make_redis(cached_value=page.model_dump_json())

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock()
            result = await svc.list_notifications(WS_ID)

        svc._repo.list_page.assert_not_called()
        assert isinstance(result, NotificationListPage)

    @pytest.mark.asyncio
    async def test_list_with_cursor_skips_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=([], None))
            await svc.list_notifications(WS_ID, cursor="some_cursor")

        redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_with_is_read_filter_skips_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=([], None))
            await svc.list_notifications(WS_ID, is_read=False)

        redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_with_priority_filter_skips_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=([], None))
            await svc.list_notifications(WS_ID, priority="urgent")

        redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_with_entity_type_filter_skips_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=([], None))
            await svc.list_notifications(WS_ID, entity_type="task")

        redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_returns_has_more_true(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)
        cursor = base64.b64encode(f"{NOW.isoformat()}|{NOTIF_ID}".encode()).decode()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=([_notification()], cursor))
            result = await svc.list_notifications(WS_ID)

        assert result.has_more is True
        assert result.next_cursor == cursor

    @pytest.mark.asyncio
    async def test_list_handles_redis_get_failure(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=([], None))
            result = await svc.list_notifications(WS_ID)

        assert isinstance(result, NotificationListPage)

    @pytest.mark.asyncio
    async def test_list_empty_returns_empty_page(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=([], None))
            result = await svc.list_notifications(WS_ID)

        assert result.items == []
        assert result.has_more is False


# ── Tenant isolation tests ─────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_create_uses_org_id_from_context(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        notif = _notification()
        notif.tenant_id = ORG_ID

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.create = AsyncMock(return_value=notif)
            data = NotificationIn(
                workspace_id=WS_ID,
                user_id=USER_ID,
                notification_type="task_assigned",
                title="T",
                message="M",
            )
            result = await svc.create(data)

        assert result.tenant_id == ORG_ID

    @pytest.mark.asyncio
    async def test_mark_read_uses_tenant_scoped_find(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=None)
            from corpmind.core.exceptions import NotFoundError
            with pytest.raises(NotFoundError):
                await svc.mark_read(NOTIF_ID)

        svc._repo.find_by_id.assert_called_once_with(NOTIF_ID)

    @pytest.mark.asyncio
    async def test_delete_uses_tenant_scoped_find(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=None)
            from corpmind.core.exceptions import NotFoundError
            with pytest.raises(NotFoundError):
                await svc.delete(NOTIF_ID)

        svc._repo.find_by_id.assert_called_once_with(NOTIF_ID)

    @pytest.mark.asyncio
    async def test_list_scoped_to_current_user(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)
        captured: list[Any] = []

        async def _cap(*args: Any, **kwargs: Any) -> Any:
            captured.append(args)
            return ([], None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = _cap
            await svc.list_notifications(WS_ID)

        # Second positional arg is user_id
        assert captured[0][1] == USER_ID

    @pytest.mark.asyncio
    async def test_unread_count_scoped_to_current_user(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)
        captured: list[Any] = []

        async def _cap(ws: Any, uid: Any) -> int:
            captured.append((ws, uid))
            return 0

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.unread_count = _cap
            await svc.unread_count(WS_ID)

        assert captured[0][1] == USER_ID

    @pytest.mark.asyncio
    async def test_mark_all_read_scoped_to_current_user(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        captured: list[Any] = []

        async def _cap(ws: Any, uid: Any, read_at: Any) -> int:
            captured.append((ws, uid))
            return 0

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.mark_all_read_for_user = _cap
            await svc.mark_all_read(WS_ID)

        assert captured[0][1] == USER_ID


# ── Cache invalidation tests ───────────────────────────────────────────────────

class TestCacheInvalidation:
    @pytest.mark.asyncio
    async def test_create_deletes_both_keys(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.create = AsyncMock(return_value=notif)
            data = NotificationIn(
                workspace_id=WS_ID,
                user_id=USER_ID,
                notification_type="task_assigned",
                title="T",
                message="M",
            )
            await svc.create(data)

        keys = redis.delete.call_args[0]
        assert _list_key(ORG_ID, WS_ID, USER_ID) in keys
        assert _count_key(ORG_ID, WS_ID, USER_ID) in keys

    @pytest.mark.asyncio
    async def test_mark_read_deletes_both_keys(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(is_read=False)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.update_fields = AsyncMock()
            await svc.mark_read(NOTIF_ID)

        keys = redis.delete.call_args[0]
        assert _list_key(ORG_ID, WS_ID, USER_ID) in keys
        assert _count_key(ORG_ID, WS_ID, USER_ID) in keys

    @pytest.mark.asyncio
    async def test_mark_all_read_deletes_both_keys(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.mark_all_read_for_user = AsyncMock(return_value=2)
            await svc.mark_all_read(WS_ID)

        keys = redis.delete.call_args[0]
        assert _list_key(ORG_ID, WS_ID, USER_ID) in keys
        assert _count_key(ORG_ID, WS_ID, USER_ID) in keys

    @pytest.mark.asyncio
    async def test_delete_deletes_both_keys(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.delete_by_id = AsyncMock()
            await svc.delete(NOTIF_ID)

        keys = redis.delete.call_args[0]
        assert _list_key(ORG_ID, WS_ID, USER_ID) in keys
        assert _count_key(ORG_ID, WS_ID, USER_ID) in keys

    @pytest.mark.asyncio
    async def test_redis_delete_failure_does_not_raise(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("connection lost"))
        notif = _notification()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.delete_by_id = AsyncMock()
            await svc.delete(NOTIF_ID)  # must not raise


# ── Cache resilience tests ─────────────────────────────────────────────────────

class TestCacheResilience:
    @pytest.mark.asyncio
    async def test_list_redis_get_failure_falls_back_to_db(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("redis unavailable"))
        items = [_notification()]

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=(items, None))
            result = await svc.list_notifications(WS_ID)

        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_list_redis_set_failure_returns_db_result(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)
        redis.set = AsyncMock(side_effect=Exception("oom"))

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=([], None))
            result = await svc.list_notifications(WS_ID)

        assert isinstance(result, NotificationListPage)

    @pytest.mark.asyncio
    async def test_count_redis_get_failure_falls_back_to_db(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("timeout"))

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.unread_count = AsyncMock(return_value=3)
            result = await svc.unread_count(WS_ID)

        assert result.count == 3

    @pytest.mark.asyncio
    async def test_invalidate_redis_failure_does_not_raise(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("network"))
        notif = _notification()

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.create = AsyncMock(return_value=notif)
            data = NotificationIn(
                workspace_id=WS_ID,
                user_id=USER_ID,
                notification_type="task_assigned",
                title="T",
                message="M",
            )
            # must not raise even though Redis is down
            result = await svc.create(data)

        assert isinstance(result, NotificationOut)


# ── Permission check tests ─────────────────────────────────────────────────────

class TestPermissions:
    @pytest.mark.asyncio
    async def test_mark_read_own_notification_succeeds(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(user_id=USER_ID, is_read=False)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.update_fields = AsyncMock()
            result = await svc.mark_read(NOTIF_ID)

        assert result.is_read is True

    @pytest.mark.asyncio
    async def test_mark_read_other_user_raises(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(user_id=OTHER_USER)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            with pytest.raises(PermissionDeniedError, match="own"):
                await svc.mark_read(NOTIF_ID)

    @pytest.mark.asyncio
    async def test_delete_own_notification_succeeds(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(user_id=USER_ID)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.delete_by_id = AsyncMock()
            await svc.delete(NOTIF_ID)

        svc._repo.delete_by_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_other_user_notification_raises(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(user_id=OTHER_USER)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            with pytest.raises(PermissionDeniedError, match="own"):
                await svc.delete(NOTIF_ID)

    @pytest.mark.asyncio
    async def test_list_scoped_to_authenticated_user(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)
        captured_user_ids: list[Any] = []

        async def _cap(ws: Any, uid: Any, *a: Any, **kw: Any) -> Any:
            captured_user_ids.append(uid)
            return ([], None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = _cap
            await svc.list_notifications(WS_ID)

        assert captured_user_ids[0] == USER_ID


# ── Additional edge case tests ─────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_create_with_null_entity_fields(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(entity_type=None, entity_id=None, extra_data=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.create = AsyncMock(return_value=notif)
            data = NotificationIn(
                workspace_id=WS_ID,
                user_id=USER_ID,
                notification_type="team_invited",
                title="Invited",
                message="Join the team",
            )
            result = await svc.create(data)

        assert result.entity_type is None
        assert result.entity_id is None
        assert result.extra_data is None

    @pytest.mark.asyncio
    async def test_mark_read_already_read_does_not_update_db(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        notif = _notification(is_read=True, read_at=NOW)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.find_by_id = AsyncMock(return_value=notif)
            svc._repo.update_fields = AsyncMock()
            await svc.mark_read(NOTIF_ID)

        svc._repo.update_fields.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_all_filters_active_skips_cache(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = AsyncMock(return_value=([], None))
            await svc.list_notifications(
                WS_ID,
                cursor="c",
                is_read=False,
                priority="urgent",
                entity_type="task",
            )

        redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_all_read_is_idempotent(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()
        call_counts = [0]

        async def _cap(ws: Any, uid: Any, read_at: Any) -> int:
            call_counts[0] += 1
            return 0

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.mark_all_read_for_user = _cap
            count1 = await svc.mark_all_read(WS_ID)
            count2 = await svc.mark_all_read(WS_ID)

        assert count1 == 0
        assert count2 == 0
        assert call_counts[0] == 2

    @pytest.mark.asyncio
    async def test_list_with_read_filter_true(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)
        captured: list[Any] = []

        async def _cap(ws: Any, uid: Any, lim: Any, cur: Any, is_read: Any = None, priority: Any = None, entity_type: Any = None) -> Any:
            captured.append(is_read)
            return ([], None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = _cap
            await svc.list_notifications(WS_ID, is_read=True)

        assert captured[0] is True

    @pytest.mark.asyncio
    async def test_list_with_unread_filter(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis(cached_value=None)
        captured: list[Any] = []

        async def _cap(ws: Any, uid: Any, lim: Any, cur: Any, is_read: Any = None, priority: Any = None, entity_type: Any = None) -> Any:
            captured.append(is_read)
            return ([], None)

        svc = _svc(session)
        with _patch(ctx, redis):
            svc._repo.list_page = _cap
            await svc.list_notifications(WS_ID, is_read=False)

        assert captured[0] is False

    @pytest.mark.asyncio
    async def test_create_different_notification_types(self) -> None:
        session = MagicMock()
        ctx = _make_ctx()
        redis = _make_redis()

        for ntype in ("proposal_accepted", "recommendation_completed", "comment_added"):
            notif = _notification(notification_type=ntype)
            svc = _svc(session)
            with _patch(ctx, redis):
                svc._repo.create = AsyncMock(return_value=notif)
                data = NotificationIn(
                    workspace_id=WS_ID,
                    user_id=USER_ID,
                    notification_type=ntype,
                    title="Title",
                    message="Body",
                )
                result = await svc.create(data)
            assert result.notification_type == ntype
