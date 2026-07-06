"""Customer Renewal repository — Sprint 48."""

from __future__ import annotations

import base64
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.customer_renewals.models import CustomerRenewal


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(token: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(token.encode()).decode()
    ts_str, id_str = raw.split("|", 1)
    return datetime.fromisoformat(ts_str), uuid.UUID(id_str)


class CustomerRenewalRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: CustomerRenewal) -> CustomerRenewal:
        self._session.add(record)
        return record

    async def find_by_id(self, record_id: uuid.UUID) -> Optional[CustomerRenewal]:
        result = await self._session.execute(
            select(CustomerRenewal).where(CustomerRenewal.id == record_id)
        )
        return result.scalar_one_or_none()

    async def find_by_customer_id(
        self, customer_id: uuid.UUID
    ) -> list[CustomerRenewal]:
        result = await self._session.execute(
            select(CustomerRenewal)
            .where(
                CustomerRenewal.customer_id == customer_id,
                CustomerRenewal.is_archived.is_(False),
            )
            .order_by(CustomerRenewal.renewal_date.asc().nulls_last())
        )
        return list(result.scalars().all())

    async def find_next_renewal_by_customer(
        self, customer_id: uuid.UUID
    ) -> Optional[CustomerRenewal]:
        result = await self._session.execute(
            select(CustomerRenewal)
            .where(
                CustomerRenewal.customer_id == customer_id,
                CustomerRenewal.is_archived.is_(False),
                CustomerRenewal.renewal_status.in_(
                    ["planned", "in_progress", "negotiation"]
                ),
            )
            .order_by(CustomerRenewal.renewal_date.asc().nulls_last())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_fields(self, record_id: uuid.UUID, **values: Any) -> None:
        record = await self.find_by_id(record_id)
        if record:
            for key, value in values.items():
                setattr(record, key, value)

    async def count(
        self,
        workspace_id: uuid.UUID,
        *,
        customer_id: Optional[uuid.UUID] = None,
        renewal_type: Optional[str] = None,
        renewal_status: Optional[str] = None,
        owner_user_id: Optional[uuid.UUID] = None,
        renewal_date_from: Optional[date] = None,
        renewal_date_to: Optional[date] = None,
        search: Optional[str] = None,
        include_archived: bool = False,
    ) -> int:
        q = select(func.count()).select_from(CustomerRenewal).where(
            CustomerRenewal.workspace_id == workspace_id
        )
        q = self._apply_filters(
            q, customer_id, renewal_type, renewal_status, owner_user_id,
            renewal_date_from, renewal_date_to, search, include_archived,
        )
        result = await self._session.execute(q)
        return result.scalar_one()

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        customer_id: Optional[uuid.UUID] = None,
        renewal_type: Optional[str] = None,
        renewal_status: Optional[str] = None,
        owner_user_id: Optional[uuid.UUID] = None,
        renewal_date_from: Optional[date] = None,
        renewal_date_to: Optional[date] = None,
        search: Optional[str] = None,
        include_archived: bool = False,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> list[CustomerRenewal]:
        q = select(CustomerRenewal).where(
            CustomerRenewal.workspace_id == workspace_id
        )
        q = self._apply_filters(
            q, customer_id, renewal_type, renewal_status, owner_user_id,
            renewal_date_from, renewal_date_to, search, include_archived,
        )
        if cursor:
            cur_ts, cur_id = decode_cursor(cursor)
            q = q.where(
                (CustomerRenewal.created_at < cur_ts)
                | (
                    (CustomerRenewal.created_at == cur_ts)
                    & (CustomerRenewal.id < cur_id)
                )
            )
        q = q.order_by(
            CustomerRenewal.created_at.desc(), CustomerRenewal.id.desc()
        ).limit(limit + 1)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    def _apply_filters(
        self,
        q: Any,
        customer_id: Optional[uuid.UUID],
        renewal_type: Optional[str],
        renewal_status: Optional[str],
        owner_user_id: Optional[uuid.UUID],
        renewal_date_from: Optional[date],
        renewal_date_to: Optional[date],
        search: Optional[str],
        include_archived: bool,
    ) -> Any:
        if not include_archived:
            q = q.where(CustomerRenewal.is_archived.is_(False))
        if customer_id:
            q = q.where(CustomerRenewal.customer_id == customer_id)
        if renewal_type:
            q = q.where(CustomerRenewal.renewal_type == renewal_type)
        if renewal_status:
            q = q.where(CustomerRenewal.renewal_status == renewal_status)
        if owner_user_id:
            q = q.where(CustomerRenewal.owner_user_id == owner_user_id)
        if renewal_date_from:
            q = q.where(CustomerRenewal.renewal_date >= renewal_date_from)
        if renewal_date_to:
            q = q.where(CustomerRenewal.renewal_date <= renewal_date_to)
        if search:
            q = q.where(
                or_(
                    CustomerRenewal.contract_name.ilike(f"%{search}%"),
                    CustomerRenewal.notes.ilike(f"%{search}%"),
                )
            )
        return q
