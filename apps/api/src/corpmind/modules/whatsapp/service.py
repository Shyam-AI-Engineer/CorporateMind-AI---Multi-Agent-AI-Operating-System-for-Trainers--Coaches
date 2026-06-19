"""WhatsApp service — 24h window and template lookup."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.whatsapp.models import WhatsAppSession, WhatsAppTemplate
from corpmind.modules.whatsapp.repo import WhatsAppSessionRepo, WhatsAppTemplateRepo

log = structlog.get_logger(__name__)


class WhatsAppService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._session_repo = WhatsAppSessionRepo(session)
        self._template_repo = WhatsAppTemplateRepo(session)

    async def check_24h_window(self, contact_id: uuid.UUID) -> WhatsAppSession | None:
        """Return the active 24h customer-care session for a contact, or None.

        An active session means the contact messaged us within the last 24h
        and free-form messages are permitted.  None means template-only mode.
        """
        session = await self._session_repo.find_active_session(contact_id)
        log.info(
            "whatsapp.24h_window_check",
            contact_id=str(contact_id),
            has_active_session=session is not None,
        )
        return session

    async def get_approved_template(
        self, name: str, language: str = "en"
    ) -> WhatsAppTemplate | None:
        """Fetch a tenant-scoped approved template by name and language."""
        return await self._template_repo.find_by_name_and_language(name, language)

    async def list_approved_templates(self) -> list[WhatsAppTemplate]:
        """Return all approved templates for the current tenant."""
        return await self._template_repo.list_approved()
