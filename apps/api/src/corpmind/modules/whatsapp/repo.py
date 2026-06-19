"""WhatsApp module repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.whatsapp.models import WhatsAppSession, WhatsAppTemplate


class WhatsAppTemplateRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_approved(self) -> list[WhatsAppTemplate]:
        """Return all approved templates for the current tenant."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WhatsAppTemplate)
            .where(
                WhatsAppTemplate.tenant_id == ctx.org_id,
                WhatsAppTemplate.approval_status == "approved",
            )
            .order_by(WhatsAppTemplate.name, WhatsAppTemplate.language)
        )
        return list(result.scalars().all())

    async def find_by_name_and_language(
        self, name: str, language: str
    ) -> WhatsAppTemplate | None:
        """Fetch the first approved template matching (name, language)."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WhatsAppTemplate)
            .where(
                WhatsAppTemplate.tenant_id == ctx.org_id,
                WhatsAppTemplate.name == name,
                WhatsAppTemplate.language == language,
                WhatsAppTemplate.approval_status == "approved",
            )
            .limit(1)
        )
        return result.scalars().first()


class WhatsAppSessionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_active_session(self, contact_id: uuid.UUID) -> WhatsAppSession | None:
        """Return the active 24h session for a contact, if any."""
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
