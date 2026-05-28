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
                # Fetch all rows; a contact may have channel-specific AND global entries.
            )
        )
        entries = result.scalars().all()
        # Blocked if any entry is global (channel IS NULL) or matches the current channel.
        return any(e.channel is None or e.channel == channel for e in entries)
