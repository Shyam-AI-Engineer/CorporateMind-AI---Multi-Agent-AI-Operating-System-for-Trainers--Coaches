"""Outreach repository."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
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

    async def list_by_contact(
        self,
        contact_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OutboundMessage]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(OutboundMessage)
            .where(
                OutboundMessage.contact_id == contact_id,
                OutboundMessage.tenant_id == ctx.org_id,
            )
            .order_by(OutboundMessage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, message: OutboundMessage) -> OutboundMessage:
        self._session.add(message)
        await self._session.flush()
        return message

    async def set_smtp_message_id(
        self,
        message_id: uuid.UUID,
        smtp_message_id: str,
    ) -> None:
        """Persist the pre-generated SMTP Message-ID before the network send.

        Called once per message (write-before-send pattern).  On Celery retry the
        caller reads the already-persisted value and skips this call.
        Does NOT commit — the caller is responsible for committing.
        """
        ctx = get_tenant_context()
        await self._session.execute(
            update(OutboundMessage)
            .where(
                OutboundMessage.id == message_id,
                OutboundMessage.tenant_id == ctx.org_id,
            )
            .values(smtp_message_id=smtp_message_id)
        )

    async def update_status(
        self,
        message_id: uuid.UUID,
        status: str,
        *,
        provider_message_id: str | None = None,
        sent_at: datetime | None = None,
    ) -> None:
        ctx = get_tenant_context()
        values: dict = {"status": status}
        if provider_message_id is not None:
            values["provider_message_id"] = provider_message_id
        if sent_at is not None:
            values["sent_at"] = sent_at
        await self._session.execute(
            update(OutboundMessage)
            .where(
                OutboundMessage.id == message_id,
                OutboundMessage.tenant_id == ctx.org_id,
            )
            .values(**values)
        )
