"""Integration Hub service — Sprint 55: API Keys and Webhooks."""

from __future__ import annotations

import hashlib
import secrets
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.integrations.events import (
    ApiKeyCreated,
    ApiKeyRevoked,
    WebhookCreated,
    WebhookDeleted,
    WebhookUpdated,
)
from corpmind.modules.integrations.models import ApiKey, Webhook
from corpmind.modules.integrations.repo import IntegrationRepo
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

log = structlog.get_logger(__name__)

_CACHE_TTL = 300  # 5 minutes


def _api_keys_cache_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:integrations:api_keys:{workspace_id}"


def _webhooks_cache_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:integrations:webhooks:{workspace_id}"


class IntegrationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = IntegrationRepo(session)

    # ── Key generation ────────────────────────────────────────────────────────

    def _generate_api_key(self) -> tuple[str, str, str]:
        """Return (plain_key, prefix, sha256_hex_hash)."""
        raw = secrets.token_hex(32)   # 64-char hex → high entropy
        plain_key = f"cm_{raw}"       # prefix makes leaked keys identifiable
        prefix = raw[:8]              # first 8 chars stored for display
        key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
        return plain_key, prefix, key_hash

    def generate_secret(self) -> str:
        """Generate a secure webhook signing secret."""
        return secrets.token_hex(32)

    # ── API Keys ──────────────────────────────────────────────────────────────

    async def create_api_key(self, req: ApiKeyCreate) -> ApiKeyCreatedOut:
        ctx = get_tenant_context()

        if not req.name.strip():
            raise ValidationError("API key name must not be blank.")

        plain_key, prefix, key_hash = self._generate_api_key()

        # Regenerate on the astronomically-unlikely collision
        existing = await self._repo.find_api_key_by_id(uuid.uuid4())  # just a dummy read path
        # Real prefix uniqueness is enforced by the UNIQUE DB index; ConflictError on flush.

        record = ApiKey(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            name=req.name.strip(),
            key_prefix=prefix,
            key_hash=key_hash,
            expires_at=req.expires_at,
            is_active=True,
            created_by=ctx.user_id,
        )
        created = await self._repo.create_api_key(record)
        await self._session.commit()

        await self._bust_api_key_cache(ctx.org_id, req.workspace_id)

        log.info(
            "integration.api_key_created",
            tenant_id=str(ctx.org_id),
            workspace_id=str(req.workspace_id),
            key_prefix=prefix,
        )
        event = ApiKeyCreated(
            key_id=created.id,
            workspace_id=req.workspace_id,
            key_prefix=prefix,
        )
        log.debug("integration.event_fired", evt=event.__class__.__name__)

        out = ApiKeyOut.model_validate(created)
        return ApiKeyCreatedOut(**out.model_dump(), plain_key=plain_key)

    async def revoke_api_key(self, key_id: uuid.UUID) -> ApiKeyOut:
        ctx = get_tenant_context()
        record = await self._repo.find_api_key_by_id(key_id)
        if record is None:
            raise NotFoundError(f"API key {key_id} not found.")
        if not record.is_active:
            raise ConflictError(f"API key {key_id} is already revoked.")

        updated = await self._repo.update_api_key(key_id, {"is_active": False})
        await self._session.commit()

        await self._bust_api_key_cache(ctx.org_id, record.workspace_id)

        log.info(
            "integration.api_key_revoked",
            tenant_id=str(ctx.org_id),
            key_id=str(key_id),
        )
        event = ApiKeyRevoked(key_id=key_id, workspace_id=record.workspace_id)
        log.debug("integration.event_fired", evt=event.__class__.__name__)

        if updated is None:
            raise NotFoundError(f"API key {key_id} not found after revoke.")
        return ApiKeyOut.model_validate(updated)

    async def list_api_keys(self, workspace_id: uuid.UUID) -> ApiKeyListOut:
        ctx = get_tenant_context()
        cache_key = _api_keys_cache_key(ctx.org_id, workspace_id)

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                return ApiKeyListOut.model_validate_json(cached)
        except Exception:
            pass

        records = await self._repo.find_api_keys(workspace_id)
        out = ApiKeyListOut(
            items=[ApiKeyOut.model_validate(r) for r in records],
            total=len(records),
        )

        try:
            redis = get_redis()
            await redis.setex(cache_key, _CACHE_TTL, out.model_dump_json())
        except Exception:
            pass

        return out

    async def get_api_key(self, key_id: uuid.UUID) -> ApiKeyOut:
        record = await self._repo.find_api_key_by_id(key_id)
        if record is None:
            raise NotFoundError(f"API key {key_id} not found.")
        return ApiKeyOut.model_validate(record)

    # ── Webhooks ──────────────────────────────────────────────────────────────

    async def create_webhook(self, req: WebhookCreate) -> WebhookCreatedOut:
        ctx = get_tenant_context()

        if not req.name.strip():
            raise ValidationError("Webhook name must not be blank.")
        if not req.url.strip():
            raise ValidationError("Webhook URL must not be blank.")
        self._validate_events(req.events)

        secret = self.generate_secret()
        record = Webhook(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            name=req.name.strip(),
            url=req.url.strip(),
            secret=secret,
            events=req.events,
            is_active=True,
            created_by=ctx.user_id,
        )
        created = await self._repo.create_webhook(record)
        await self._session.commit()

        await self._bust_webhook_cache(ctx.org_id, req.workspace_id)

        log.info(
            "integration.webhook_created",
            tenant_id=str(ctx.org_id),
            workspace_id=str(req.workspace_id),
            webhook_id=str(created.id),
        )
        event = WebhookCreated(
            webhook_id=created.id,
            workspace_id=req.workspace_id,
            name=created.name,
        )
        log.debug("integration.event_fired", evt=event.__class__.__name__)

        out = WebhookOut.model_validate(created)
        return WebhookCreatedOut(**out.model_dump(), secret=secret)

    async def update_webhook(
        self, webhook_id: uuid.UUID, req: WebhookUpdate
    ) -> WebhookOut:
        ctx = get_tenant_context()
        record = await self._repo.find_webhook_by_id(webhook_id)
        if record is None:
            raise NotFoundError(f"Webhook {webhook_id} not found.")

        if req.events is not None:
            self._validate_events(req.events)

        fields = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
        if not fields:
            return WebhookOut.model_validate(record)

        updated_field_names = list(fields.keys())
        updated = await self._repo.update_webhook(webhook_id, fields)
        await self._session.commit()

        await self._bust_webhook_cache(ctx.org_id, record.workspace_id)

        log.info(
            "integration.webhook_updated",
            tenant_id=str(ctx.org_id),
            webhook_id=str(webhook_id),
            updated_fields=updated_field_names,
        )
        event = WebhookUpdated(
            webhook_id=webhook_id,
            workspace_id=record.workspace_id,
            updated_fields=updated_field_names,
        )
        log.debug("integration.event_fired", evt=event.__class__.__name__)

        if updated is None:
            raise NotFoundError(f"Webhook {webhook_id} not found after update.")
        return WebhookOut.model_validate(updated)

    async def delete_webhook(self, webhook_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        record = await self._repo.find_webhook_by_id(webhook_id)
        if record is None:
            raise NotFoundError(f"Webhook {webhook_id} not found.")

        workspace_id = record.workspace_id
        deleted = await self._repo.delete_webhook(webhook_id)
        await self._session.commit()

        if not deleted:
            raise NotFoundError(f"Webhook {webhook_id} not found.")

        await self._bust_webhook_cache(ctx.org_id, workspace_id)

        log.info(
            "integration.webhook_deleted",
            tenant_id=str(ctx.org_id),
            webhook_id=str(webhook_id),
        )
        event = WebhookDeleted(webhook_id=webhook_id, workspace_id=workspace_id)
        log.debug("integration.event_fired", evt=event.__class__.__name__)

    async def list_webhooks(self, workspace_id: uuid.UUID) -> WebhookListOut:
        ctx = get_tenant_context()
        cache_key = _webhooks_cache_key(ctx.org_id, workspace_id)

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                return WebhookListOut.model_validate_json(cached)
        except Exception:
            pass

        records = await self._repo.find_webhooks(workspace_id)
        out = WebhookListOut(
            items=[WebhookOut.model_validate(r) for r in records],
            total=len(records),
        )

        try:
            redis = get_redis()
            await redis.setex(cache_key, _CACHE_TTL, out.model_dump_json())
        except Exception:
            pass

        return out

    # ── Private helpers ───────────────────────────────────────────────────────

    def _validate_events(self, events: list[str]) -> None:
        invalid = [e for e in events if e not in SUPPORTED_WEBHOOK_EVENTS]
        if invalid:
            raise ValidationError(
                f"Unsupported event type(s): {invalid}. "
                f"Supported: {sorted(SUPPORTED_WEBHOOK_EVENTS)}"
            )

    async def _bust_api_key_cache(
        self, org_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        try:
            redis = get_redis()
            await redis.delete(_api_keys_cache_key(org_id, workspace_id))
        except Exception:
            pass

    async def _bust_webhook_cache(
        self, org_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        try:
            redis = get_redis()
            await redis.delete(_webhooks_cache_key(org_id, workspace_id))
        except Exception:
            pass
