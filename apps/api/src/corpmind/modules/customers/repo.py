"""Customer repository — cursor-paginated reads, full-text search, tenant-isolated."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.customers.models import Customer


# ── Cursor helpers ─────────────────────────────────────────────────────────────

def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    """Encode (created_at_iso, id) as a URL-safe base64 cursor token."""
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(token: str) -> tuple[datetime, uuid.UUID]:
    """Decode cursor token back to (created_at, id). Raises ValueError on malformed input."""
    raw = base64.urlsafe_b64decode(token.encode()).decode()
    ts_str, id_str = raw.split("|", 1)
    return datetime.fromisoformat(ts_str), uuid.UUID(id_str)


# ── Repository ─────────────────────────────────────────────────────────────────

class CustomerRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, customer: Customer) -> Customer:
        self._session.add(customer)
        await self._session.flush()
        return customer

    async def find_by_id(self, customer_id: uuid.UUID) -> Customer | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_fields(self, customer_id: uuid.UUID, **values: Any) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(Customer)
            .where(
                Customer.id == customer_id,
                Customer.tenant_id == ctx.org_id,
            )
            .values(**values)
        )

    async def count(
        self,
        workspace_id: uuid.UUID,
        *,
        status: str | None = None,
        industry: str | None = None,
        health_status: str | None = None,
        owner_id: uuid.UUID | None = None,
        search: str | None = None,
    ) -> int:
        ctx = get_tenant_context()
        stmt = (
            select(func.count())
            .select_from(Customer)
            .where(
                Customer.workspace_id == workspace_id,
                Customer.tenant_id == ctx.org_id,
                Customer.status != "archived",
            )
        )
        stmt = self._apply_filters(stmt, status, industry, health_status, owner_id, search)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        status: str | None = None,
        industry: str | None = None,
        health_status: str | None = None,
        owner_id: uuid.UUID | None = None,
        search: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> list[Customer]:
        ctx = get_tenant_context()
        stmt = (
            select(Customer)
            .where(
                Customer.workspace_id == workspace_id,
                Customer.tenant_id == ctx.org_id,
                Customer.status != "archived",
            )
        )
        stmt = self._apply_filters(stmt, status, industry, health_status, owner_id, search)

        if cursor:
            cursor_created_at, cursor_id = decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    Customer.created_at < cursor_created_at,
                    and_(
                        Customer.created_at == cursor_created_at,
                        Customer.id < cursor_id,
                    ),
                )
            )

        stmt = stmt.order_by(Customer.created_at.desc(), Customer.id.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def _apply_filters(
        self,
        stmt: Any,
        status: str | None,
        industry: str | None,
        health_status: str | None,
        owner_id: uuid.UUID | None,
        search: str | None,
    ) -> Any:
        if status:
            stmt = stmt.where(Customer.status == status)
        if industry:
            stmt = stmt.where(Customer.industry == industry)
        if health_status:
            stmt = stmt.where(Customer.health_status == health_status)
        if owner_id:
            stmt = stmt.where(Customer.relationship_owner_id == owner_id)
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Customer.company_name).like(pattern),
                    func.lower(Customer.display_name).like(pattern),
                )
            )
        return stmt
