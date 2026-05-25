"""Compliance repository — audit events, unsubscribe list, opt-in lookups."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.compliance.models import AuditEvent, UnsubscribeEntry

log = structlog.get_logger(__name__)


class AuditRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: AuditEvent) -> AuditEvent:
        self._session.add(event)
        await self._session.flush()
        return event


class UnsubscribeRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_unsubscribed(
        self,
        tenant_id: uuid.UUID,
        contact_hash: str,
        channel: str,
    ) -> bool:
        result = await self._session.execute(
            select(UnsubscribeEntry).where(
                UnsubscribeEntry.tenant_id == tenant_id,
                UnsubscribeEntry.contact_hash == contact_hash,
                # Match channel-specific OR global (channel IS NULL) unsubscribe
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return False
        return entry.channel is None or entry.channel == channel
