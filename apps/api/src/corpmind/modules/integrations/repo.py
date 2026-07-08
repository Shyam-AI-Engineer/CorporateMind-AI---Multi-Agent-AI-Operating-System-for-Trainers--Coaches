"""Integration Hub repository — Sprint 55."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.integrations.models import ApiKey, Webhook


class IntegrationRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── API Keys ──────────────────────────────────────────────────────────────

    async def create_api_key(self, record: ApiKey) -> ApiKey:
        self._session.add(record)
        await self._session.flush()
        return record

    async def find_api_key_by_id(self, key_id: uuid.UUID) -> ApiKey | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(ApiKey).where(
                ApiKey.tenant_id == ctx.org_id,
                ApiKey.id == key_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_api_keys(self, workspace_id: uuid.UUID) -> list[ApiKey]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(ApiKey)
            .where(
                ApiKey.tenant_id == ctx.org_id,
                ApiKey.workspace_id == workspace_id,
            )
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_api_key(
        self, key_id: uuid.UUID, fields: dict
    ) -> ApiKey | None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(ApiKey)
            .where(
                ApiKey.tenant_id == ctx.org_id,
                ApiKey.id == key_id,
            )
            .values(**fields)
        )
        return await self.find_api_key_by_id(key_id)

    # ── Webhooks ──────────────────────────────────────────────────────────────

    async def create_webhook(self, record: Webhook) -> Webhook:
        self._session.add(record)
        await self._session.flush()
        return record

    async def find_webhook_by_id(self, webhook_id: uuid.UUID) -> Webhook | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Webhook).where(
                Webhook.tenant_id == ctx.org_id,
                Webhook.id == webhook_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_webhooks(self, workspace_id: uuid.UUID) -> list[Webhook]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Webhook)
            .where(
                Webhook.tenant_id == ctx.org_id,
                Webhook.workspace_id == workspace_id,
            )
            .order_by(Webhook.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_webhook(
        self, webhook_id: uuid.UUID, fields: dict
    ) -> Webhook | None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(Webhook)
            .where(
                Webhook.tenant_id == ctx.org_id,
                Webhook.id == webhook_id,
            )
            .values(**fields)
        )
        return await self.find_webhook_by_id(webhook_id)

    async def delete_webhook(self, webhook_id: uuid.UUID) -> bool:
        ctx = get_tenant_context()
        record = await self.find_webhook_by_id(webhook_id)
        if record is None or record.tenant_id != ctx.org_id:
            return False
        await self._session.delete(record)
        return True
