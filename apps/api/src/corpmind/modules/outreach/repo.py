"""Outreach repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.outreach.models import OutboundMessage


class OutboundMessageRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, message_id: uuid.UUID) -> OutboundMessage | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(OutboundMessage).where(
                OutboundMessage.id == message_id,
                OutboundMessage.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, message: OutboundMessage) -> OutboundMessage:
        self._session.add(message)
        await self._session.flush()
        return message
