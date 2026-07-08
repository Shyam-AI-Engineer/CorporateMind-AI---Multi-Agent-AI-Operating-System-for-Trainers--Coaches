"""Unit tests — Sprint 55: Integration Hub (part 1).

Tests for IntegrationService, schemas, events, and repo patterns.
Run: uv run pytest tests/unit/test_integration_service.py -q
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.integrations.events import (
    ApiKeyCreated,
    ApiKeyRevoked,
    WebhookCreated,
    WebhookDeleted,
    WebhookUpdated,
)
from corpmind.modules.integrations.models import ApiKey, Webhook
from corpmind.modules.integrations.schemas import (
    SUPPORTED_WEBHOOK_EVENTS,
    ApiKeyCreate,
    ApiKeyCreatedOut,
    ApiKeyListOut,
    ApiKeyOut,
    WebhookCreate,
    WebhookCreatedOut,
    WebhookListOut,
    WebhookOut,
    WebhookUpdate,
)
from corpmind.modules.integrations.service import (
    IntegrationService,
    _api_keys_cache_key,
    _webhooks_cache_key,
    _CACHE_TTL,
)

# ── Fixtures and helpers ──────────────────────────────────────────────────────

_ORG_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_WS_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
_USER_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
_KEY_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000004")
_HOOK_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000005")

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
        name="Test Key",
        key_prefix="abcd1234",
        key_hash="a" * 64,
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
        name="My Hook",
        url="https://example.com/hook",
        secret="s3cr3t" * 10,
        events=["customer.created"],
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


# ── 1. Cache key helpers ──────────────────────────────────────────────────────

class TestCacheKeys:
    def test_api_keys_key_format(self):
        k = _api_keys_cache_key(_ORG_ID, _WS_ID)
        assert k.startswith(f"t:{_ORG_ID}:")
        assert "api_keys" in k
        assert str(_WS_ID) in k

    def test_webhooks_key_format(self):
        k = _webhooks_cache_key(_ORG_ID, _WS_ID)
        assert k.startswith(f"t:{_ORG_ID}:")
        assert "webhooks" in k
        assert str(_WS_ID) in k

    def test_api_keys_key_different_workspaces(self):
        ws2 = uuid.uuid4()
        k1 = _api_keys_cache_key(_ORG_ID, _WS_ID)
        k2 = _api_keys_cache_key(_ORG_ID, ws2)
        assert k1 != k2

    def test_webhooks_key_different_orgs(self):
        org2 = uuid.uuid4()
        k1 = _webhooks_cache_key(_ORG_ID, _WS_ID)
        k2 = _webhooks_cache_key(org2, _WS_ID)
        assert k1 != k2

    def test_api_keys_and_webhooks_keys_distinct(self):
        k1 = _api_keys_cache_key(_ORG_ID, _WS_ID)
        k2 = _webhooks_cache_key(_ORG_ID, _WS_ID)
        assert k1 != k2

    def test_cache_ttl_is_300(self):
        assert _CACHE_TTL == 300


# ── 2. Schema constants ───────────────────────────────────────────────────────

class TestSchemaConstants:
    def test_supported_events_is_frozenset(self):
        assert isinstance(SUPPORTED_WEBHOOK_EVENTS, frozenset)

    def test_customer_events_present(self):
        assert "customer.created" in SUPPORTED_WEBHOOK_EVENTS
        assert "customer.updated" in SUPPORTED_WEBHOOK_EVENTS
        assert "customer.deleted" in SUPPORTED_WEBHOOK_EVENTS

    def test_invoice_events_present(self):
        assert "invoice.created" in SUPPORTED_WEBHOOK_EVENTS
        assert "invoice.paid" in SUPPORTED_WEBHOOK_EVENTS
        assert "invoice.overdue" in SUPPORTED_WEBHOOK_EVENTS

    def test_payment_events_present(self):
        assert "payment.received" in SUPPORTED_WEBHOOK_EVENTS
        assert "payment.failed" in SUPPORTED_WEBHOOK_EVENTS

    def test_training_events_present(self):
        assert "training.session.started" in SUPPORTED_WEBHOOK_EVENTS
        assert "training.session.completed" in SUPPORTED_WEBHOOK_EVENTS

    def test_workflow_events_present(self):
        assert "workflow.started" in SUPPORTED_WEBHOOK_EVENTS
        assert "workflow.completed" in SUPPORTED_WEBHOOK_EVENTS
        assert "workflow.failed" in SUPPORTED_WEBHOOK_EVENTS

    def test_renewal_events_present(self):
        assert "renewal.upcoming" in SUPPORTED_WEBHOOK_EVENTS
        assert "renewal.completed" in SUPPORTED_WEBHOOK_EVENTS

    def test_api_key_revoked_event_present(self):
        assert "api_key.revoked" in SUPPORTED_WEBHOOK_EVENTS

    def test_at_least_15_events(self):
        assert len(SUPPORTED_WEBHOOK_EVENTS) >= 15

    def test_no_empty_string_event(self):
        assert "" not in SUPPORTED_WEBHOOK_EVENTS

    def test_all_events_have_dot_separator(self):
        assert all("." in e for e in SUPPORTED_WEBHOOK_EVENTS)

    def test_certificate_event_present(self):
        assert "training.certificate.issued" in SUPPORTED_WEBHOOK_EVENTS


# ── 3. Schema models ──────────────────────────────────────────────────────────

class TestSchemaModels:
    def test_api_key_out_no_key_hash_field(self):
        fields = ApiKeyOut.model_fields
        assert "key_hash" not in fields

    def test_api_key_out_has_required_fields(self):
        fields = ApiKeyOut.model_fields
        for f in ["id", "tenant_id", "workspace_id", "name", "key_prefix", "is_active"]:
            assert f in fields

    def test_api_key_created_out_has_plain_key(self):
        assert "plain_key" in ApiKeyCreatedOut.model_fields

    def test_api_key_created_out_inherits_api_key_out(self):
        assert issubclass(ApiKeyCreatedOut, ApiKeyOut)

    def test_api_key_list_out_has_items_and_total(self):
        out = ApiKeyListOut(items=[], total=0)
        assert out.items == []
        assert out.total == 0

    def test_webhook_out_no_secret_field(self):
        fields = WebhookOut.model_fields
        assert "secret" not in fields

    def test_webhook_created_out_has_secret(self):
        assert "secret" in WebhookCreatedOut.model_fields

    def test_webhook_created_out_inherits_webhook_out(self):
        assert issubclass(WebhookCreatedOut, WebhookOut)

    def test_webhook_list_out_has_items_and_total(self):
        out = WebhookListOut(items=[], total=0)
        assert out.items == []
        assert out.total == 0

    def test_api_key_create_requires_workspace_id_and_name(self):
        req = ApiKeyCreate(workspace_id=_WS_ID, name="My Key")
        assert req.name == "My Key"
        assert req.expires_at is None

    def test_webhook_create_defaults_empty_events(self):
        req = WebhookCreate(workspace_id=_WS_ID, name="H", url="https://x.com")
        assert req.events == []

    def test_webhook_update_all_optional(self):
        req = WebhookUpdate()
        assert req.name is None
        assert req.url is None
        assert req.events is None
        assert req.is_active is None

    def test_api_key_out_from_orm(self):
        orm = _make_orm_key()
        out = ApiKeyOut.model_validate(orm)
        assert out.id == _KEY_ID
        assert out.key_prefix == "abcd1234"

    def test_webhook_out_from_orm(self):
        orm = _make_orm_webhook()
        out = WebhookOut.model_validate(orm)
        assert out.id == _HOOK_ID
        assert out.url == "https://example.com/hook"

    def test_webhook_out_from_orm_no_secret_exposed(self):
        orm = _make_orm_webhook()
        out = WebhookOut.model_validate(orm)
        d = out.model_dump()
        assert "secret" not in d


# ── 4. Events ─────────────────────────────────────────────────────────────────

class TestEvents:
    def test_api_key_created_fields(self):
        e = ApiKeyCreated(key_id=_KEY_ID, workspace_id=_WS_ID, key_prefix="abcd1234")
        assert e.key_id == _KEY_ID
        assert e.key_prefix == "abcd1234"

    def test_api_key_created_has_timestamp(self):
        e = ApiKeyCreated(key_id=_KEY_ID, workspace_id=_WS_ID, key_prefix="x")
        assert isinstance(e.occurred_at, datetime)

    def test_api_key_revoked_fields(self):
        e = ApiKeyRevoked(key_id=_KEY_ID, workspace_id=_WS_ID)
        assert e.key_id == _KEY_ID
        assert e.workspace_id == _WS_ID

    def test_webhook_created_fields(self):
        e = WebhookCreated(webhook_id=_HOOK_ID, workspace_id=_WS_ID, name="H")
        assert e.name == "H"

    def test_webhook_updated_fields(self):
        e = WebhookUpdated(webhook_id=_HOOK_ID, workspace_id=_WS_ID, updated_fields=["url"])
        assert e.updated_fields == ["url"]

    def test_webhook_deleted_fields(self):
        e = WebhookDeleted(webhook_id=_HOOK_ID, workspace_id=_WS_ID)
        assert e.webhook_id == _HOOK_ID

    def test_events_have_utc_timestamp(self):
        e = ApiKeyCreated(key_id=_KEY_ID, workspace_id=_WS_ID, key_prefix="x")
        assert e.occurred_at.tzinfo is not None

    def test_webhook_updated_multiple_fields(self):
        e = WebhookUpdated(
            webhook_id=_HOOK_ID,
            workspace_id=_WS_ID,
            updated_fields=["url", "name", "events"],
        )
        assert len(e.updated_fields) == 3


# ── 5. _generate_api_key ──────────────────────────────────────────────────────

class TestGenerateApiKey:
    def _svc(self) -> IntegrationService:
        svc, _ = _make_svc()
        return svc

    def test_plain_key_starts_with_cm(self):
        svc = self._svc()
        plain, _, _ = svc._generate_api_key()
        assert plain.startswith("cm_")

    def test_plain_key_length(self):
        svc = self._svc()
        plain, _, _ = svc._generate_api_key()
        # "cm_" + 64 hex chars = 67 chars
        assert len(plain) == 67

    def test_prefix_length_is_8(self):
        svc = self._svc()
        _, prefix, _ = svc._generate_api_key()
        assert len(prefix) == 8

    def test_hash_is_sha256_hex(self):
        svc = self._svc()
        plain, _, key_hash = svc._generate_api_key()
        expected = hashlib.sha256(plain.encode()).hexdigest()
        assert key_hash == expected

    def test_hash_length_is_64(self):
        svc = self._svc()
        _, _, key_hash = svc._generate_api_key()
        assert len(key_hash) == 64

    def test_different_calls_produce_different_keys(self):
        svc = self._svc()
        plain1, _, _ = svc._generate_api_key()
        plain2, _, _ = svc._generate_api_key()
        assert plain1 != plain2

    def test_prefix_is_hex_chars(self):
        svc = self._svc()
        _, prefix, _ = svc._generate_api_key()
        assert all(c in "0123456789abcdef" for c in prefix)

    def test_hash_is_lowercase_hex(self):
        svc = self._svc()
        _, _, key_hash = svc._generate_api_key()
        assert key_hash == key_hash.lower()
        assert all(c in "0123456789abcdef" for c in key_hash)


# ── 6. generate_secret ────────────────────────────────────────────────────────

class TestGenerateSecret:
    def _svc(self) -> IntegrationService:
        svc, _ = _make_svc()
        return svc

    def test_secret_is_string(self):
        svc = self._svc()
        assert isinstance(svc.generate_secret(), str)

    def test_secret_length_is_64(self):
        svc = self._svc()
        assert len(svc.generate_secret()) == 64

    def test_different_secrets_each_call(self):
        svc = self._svc()
        assert svc.generate_secret() != svc.generate_secret()

    def test_secret_is_hex(self):
        svc = self._svc()
        s = svc.generate_secret()
        assert all(c in "0123456789abcdef" for c in s)


# ── 7. create_api_key ─────────────────────────────────────────────────────────

class TestCreateApiKey:
    @pytest.mark.asyncio
    async def test_create_returns_api_key_created_out(self):
        svc, repo = _make_svc()
        orm = _make_orm_key()
        repo.create_api_key.return_value = orm
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            req = ApiKeyCreate(workspace_id=_WS_ID, name="Key 1")
            result = await svc.create_api_key(req)
        assert isinstance(result, ApiKeyCreatedOut)

    @pytest.mark.asyncio
    async def test_create_plain_key_starts_with_cm(self):
        svc, repo = _make_svc()
        orm = _make_orm_key()
        repo.create_api_key.return_value = orm
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            req = ApiKeyCreate(workspace_id=_WS_ID, name="Key 1")
            result = await svc.create_api_key(req)
        assert result.plain_key.startswith("cm_")

    @pytest.mark.asyncio
    async def test_create_plain_key_not_in_list_after(self):
        # plain_key only in CreatedOut, not in base ApiKeyOut
        svc, repo = _make_svc()
        orm = _make_orm_key()
        repo.create_api_key.return_value = orm
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            req = ApiKeyCreate(workspace_id=_WS_ID, name="Key 1")
            result = await svc.create_api_key(req)
        # ApiKeyOut fields should not include plain_key
        base = ApiKeyOut.model_validate(orm)
        assert not hasattr(base, "plain_key")

    @pytest.mark.asyncio
    async def test_create_busts_cache(self):
        svc, repo = _make_svc()
        orm = _make_orm_key()
        repo.create_api_key.return_value = orm
        redis = _null_redis()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            req = ApiKeyCreate(workspace_id=_WS_ID, name="Key 1")
            await svc.create_api_key(req)
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_create_blank_name_raises(self):
        svc, _ = _make_svc()
        with patch(_PATCH_CTX, return_value=_mock_ctx()):
            with pytest.raises(Exception):
                await svc.create_api_key(ApiKeyCreate(workspace_id=_WS_ID, name="   "))

    @pytest.mark.asyncio
    async def test_create_commits_session(self):
        svc, repo = _make_svc()
        orm = _make_orm_key()
        repo.create_api_key.return_value = orm
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            await svc.create_api_key(ApiKeyCreate(workspace_id=_WS_ID, name="K"))
        svc._session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_expiry(self):
        svc, repo = _make_svc()
        expires = datetime(2027, 1, 1, tzinfo=UTC)
        orm = _make_orm_key(expires_at=expires)
        repo.create_api_key.return_value = orm
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            req = ApiKeyCreate(workspace_id=_WS_ID, name="Expiring Key", expires_at=expires)
            result = await svc.create_api_key(req)
        assert result.expires_at == expires

    @pytest.mark.asyncio
    async def test_create_graceful_redis_failure(self):
        svc, repo = _make_svc()
        orm = _make_orm_key()
        repo.create_api_key.return_value = orm
        bad_redis = AsyncMock()
        bad_redis.get = AsyncMock(side_effect=Exception("Redis down"))
        bad_redis.setex = AsyncMock(side_effect=Exception("Redis down"))
        bad_redis.delete = AsyncMock(side_effect=Exception("Redis down"))
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=bad_redis),
        ):
            result = await svc.create_api_key(ApiKeyCreate(workspace_id=_WS_ID, name="K"))
        assert isinstance(result, ApiKeyCreatedOut)


# ── 8. revoke_api_key ─────────────────────────────────────────────────────────

class TestRevokeApiKey:
    @pytest.mark.asyncio
    async def test_revoke_active_key(self):
        svc, repo = _make_svc()
        orm = _make_orm_key(is_active=True)
        updated = _make_orm_key(is_active=False)
        repo.find_api_key_by_id.return_value = orm
        repo.update_api_key.return_value = updated
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.revoke_api_key(_KEY_ID)
        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_revoke_not_found_raises(self):
        svc, repo = _make_svc()
        repo.find_api_key_by_id.return_value = None
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            with pytest.raises(Exception, match="not found"):
                await svc.revoke_api_key(_KEY_ID)

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_raises(self):
        svc, repo = _make_svc()
        orm = _make_orm_key(is_active=False)
        repo.find_api_key_by_id.return_value = orm
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            with pytest.raises(Exception):
                await svc.revoke_api_key(_KEY_ID)

    @pytest.mark.asyncio
    async def test_revoke_busts_cache(self):
        svc, repo = _make_svc()
        orm = _make_orm_key(is_active=True)
        updated = _make_orm_key(is_active=False)
        repo.find_api_key_by_id.return_value = orm
        repo.update_api_key.return_value = updated
        redis = _null_redis()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            await svc.revoke_api_key(_KEY_ID)
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_revoke_commits_session(self):
        svc, repo = _make_svc()
        orm = _make_orm_key(is_active=True)
        updated = _make_orm_key(is_active=False)
        repo.find_api_key_by_id.return_value = orm
        repo.update_api_key.return_value = updated
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            await svc.revoke_api_key(_KEY_ID)
        svc._session.commit.assert_called_once()


# ── 9. list_api_keys ──────────────────────────────────────────────────────────

class TestListApiKeys:
    @pytest.mark.asyncio
    async def test_list_returns_api_key_list_out(self):
        svc, repo = _make_svc()
        repo.find_api_keys.return_value = [_make_orm_key()]
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.list_api_keys(_WS_ID)
        assert isinstance(result, ApiKeyListOut)
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_list_empty_workspace(self):
        svc, repo = _make_svc()
        repo.find_api_keys.return_value = []
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.list_api_keys(_WS_ID)
        assert result.total == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_list_uses_cache_hit(self):
        svc, repo = _make_svc()
        cached_out = ApiKeyListOut(items=[], total=0)
        redis = _null_redis()
        redis.get.return_value = cached_out.model_dump_json()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            result = await svc.list_api_keys(_WS_ID)
        repo.find_api_keys.assert_not_called()
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_stores_in_cache(self):
        svc, repo = _make_svc()
        repo.find_api_keys.return_value = [_make_orm_key()]
        redis = _null_redis()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            await svc.list_api_keys(_WS_ID)
        redis.setex.assert_called_once()
        args = redis.setex.call_args[0]
        assert args[1] == _CACHE_TTL

    @pytest.mark.asyncio
    async def test_list_key_hash_not_in_output(self):
        svc, repo = _make_svc()
        repo.find_api_keys.return_value = [_make_orm_key()]
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.list_api_keys(_WS_ID)
        for item in result.items:
            d = item.model_dump()
            assert "key_hash" not in d

    @pytest.mark.asyncio
    async def test_list_graceful_redis_failure(self):
        svc, repo = _make_svc()
        repo.find_api_keys.return_value = []
        bad = AsyncMock()
        bad.get = AsyncMock(side_effect=Exception("down"))
        bad.setex = AsyncMock(side_effect=Exception("down"))
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=bad),
        ):
            result = await svc.list_api_keys(_WS_ID)
        assert result.total == 0


# ── 10. get_api_key ───────────────────────────────────────────────────────────

class TestGetApiKey:
    @pytest.mark.asyncio
    async def test_get_returns_api_key_out(self):
        svc, repo = _make_svc()
        repo.find_api_key_by_id.return_value = _make_orm_key()
        with patch(_PATCH_CTX, return_value=_mock_ctx()):
            result = await svc.get_api_key(_KEY_ID)
        assert isinstance(result, ApiKeyOut)
        assert result.id == _KEY_ID

    @pytest.mark.asyncio
    async def test_get_not_found_raises(self):
        svc, repo = _make_svc()
        repo.find_api_key_by_id.return_value = None
        with patch(_PATCH_CTX, return_value=_mock_ctx()):
            with pytest.raises(Exception, match="not found"):
                await svc.get_api_key(_KEY_ID)

    @pytest.mark.asyncio
    async def test_get_no_key_hash_in_output(self):
        svc, repo = _make_svc()
        repo.find_api_key_by_id.return_value = _make_orm_key()
        with patch(_PATCH_CTX, return_value=_mock_ctx()):
            result = await svc.get_api_key(_KEY_ID)
        assert "key_hash" not in result.model_dump()

    @pytest.mark.asyncio
    async def test_get_inactive_key_still_returns(self):
        svc, repo = _make_svc()
        repo.find_api_key_by_id.return_value = _make_orm_key(is_active=False)
        with patch(_PATCH_CTX, return_value=_mock_ctx()):
            result = await svc.get_api_key(_KEY_ID)
        assert result.is_active is False


# ── 11. create_webhook ────────────────────────────────────────────────────────

class TestCreateWebhook:
    @pytest.mark.asyncio
    async def test_create_returns_webhook_created_out(self):
        svc, repo = _make_svc()
        orm = _make_orm_webhook()
        repo.create_webhook.return_value = orm
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            req = WebhookCreate(workspace_id=_WS_ID, name="H", url="https://x.com")
            result = await svc.create_webhook(req)
        assert isinstance(result, WebhookCreatedOut)
        assert result.secret is not None

    @pytest.mark.asyncio
    async def test_create_secret_is_64_chars(self):
        svc, repo = _make_svc()
        repo.create_webhook.return_value = _make_orm_webhook()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            req = WebhookCreate(workspace_id=_WS_ID, name="H", url="https://x.com")
            result = await svc.create_webhook(req)
        assert len(result.secret) == 64

    @pytest.mark.asyncio
    async def test_create_secret_not_in_list(self):
        svc, repo = _make_svc()
        repo.create_webhook.return_value = _make_orm_webhook()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.create_webhook(
                WebhookCreate(workspace_id=_WS_ID, name="H", url="https://x.com")
            )
        base = WebhookOut.model_validate(_make_orm_webhook())
        assert "secret" not in base.model_dump()

    @pytest.mark.asyncio
    async def test_create_invalid_event_raises(self):
        svc, _ = _make_svc()
        with patch(_PATCH_CTX, return_value=_mock_ctx()):
            with pytest.raises(Exception, match="Unsupported event"):
                await svc.create_webhook(
                    WebhookCreate(
                        workspace_id=_WS_ID,
                        name="H",
                        url="https://x.com",
                        events=["not.real.event"],
                    )
                )

    @pytest.mark.asyncio
    async def test_create_blank_name_raises(self):
        svc, _ = _make_svc()
        with patch(_PATCH_CTX, return_value=_mock_ctx()):
            with pytest.raises(Exception):
                await svc.create_webhook(
                    WebhookCreate(workspace_id=_WS_ID, name="  ", url="https://x.com")
                )

    @pytest.mark.asyncio
    async def test_create_busts_webhook_cache(self):
        svc, repo = _make_svc()
        repo.create_webhook.return_value = _make_orm_webhook()
        redis = _null_redis()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            await svc.create_webhook(
                WebhookCreate(workspace_id=_WS_ID, name="H", url="https://x.com")
            )
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_create_commits_session(self):
        svc, repo = _make_svc()
        repo.create_webhook.return_value = _make_orm_webhook()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            await svc.create_webhook(
                WebhookCreate(workspace_id=_WS_ID, name="H", url="https://x.com")
            )
        svc._session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_valid_events(self):
        svc, repo = _make_svc()
        repo.create_webhook.return_value = _make_orm_webhook(events=["customer.created"])
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.create_webhook(
                WebhookCreate(
                    workspace_id=_WS_ID,
                    name="H",
                    url="https://x.com",
                    events=["customer.created"],
                )
            )
        assert isinstance(result, WebhookCreatedOut)


# ── 12. list_webhooks ─────────────────────────────────────────────────────────

class TestListWebhooks:
    @pytest.mark.asyncio
    async def test_list_returns_webhook_list_out(self):
        svc, repo = _make_svc()
        repo.find_webhooks.return_value = [_make_orm_webhook()]
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.list_webhooks(_WS_ID)
        assert isinstance(result, WebhookListOut)
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_list_cache_hit(self):
        svc, repo = _make_svc()
        cached = WebhookListOut(items=[], total=0)
        redis = _null_redis()
        redis.get.return_value = cached.model_dump_json()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            result = await svc.list_webhooks(_WS_ID)
        repo.find_webhooks.assert_not_called()
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_no_secrets_in_output(self):
        svc, repo = _make_svc()
        repo.find_webhooks.return_value = [_make_orm_webhook()]
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=_null_redis()),
        ):
            result = await svc.list_webhooks(_WS_ID)
        for item in result.items:
            assert "secret" not in item.model_dump()

    @pytest.mark.asyncio
    async def test_list_stores_in_cache(self):
        svc, repo = _make_svc()
        repo.find_webhooks.return_value = []
        redis = _null_redis()
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=redis),
        ):
            await svc.list_webhooks(_WS_ID)
        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_graceful_redis_failure(self):
        svc, repo = _make_svc()
        repo.find_webhooks.return_value = []
        bad = AsyncMock()
        bad.get = AsyncMock(side_effect=Exception("down"))
        bad.setex = AsyncMock(side_effect=Exception("down"))
        with (
            patch(_PATCH_CTX, return_value=_mock_ctx()),
            patch(_PATCH_REDIS, return_value=bad),
        ):
            result = await svc.list_webhooks(_WS_ID)
        assert result.total == 0
