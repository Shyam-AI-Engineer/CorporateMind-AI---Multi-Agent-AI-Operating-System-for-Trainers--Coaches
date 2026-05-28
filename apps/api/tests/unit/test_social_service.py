"""Unit tests for SocialService.

Mocks: DB session, SocialPostRepo.
Tests cover status derivation, recipient persistence, list pagination,
and the delete-status guard.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from corpmind.core.exceptions import ConflictError, NotFoundError
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.social.models import SocialPost
from corpmind.modules.social.schemas import SocialPostCreate
from corpmind.modules.social.service import SocialService

# ── Fixtures ───────────────────────────────────────────────────────────────────

_ORG_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_POST_ID = uuid.uuid4()

_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="trainer",
    request_id="req-social-test-001",
)


def _make_post(
    status: str = "draft",
    channel: str = "linkedin",
    content: str = "Hello world",
    hashtags: list[str] | None = None,
    scheduled_at: datetime | None = None,
) -> SocialPost:
    p = SocialPost(
        tenant_id=_ORG_ID,
        workspace_id=_WS_ID,
        channel=channel,
        content=content,
        hashtags=hashtags or [],
        status=status,
        scheduled_at=scheduled_at,
    )
    p.id = _POST_ID
    p.media_urls = []
    p.provider_post_id = None
    p.published_at = None
    p.created_at = datetime.now(UTC)
    return p


def _make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


def _attach_create(svc: SocialService) -> list[SocialPost]:
    """Patches svc._repo.create to populate id/timestamps and captures the post."""
    captured: list[SocialPost] = []

    async def _create(post: SocialPost) -> SocialPost:
        post.id = _POST_ID
        post.media_urls = []
        post.provider_post_id = None
        post.published_at = None
        post.created_at = datetime.now(UTC)
        captured.append(post)
        return post

    svc._repo.create = _create  # type: ignore[method-assign]
    return captured


# ── Tests: schedule_post ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_post_future_date_marks_scheduled():
    """A future scheduled_at yields status='scheduled'."""
    token = set_tenant_context(_CTX)
    svc = SocialService(_make_session())
    captured = _attach_create(svc)

    future = datetime.now(UTC) + timedelta(hours=2)
    req = SocialPostCreate(
        workspace_id=_WS_ID, channel="linkedin", content="Future post", scheduled_at=future
    )

    result = await svc.schedule_post(req)

    clear_tenant_context(token)
    assert result.status == "scheduled"
    assert captured[0].status == "scheduled"
    assert captured[0].scheduled_at == future


@pytest.mark.asyncio
async def test_schedule_post_past_date_marks_draft():
    """A scheduled_at in the past yields status='draft' (treated as backdated draft)."""
    token = set_tenant_context(_CTX)
    svc = SocialService(_make_session())
    _attach_create(svc)

    past = datetime.now(UTC) - timedelta(hours=1)
    req = SocialPostCreate(
        workspace_id=_WS_ID, channel="linkedin", content="Past date", scheduled_at=past
    )

    result = await svc.schedule_post(req)

    clear_tenant_context(token)
    assert result.status == "draft"


@pytest.mark.asyncio
async def test_schedule_post_no_date_marks_draft():
    """A missing scheduled_at yields status='draft'."""
    token = set_tenant_context(_CTX)
    svc = SocialService(_make_session())
    _attach_create(svc)

    req = SocialPostCreate(workspace_id=_WS_ID, channel="instagram", content="Draft only")
    result = await svc.schedule_post(req)

    clear_tenant_context(token)
    assert result.status == "draft"
    assert result.scheduled_at is None


@pytest.mark.asyncio
async def test_schedule_post_persists_channel_content_hashtags():
    """Channel, content, and hashtags are passed through to the stored post."""
    token = set_tenant_context(_CTX)
    svc = SocialService(_make_session())
    captured = _attach_create(svc)

    req = SocialPostCreate(
        workspace_id=_WS_ID,
        channel="facebook",
        content="Big launch announcement",
        hashtags=["launch", "ai"],
    )
    await svc.schedule_post(req)

    clear_tenant_context(token)
    assert captured[0].channel == "facebook"
    assert captured[0].content == "Big launch announcement"
    assert captured[0].hashtags == ["launch", "ai"]


@pytest.mark.asyncio
async def test_schedule_post_commits_session():
    """schedule_post commits the session so the post is durable."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = SocialService(session)
    _attach_create(svc)

    req = SocialPostCreate(workspace_id=_WS_ID, channel="telegram", content="Hello")
    await svc.schedule_post(req)

    clear_tenant_context(token)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_schedule_post_tenant_id_from_context():
    """The tenant_id on the persisted post comes from TenantContext, not the request."""
    token = set_tenant_context(_CTX)
    svc = SocialService(_make_session())
    captured = _attach_create(svc)

    req = SocialPostCreate(workspace_id=_WS_ID, channel="linkedin", content="Test")
    await svc.schedule_post(req)

    clear_tenant_context(token)
    assert captured[0].tenant_id == _ORG_ID


# ── Tests: list_posts ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_posts_returns_items_with_total():
    """list_posts serialises posts and reports total + pagination."""
    token = set_tenant_context(_CTX)
    svc = SocialService(_make_session())

    svc._repo.list_by_workspace = AsyncMock(
        return_value=[_make_post("draft"), _make_post("scheduled")]
    )
    svc._repo.count_by_workspace = AsyncMock(return_value=2)

    result = await svc.list_posts(_WS_ID, limit=10, offset=0)

    clear_tenant_context(token)
    assert result.total == 2
    assert result.limit == 10
    assert result.offset == 0
    assert {p.status for p in result.items} == {"draft", "scheduled"}


@pytest.mark.asyncio
async def test_list_posts_empty():
    """list_posts returns an empty list when workspace has no posts."""
    token = set_tenant_context(_CTX)
    svc = SocialService(_make_session())

    svc._repo.list_by_workspace = AsyncMock(return_value=[])
    svc._repo.count_by_workspace = AsyncMock(return_value=0)

    result = await svc.list_posts(_WS_ID)

    clear_tenant_context(token)
    assert result.total == 0
    assert result.items == []


# ── Tests: delete_post ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_post_draft_succeeds():
    """A draft post can be deleted."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = SocialService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_post("draft"))
    svc._repo.delete = AsyncMock()

    await svc.delete_post(_POST_ID)

    clear_tenant_context(token)
    svc._repo.delete.assert_awaited_once_with(_POST_ID)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_post_scheduled_succeeds():
    """A scheduled post can be deleted before publication."""
    token = set_tenant_context(_CTX)
    svc = SocialService(_make_session())

    svc._repo.find_by_id = AsyncMock(return_value=_make_post("scheduled"))
    svc._repo.delete = AsyncMock()

    await svc.delete_post(_POST_ID)

    clear_tenant_context(token)
    svc._repo.delete.assert_awaited_once_with(_POST_ID)


@pytest.mark.asyncio
async def test_delete_post_published_raises_conflict():
    """A published post cannot be deleted — that would rewrite history."""
    token = set_tenant_context(_CTX)
    svc = SocialService(_make_session())

    svc._repo.find_by_id = AsyncMock(return_value=_make_post("published"))
    svc._repo.delete = AsyncMock()

    with pytest.raises(ConflictError, match="published"):
        await svc.delete_post(_POST_ID)

    clear_tenant_context(token)
    svc._repo.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_post_failed_raises_conflict():
    """A failed post is still a historical record — block delete."""
    token = set_tenant_context(_CTX)
    svc = SocialService(_make_session())

    svc._repo.find_by_id = AsyncMock(return_value=_make_post("failed"))
    svc._repo.delete = AsyncMock()

    with pytest.raises(ConflictError):
        await svc.delete_post(_POST_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_delete_post_not_found_raises():
    """NotFoundError when the post does not exist (or belongs to another tenant)."""
    token = set_tenant_context(_CTX)
    svc = SocialService(_make_session())

    svc._repo.find_by_id = AsyncMock(return_value=None)
    svc._repo.delete = AsyncMock()

    with pytest.raises(NotFoundError):
        await svc.delete_post(_POST_ID)

    clear_tenant_context(token)
    svc._repo.delete.assert_not_awaited()
