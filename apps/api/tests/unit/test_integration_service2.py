"""Unit tests — Sprint 55: Integration Hub (part 2).

Additional coverage for update_webhook, delete_webhook, validation,
tenant isolation, model fields, and edge cases.
Run: uv run pytest tests/unit/test_integration_service2.py -q
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.integrations.models import ApiKey, Webhook
from corpmind.modules.integrations.schemas import (
    SUPPORTED_WEBHOOK_EVENTS,
    ApiKeyOut,
    WebhookListOut,
    WebhookOut,
    WebhookUpdate,
)
from corpmind.modules.integrations.service import (
    IntegrationService,
    _api_keys_cache_key,
    _webhooks_cache_key,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_ORG_ID = uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001")
_WS_ID = uuid.UUID("bbbbbbbb-1111-0000-0000-000000000002")
_USER_ID = uuid.UUID("cccccccc-1111-0000-0000-000000000003")
_HOOK_ID = uuid.UUID("eeeeeeee-1111-0000-0000-000000000005")
_KEY_ID = uuid.UUID("dddddddd-1111-0000-0000-000000000004")

_PATCH_CTX = "corpmind.modules.integrations.service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.integrations.service.get_redis"


def _mock_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = _ORG_ID
    ctx.user_id = _USER_ID
    return ctx


def _make_orm_key(**kwargs) -> MagicMock:
    defaults = dict(
        id=_KEY_ID,
        tenant_id=_ORG_ID,
        workspace_id=_WS_ID,
        name="Key A",
        key_prefix="11223344",
        key_hash="b" * 64,
        last_used_at=None,
        expires_at=None,
        is_active=True,
        created_by=_USER_ID,
        created_at=datetime(2026, 7, 8, tzinfo=UTC),
    )
    defaults.update(kwargs)
    m = MagicMock(spec=ApiKey)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _make_orm_webhook(**kwargs) -> MagicMock:
    defaults = dict(
        id=_HOOK_ID,
        tenant_id=_ORG_ID,
        workspace_id=_WS_ID,
        name="Hook B",
        url="https://b.example.com/wh",
        secret="sec" * 20,
        events=["invoice.paid"],
        is_active=True,
        last_delivery_at=None,
        created_by=_USER_ID,
        created_at=datetime(2026, 7, 8, tzinfo=UTC),
    )
    defaults.update(kwargs)
    m = MagicMock(spec=Webhook)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _make_svc() -> tuple[IntegrationService, MagicMock]:
    session = AsyncMock()
    svc = IntegrationService(session)
    mock_repo = MagicMock()
    mock_repo.create_api_key = AsyncMock()
    mock_repo.find_api_key_by_id = AsyncMock(return_value=None)
    mock_repo.find_api_keys = AsyncMock(return_value=[])
    mock_repo.update_api_key = AsyncMock(return_value=None)
    mock_repo.create_webhook = AsyncMock()
    mock_repo.find_webhook_by_id = AsyncMock(return_value=None)
    mock_repo.find_webhooks = AsyncMock(return_value=[])
    mock_repo.update_webhook = AsyncMock(return_value=None)
    mock_repo.delete_webhook = AsyncMock(return_value=True)
    svc._repo = mock_repo
    return svc, mock_repo


def _null_redis() -> MagicMock:
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.delete = AsyncMock()
    return r


# ── 13. update_webhook ────────────────────────────────────────────────────────

class TestUpdateWebhook:
    @pytest.mark.asyncio
    async def test_update_name(self):
        svc, repo = _make_svc()
        orm = _make_orm_webhook()
        updated = _make_orm_webhook(name="New Name")
        repo.find_webhook_by_id.return_value = orm
        repo.update_webhook.return_value = updated
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.update_webhook(_HOOK_ID, WebhookUpdate(name="New Name"))
        assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        svc, repo = _make_svc()
        repo.find_webhook_by_id.return_value = None
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            with pytest.raises(Exception, match="not found"):
                await svc.update_webhook(_HOOK_ID, WebhookUpdate(name="X"))

    @pytest.mark.asyncio
    async def test_update_invalid_events_raises(self):
        svc, repo = _make_svc()
        repo.find_webhook_by_id.return_value = _make_orm_webhook()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            with pytest.raises(Exception, match="Unsupported event"):
                await svc.update_webhook(
                    _HOOK_ID, WebhookUpdate(events=["bad.event.xyz"])
                )

    @pytest.mark.asyncio
    async def test_update_no_fields_returns_existing(self):
        svc, repo = _make_svc()
        orm = _make_orm_webhook()
        repo.find_webhook_by_id.return_value = orm
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.update_webhook(_HOOK_ID, WebhookUpdate())
        repo.update_webhook.assert_not_called()
        assert isinstance(result, WebhookOut)

    @pytest.mark.asyncio
    async def test_update_is_active_false(self):
        svc, repo = _make_svc()
        orm = _make_orm_webhook()
        updated = _make_orm_webhook(is_active=False)
        repo.find_webhook_by_id.return_value = orm
        repo.update_webhook.return_value = updated
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.update_webhook(_HOOK_ID, WebhookUpdate(is_active=False))
        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_update_busts_cache(self):
        svc, repo = _make_svc()
        orm = _make_orm_webhook()
        repo.find_webhook_by_id.return_value = orm
        repo.update_webhook.return_value = _make_orm_webhook(name="Updated")
        redis = _null_redis()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            await svc.update_webhook(_HOOK_ID, WebhookUpdate(name="Updated"))
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_update_commits_session(self):
        svc, repo = _make_svc()
        orm = _make_orm_webhook()
        repo.find_webhook_by_id.return_value = orm
        repo.update_webhook.return_value = _make_orm_webhook(name="U")
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            await svc.update_webhook(_HOOK_ID, WebhookUpdate(name="U"))
        svc._session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_valid_events_accepted(self):
        svc, repo = _make_svc()
        orm = _make_orm_webhook()
        updated = _make_orm_webhook(events=["payment.received", "invoice.paid"])
        repo.find_webhook_by_id.return_value = orm
        repo.update_webhook.return_value = updated
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.update_webhook(
                _HOOK_ID,
                WebhookUpdate(events=["payment.received", "invoice.paid"]),
            )
        assert isinstance(result, WebhookOut)

    @pytest.mark.asyncio
    async def test_update_url(self):
        svc, repo = _make_svc()
        orm = _make_orm_webhook()
        updated = _make_orm_webhook(url="https://new-endpoint.com/hook")
        repo.find_webhook_by_id.return_value = orm
        repo.update_webhook.return_value = updated
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.update_webhook(
                _HOOK_ID,
                WebhookUpdate(url="https://new-endpoint.com/hook"),
            )
        assert result.url == "https://new-endpoint.com/hook"


# ── 14. delete_webhook ────────────────────────────────────────────────────────

class TestDeleteWebhook:
    @pytest.mark.asyncio
    async def test_delete_existing_webhook(self):
        svc, repo = _make_svc()
        repo.find_webhook_by_id.return_value = _make_orm_webhook()
        repo.delete_webhook.return_value = True
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            await svc.delete_webhook(_HOOK_ID)  # should not raise

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self):
        svc, repo = _make_svc()
        repo.find_webhook_by_id.return_value = None
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            with pytest.raises(Exception, match="not found"):
                await svc.delete_webhook(_HOOK_ID)

    @pytest.mark.asyncio
    async def test_delete_busts_cache(self):
        svc, repo = _make_svc()
        repo.find_webhook_by_id.return_value = _make_orm_webhook()
        repo.delete_webhook.return_value = True
        redis = _null_redis()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            await svc.delete_webhook(_HOOK_ID)
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_delete_commits_session(self):
        svc, repo = _make_svc()
        repo.find_webhook_by_id.return_value = _make_orm_webhook()
        repo.delete_webhook.return_value = True
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            await svc.delete_webhook(_HOOK_ID)
        svc._session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none(self):
        svc, repo = _make_svc()
        repo.find_webhook_by_id.return_value = _make_orm_webhook()
        repo.delete_webhook.return_value = True
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.delete_webhook(_HOOK_ID)
        assert result is None


# ── 15. Validation edge cases ─────────────────────────────────────────────────

class TestValidationEdgeCases:
    def test_validate_empty_events_list_ok(self):
        svc, _ = _make_svc()
        # should not raise for empty list
        svc._validate_events([])

    def test_validate_single_valid_event(self):
        svc, _ = _make_svc()
        svc._validate_events(["customer.created"])

    def test_validate_multiple_valid_events(self):
        svc, _ = _make_svc()
        svc._validate_events(["customer.created", "invoice.paid", "payment.received"])

    def test_validate_invalid_event_raises(self):
        svc, _ = _make_svc()
        with pytest.raises(Exception, match="Unsupported event"):
            svc._validate_events(["totally.fake"])

    def test_validate_mixed_valid_invalid_raises(self):
        svc, _ = _make_svc()
        with pytest.raises(Exception, match="Unsupported event"):
            svc._validate_events(["customer.created", "totally.fake"])

    def test_validate_all_events_valid(self):
        svc, _ = _make_svc()
        # All supported events should pass
        svc._validate_events(list(SUPPORTED_WEBHOOK_EVENTS))

    @pytest.mark.asyncio
    async def test_create_api_key_strips_name(self):
        from corpmind.modules.integrations.schemas import ApiKeyCreate
        svc, repo = _make_svc()
        orm = _make_orm_key(name="Stripped Name")
        repo.create_api_key.return_value = orm
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            # Leading/trailing whitespace in name — service strips it
            await svc.create_api_key(ApiKeyCreate(workspace_id=_WS_ID, name="  Stripped Name  "))
        call_args = repo.create_api_key.call_args[0][0]
        assert call_args.name == "Stripped Name"

    @pytest.mark.asyncio
    async def test_create_webhook_strips_url(self):
        from corpmind.modules.integrations.schemas import WebhookCreate
        svc, repo = _make_svc()
        repo.create_webhook.return_value = _make_orm_webhook()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            await svc.create_webhook(
                WebhookCreate(workspace_id=_WS_ID, name="H", url="  https://x.com  ")
            )
        call_args = repo.create_webhook.call_args[0][0]
        assert call_args.url == "https://x.com"


# ── 16. Model field checks ────────────────────────────────────────────────────

class TestModelFields:
    def test_api_key_tablename(self):
        assert ApiKey.__tablename__ == "api_keys"

    def test_webhook_tablename(self):
        assert Webhook.__tablename__ == "webhooks"

    def test_api_key_has_key_hash_column(self):
        cols = {c.name for c in ApiKey.__table__.columns}
        assert "key_hash" in cols

    def test_api_key_has_key_prefix_column(self):
        cols = {c.name for c in ApiKey.__table__.columns}
        assert "key_prefix" in cols

    def test_api_key_has_is_active_column(self):
        cols = {c.name for c in ApiKey.__table__.columns}
        assert "is_active" in cols

    def test_api_key_has_created_by_column(self):
        cols = {c.name for c in ApiKey.__table__.columns}
        assert "created_by" in cols

    def test_api_key_has_workspace_id_column(self):
        cols = {c.name for c in ApiKey.__table__.columns}
        assert "workspace_id" in cols

    def test_webhook_has_url_column(self):
        cols = {c.name for c in Webhook.__table__.columns}
        assert "url" in cols

    def test_webhook_has_secret_column(self):
        cols = {c.name for c in Webhook.__table__.columns}
        assert "secret" in cols

    def test_webhook_has_events_column(self):
        cols = {c.name for c in Webhook.__table__.columns}
        assert "events" in cols

    def test_webhook_has_is_active_column(self):
        cols = {c.name for c in Webhook.__table__.columns}
        assert "is_active" in cols

    def test_webhook_has_last_delivery_at_column(self):
        cols = {c.name for c in Webhook.__table__.columns}
        assert "last_delivery_at" in cols

    def test_api_key_prefix_unique_constraint(self):
        # unique=True on mapped_column may register as UniqueConstraint or as unique index
        from sqlalchemy import UniqueConstraint
        unique_cols: set[str] = set()
        for idx in ApiKey.__table__.indexes:
            if idx.unique:
                for col in idx.columns:
                    unique_cols.add(col.name)
        for c in ApiKey.__table__.constraints:
            if isinstance(c, UniqueConstraint):
                for col in c.columns:
                    unique_cols.add(col.name)
        assert "key_prefix" in unique_cols


# ── 17. Tenant isolation patterns ─────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_list_api_keys_uses_tenant_context(self):
        svc, repo = _make_svc()
        repo.find_api_keys.return_value = []
        ctx = _mock_ctx()
        with (
            patch(_PATCH_CTX, return_value=ctx),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            await svc.list_api_keys(_WS_ID)
        # Repo is called (uses ctx internally)
        repo.find_api_keys.assert_called_once_with(_WS_ID)

    @pytest.mark.asyncio
    async def test_list_webhooks_uses_tenant_context(self):
        svc, repo = _make_svc()
        repo.find_webhooks.return_value = []
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            await svc.list_webhooks(_WS_ID)
        repo.find_webhooks.assert_called_once_with(_WS_ID)

    @pytest.mark.asyncio
    async def test_api_key_cache_scoped_to_org(self):
        org_a = uuid.UUID("aaaa0000-0000-0000-0000-000000000001")
        org_b = uuid.UUID("bbbb0000-0000-0000-0000-000000000001")
        k_a = _api_keys_cache_key(org_a, _WS_ID)
        k_b = _api_keys_cache_key(org_b, _WS_ID)
        assert k_a != k_b
        assert str(org_a) in k_a
        assert str(org_b) in k_b

    @pytest.mark.asyncio
    async def test_webhook_cache_scoped_to_org(self):
        org_a = uuid.UUID("aaaa0000-0000-0000-0000-000000000002")
        org_b = uuid.UUID("bbbb0000-0000-0000-0000-000000000002")
        k_a = _webhooks_cache_key(org_a, _WS_ID)
        k_b = _webhooks_cache_key(org_b, _WS_ID)
        assert k_a != k_b

    @pytest.mark.asyncio
    async def test_get_api_key_checks_tenant(self):
        svc, repo = _make_svc()
        repo.find_api_key_by_id.return_value = None
        with patch(_PATCH_CTX, return_value=_mock_ctx()):
            with pytest.raises(Exception, match="not found"):
                await svc.get_api_key(uuid.uuid4())


# ── 18. Redis cache TTL and bust patterns ─────────────────────────────────────

class TestRedisCacheBust:
    @pytest.mark.asyncio
    async def test_api_key_cache_key_in_bust_call(self):
        svc, repo = _make_svc()
        repo.find_api_key_by_id.return_value = _make_orm_key(is_active=True)
        repo.update_api_key.return_value = _make_orm_key(is_active=False)
        redis = _null_redis()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            await svc.revoke_api_key(_KEY_ID)
        bust_key = _api_keys_cache_key(_ORG_ID, _WS_ID)
        redis.delete.assert_called_with(bust_key)

    @pytest.mark.asyncio
    async def test_webhook_cache_key_in_bust_call(self):
        svc, repo = _make_svc()
        repo.find_webhook_by_id.return_value = _make_orm_webhook()
        repo.delete_webhook.return_value = True
        redis = _null_redis()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            await svc.delete_webhook(_HOOK_ID)
        bust_key = _webhooks_cache_key(_ORG_ID, _WS_ID)
        redis.delete.assert_called_with(bust_key)

    @pytest.mark.asyncio
    async def test_cache_setex_called_with_correct_ttl(self):
        svc, repo = _make_svc()
        repo.find_webhooks.return_value = [_make_orm_webhook()]
        redis = _null_redis()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            await svc.list_webhooks(_WS_ID)
        args = redis.setex.call_args[0]
        assert args[1] == 300  # _CACHE_TTL

    @pytest.mark.asyncio
    async def test_api_keys_cache_setex_ttl(self):
        svc, repo = _make_svc()
        repo.find_api_keys.return_value = [_make_orm_key()]
        redis = _null_redis()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            await svc.list_api_keys(_WS_ID)
        args = redis.setex.call_args[0]
        assert args[1] == 300


# ── 19. Repo table map ────────────────────────────────────────────────────────

class TestRepoPatterns:
    def test_repo_instantiates_with_session(self):
        from corpmind.modules.integrations.repo import IntegrationRepo
        session = AsyncMock()
        repo = IntegrationRepo(session)
        assert repo._session is session

    def test_service_instantiates_with_session(self):
        session = AsyncMock()
        svc = IntegrationService(session)
        assert svc._session is session

    def test_service_creates_repo(self):
        from corpmind.modules.integrations.repo import IntegrationRepo
        session = AsyncMock()
        svc = IntegrationService(session)
        assert isinstance(svc._repo, IntegrationRepo)

    def test_api_key_model_has_tenant_id(self):
        cols = {c.name for c in ApiKey.__table__.columns}
        assert "tenant_id" in cols

    def test_webhook_model_has_tenant_id(self):
        cols = {c.name for c in Webhook.__table__.columns}
        assert "tenant_id" in cols


# ── 20. Edge cases ────────────────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_list_multiple_api_keys(self):
        svc, repo = _make_svc()
        keys = [_make_orm_key(id=uuid.uuid4(), key_prefix=f"pref{i:04d}") for i in range(5)]
        repo.find_api_keys.return_value = keys
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.list_api_keys(_WS_ID)
        assert result.total == 5
        assert len(result.items) == 5

    @pytest.mark.asyncio
    async def test_list_multiple_webhooks(self):
        svc, repo = _make_svc()
        hooks = [_make_orm_webhook(id=uuid.uuid4(), name=f"hook-{i}") for i in range(3)]
        repo.find_webhooks.return_value = hooks
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.list_webhooks(_WS_ID)
        assert result.total == 3

    @pytest.mark.asyncio
    async def test_webhook_list_schema_parses_from_json(self):
        out = WebhookListOut(items=[], total=0)
        json_str = out.model_dump_json()
        parsed = WebhookListOut.model_validate_json(json_str)
        assert parsed.total == 0

    def test_api_key_out_dump_excludes_key_hash(self):
        orm = MagicMock(spec=ApiKey)
        orm.id = uuid.uuid4()
        orm.tenant_id = _ORG_ID
        orm.workspace_id = _WS_ID
        orm.name = "K"
        orm.key_prefix = "abcd1234"
        orm.last_used_at = None
        orm.expires_at = None
        orm.is_active = True
        orm.created_by = _USER_ID
        orm.created_at = datetime(2026, 7, 8, tzinfo=UTC)
        out = ApiKeyOut.model_validate(orm)
        dumped = out.model_dump()
        assert "key_hash" not in dumped

    def test_webhook_out_events_is_list(self):
        orm = MagicMock(spec=Webhook)
        orm.id = uuid.uuid4()
        orm.tenant_id = _ORG_ID
        orm.workspace_id = _WS_ID
        orm.name = "H"
        orm.url = "https://x.com"
        orm.events = ["customer.created"]
        orm.is_active = True
        orm.last_delivery_at = None
        orm.created_by = _USER_ID
        orm.created_at = datetime(2026, 7, 8, tzinfo=UTC)
        out = WebhookOut.model_validate(orm)
        assert isinstance(out.events, list)

    @pytest.mark.asyncio
    async def test_get_api_key_with_expiry(self):
        svc, repo = _make_svc()
        expires = datetime(2027, 12, 31, tzinfo=UTC)
        repo.find_api_key_by_id.return_value = _make_orm_key(expires_at=expires)
        with patch(_PATCH_CTX, return_value=_mock_ctx()):
            result = await svc.get_api_key(_KEY_ID)
        assert result.expires_at == expires

    @pytest.mark.asyncio
    async def test_list_api_keys_cache_key_is_workspace_scoped(self):
        ws_a = uuid.uuid4()
        ws_b = uuid.uuid4()
        svc, repo = _make_svc()
        repo.find_api_keys.return_value = []
        redis_a = _null_redis()
        redis_b = _null_redis()

        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis_a),
        ):
            await svc.list_api_keys(ws_a)

        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis_b),
        ):
            await svc.list_api_keys(ws_b)

        key_a = redis_a.setex.call_args[0][0]
        key_b = redis_b.setex.call_args[0][0]
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_update_webhook_no_none_values_sent(self):
        """Fields that are None in update request must not be written to DB."""
        svc, repo = _make_svc()
        orm = _make_orm_webhook()
        repo.find_webhook_by_id.return_value = orm
        repo.update_webhook.return_value = _make_orm_webhook(name="Updated")
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            await svc.update_webhook(_HOOK_ID, WebhookUpdate(name="Updated", url=None))
        # Only "name" should be in the fields passed to update_webhook
        call_fields = repo.update_webhook.call_args[0][1]
        assert "url" not in call_fields
        assert "name" in call_fields
