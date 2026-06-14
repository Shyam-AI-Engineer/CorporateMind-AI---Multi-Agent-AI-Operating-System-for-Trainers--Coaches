"""HR discovery repository."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.hr_discovery.models import Company, HRContact


@dataclass
class ContactFilters:
    company_id: uuid.UUID | None = None
    limit: int = 50
    offset: int = 0


class CompanyRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_name(self, name: str) -> Company | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Company).where(
                Company.tenant_id == ctx.org_id,
                func.lower(Company.name) == name.lower(),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, company: Company) -> Company:
        self._session.add(company)
        await self._session.flush()
        return company

    async def get_or_create(self, name: str, **fields: object) -> tuple[Company, bool]:
        """Return (company, created). Idempotent by normalised lowercase name."""
        existing = await self.find_by_name(name)
        if existing:
            return existing, False
        ctx = get_tenant_context()
        company = Company(tenant_id=ctx.org_id, name=name, **fields)
        await self.create(company)
        return company, True

    async def search_by_industries(
        self,
        industries: list[str],
        employee_ranges: list[str],
        limit: int = 200,
    ) -> list[Company]:
        """Return companies matching the given industry and employee-range filters.

        When ``industries`` is empty, all tenant companies are returned (up to
        ``limit``).  Each filter is optional; passing both narrows the result set.
        Results are ordered newest-first so freshly-imported companies surface at
        the top of the discovery pool.
        """
        ctx = get_tenant_context()
        stmt = (
            select(Company)
            .where(Company.tenant_id == ctx.org_id)
            .order_by(Company.created_at.desc())
            .limit(limit)
        )
        if industries:
            industries_lower = [i.lower() for i in industries]
            stmt = stmt.where(func.lower(Company.industry).in_(industries_lower))
        if employee_ranges:
            stmt = stmt.where(Company.employee_count_range.in_(employee_ranges))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class HRContactRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, contact_id: uuid.UUID) -> HRContact | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(HRContact).where(
                HRContact.id == contact_id,
                HRContact.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

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

    async def count_contacts(self, filters: ContactFilters) -> int:
        ctx = get_tenant_context()
        stmt = (
            select(func.count())
            .select_from(HRContact)
            .where(
                HRContact.tenant_id == ctx.org_id,
                HRContact.is_contactable == True,  # noqa: E712
                HRContact.email_deliverable == True,  # noqa: E712
            )
        )
        if filters.company_id:
            stmt = stmt.where(HRContact.company_id == filters.company_id)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_contacts(self, filters: ContactFilters) -> list[HRContact]:
        ctx = get_tenant_context()
        stmt = (
            select(HRContact)
            .where(
                HRContact.tenant_id == ctx.org_id,
                HRContact.is_contactable == True,  # noqa: E712
                HRContact.email_deliverable == True,  # noqa: E712
            )
            .order_by(HRContact.created_at.desc())
            .limit(filters.limit)
            .offset(filters.offset)
        )
        if filters.company_id:
            stmt = stmt.where(HRContact.company_id == filters.company_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_many_by_ids(self, contact_ids: list[uuid.UUID]) -> list[HRContact]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(HRContact).where(
                HRContact.tenant_id == ctx.org_id,
                HRContact.id.in_(contact_ids),
            )
        )
        return list(result.scalars().all())

    async def create(self, contact: HRContact) -> HRContact:
        self._session.add(contact)
        await self._session.flush()
        return contact

    async def mark_non_deliverable(self, contact_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(HRContact)
            .where(HRContact.id == contact_id, HRContact.tenant_id == ctx.org_id)
            .values(email_deliverable=False)
        )
