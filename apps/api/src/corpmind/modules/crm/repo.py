"""CRM repository."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.crm.models import Lead


class LeadRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, lead: Lead) -> Lead:
        self._session.add(lead)
        await self._session.flush()
        return lead
