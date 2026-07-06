"""Customer Success repository — Sprint 47."""

from __future__ import annotations

import base64
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.customer_success.models import CustomerSuccess


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(token: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(token.encode()).decode()
    ts_str, id_str = raw.split("|", 1)
    return datetime.fromisoformat(ts_str), uuid.UUID(id_str)


class CustomerSuccessRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: CustomerSuccess) -> CustomerSuccess:
        self._session.add(record)
        return record

    async def find_by_id(self, record_id: uuid.UUID) -> Optional[CustomerSuccess]:
        result = await self._session.execute(
            select(CustomerSuccess).where(CustomerSuccess.id == record_id)
        )
        return result.scalar_one_or_none()

    async def find_by_customer_id(self, customer_id: uuid.UUID) -> Optional[CustomerSuccess]:
        result = await self._session.execute(
            select(CustomerSuccess).where(CustomerSuccess.customer_id == customer_id)
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
        health_status: Optional[str] = None,
        risk_level: Optional[str] = None,
        owner_user_id: Optional[uuid.UUID] = None,
        renewal_date_from: Optional[date] = None,
        renewal_date_to: Optional[date] = None,
        followup_due_by: Optional[date] = None,
        expansion_opportunity: Optional[bool] = None,
        search: Optional[str] = None,
        include_archived: bool = False,
    ) -> int:
        q = select(func.count()).select_from(CustomerSuccess).where(
            CustomerSuccess.workspace_id == workspace_id
        )
        q = self._apply_filters(
            q, health_status, risk_level, owner_user_id, renewal_date_from,
            renewal_date_to, followup_due_by, expansion_opportunity, search, include_archived
        )
        result = await self._session.execute(q)
        return result.scalar_one()

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        health_status: Optional[str] = None,
        risk_level: Optional[str] = None,
        owner_user_id: Optional[uuid.UUID] = None,
        renewal_date_from: Optional[date] = None,
        renewal_date_to: Optional[date] = None,
        followup_due_by: Optional[date] = None,
        expansion_opportunity: Optional[bool] = None,
        search: Optional[str] = None,
        include_archived: bool = False,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> list[CustomerSuccess]:
        q = select(CustomerSuccess).where(CustomerSuccess.workspace_id == workspace_id)
        q = self._apply_filters(
            q, health_status, risk_level, owner_user_id, renewal_date_from,
            renewal_date_to, followup_due_by, expansion_opportunity, search, include_archived
        )
        if cursor:
            cur_ts, cur_id = decode_cursor(cursor)
            q = q.where(
                (CustomerSuccess.created_at < cur_ts)
                | (
                    (CustomerSuccess.created_at == cur_ts)
                    & (CustomerSuccess.id < cur_id)
                )
            )
        q = q.order_by(CustomerSuccess.created_at.desc(), CustomerSuccess.id.desc()).limit(limit + 1)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    def _apply_filters(
        self,
        q: Any,
        health_status: Optional[str],
        risk_level: Optional[str],
        owner_user_id: Optional[uuid.UUID],
        renewal_date_from: Optional[date],
        renewal_date_to: Optional[date],
        followup_due_by: Optional[date],
        expansion_opportunity: Optional[bool],
        search: Optional[str],
        include_archived: bool,
    ) -> Any:
        if not include_archived:
            q = q.where(CustomerSuccess.is_archived.is_(False))
        if health_status:
            q = q.where(CustomerSuccess.health_status == health_status)
        if risk_level:
            q = q.where(CustomerSuccess.risk_level == risk_level)
        if owner_user_id:
            q = q.where(CustomerSuccess.owner_user_id == owner_user_id)
        if renewal_date_from:
            q = q.where(CustomerSuccess.renewal_date >= renewal_date_from)
        if renewal_date_to:
            q = q.where(CustomerSuccess.renewal_date <= renewal_date_to)
        if followup_due_by:
            q = q.where(
                CustomerSuccess.next_followup_date.isnot(None),
                CustomerSuccess.next_followup_date <= followup_due_by,
            )
        if expansion_opportunity is not None:
            q = q.where(CustomerSuccess.expansion_opportunity == expansion_opportunity)
        if search:
            q = q.where(CustomerSuccess.notes.ilike(f"%{search}%"))
        return q
