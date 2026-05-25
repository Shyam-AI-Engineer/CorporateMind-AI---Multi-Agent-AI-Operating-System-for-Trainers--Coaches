"""WhatsApp repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.whatsapp.models import WhatsAppSession


class WhatsAppSessionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_active_session(self, contact_id: uuid.UUID) -> WhatsAppSession | None:
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(WhatsAppSession).where(
                WhatsAppSession.tenant_id == ctx.org_id,
                WhatsAppSession.contact_id == contact_id,
                WhatsAppSession.is_active == True,  # noqa: E712
                WhatsAppSession.window_expires_at > now,
            )
        )
        return result.scalar_one_or_none()
