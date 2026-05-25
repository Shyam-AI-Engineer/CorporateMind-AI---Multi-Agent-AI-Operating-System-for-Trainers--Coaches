"""HR discovery repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.hr_discovery.models import HRContact


class HRContactRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_contactable_by_company(self, company_id: uuid.UUID) -> list[HRContact]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(HRContact).where(
                HRContact.tenant_id == ctx.org_id,
                HRContact.company_id == company_id,
                HRContact.is_contactable == True,  # noqa: E712
                HRContact.email_deliverable == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def mark_non_deliverable(self, contact_id: uuid.UUID) -> None:
        from sqlalchemy import update
        ctx = get_tenant_context()
        await self._session.execute(
            update(HRContact)
            .where(HRContact.id == contact_id, HRContact.tenant_id == ctx.org_id)
            .values(email_deliverable=False)
        )

    async def create(self, contact: HRContact) -> HRContact:
        self._session.add(contact)
        await self._session.flush()
        return contact
