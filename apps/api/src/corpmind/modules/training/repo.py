"""Training Engagement repository — Sprint 42."""

from __future__ import annotations

import base64
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.training.models import TrainingEngagement


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(token: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(token.encode()).decode()
    ts_str, id_str = raw.split("|", 1)
    return datetime.fromisoformat(ts_str), uuid.UUID(id_str)


class TrainingEngagementRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, engagement: TrainingEngagement) -> TrainingEngagement:
        self._session.add(engagement)
        return engagement

    async def find_by_id(self, engagement_id: uuid.UUID) -> Optional[TrainingEngagement]:
        result = await self._session.execute(
            select(TrainingEngagement).where(TrainingEngagement.id == engagement_id)
        )
        return result.scalar_one_or_none()

    async def update_fields(self, engagement_id: uuid.UUID, **values: Any) -> None:
        engagement = await self.find_by_id(engagement_id)
        if engagement:
            for key, value in values.items():
                setattr(engagement, key, value)

    async def count(
        self,
        workspace_id: uuid.UUID,
        *,
        status: Optional[str] = None,
        trainer_id: Optional[uuid.UUID] = None,
        customer_id: Optional[uuid.UUID] = None,
        delivery_mode: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        search: Optional[str] = None,
    ) -> int:
        q = select(func.count()).select_from(TrainingEngagement).where(
            TrainingEngagement.workspace_id == workspace_id
        )
        q = self._apply_filters(
            q, status, trainer_id, customer_id, delivery_mode, date_from, date_to, search
        )
        result = await self._session.execute(q)
        return result.scalar_one()

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        status: Optional[str] = None,
        trainer_id: Optional[uuid.UUID] = None,
        customer_id: Optional[uuid.UUID] = None,
        delivery_mode: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        search: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> list[TrainingEngagement]:
        q = select(TrainingEngagement).where(
            TrainingEngagement.workspace_id == workspace_id
        )
        q = self._apply_filters(
            q, status, trainer_id, customer_id, delivery_mode, date_from, date_to, search
        )
        if cursor:
            cursor_ts, cursor_id = decode_cursor(cursor)
            q = q.where(
                (TrainingEngagement.created_at < cursor_ts)
                | (
                    (TrainingEngagement.created_at == cursor_ts)
                    & (TrainingEngagement.id < cursor_id)
                )
            )
        q = q.order_by(
            TrainingEngagement.created_at.desc(), TrainingEngagement.id.desc()
        ).limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    def _apply_filters(
        self,
        q: Any,
        status: Optional[str],
        trainer_id: Optional[uuid.UUID],
        customer_id: Optional[uuid.UUID],
        delivery_mode: Optional[str],
        date_from: Optional[date],
        date_to: Optional[date],
        search: Optional[str],
    ) -> Any:
        if status:
            q = q.where(TrainingEngagement.status == status)
        if trainer_id:
            q = q.where(TrainingEngagement.assigned_trainer_id == trainer_id)
        if customer_id:
            q = q.where(TrainingEngagement.customer_id == customer_id)
        if delivery_mode:
            q = q.where(TrainingEngagement.delivery_mode == delivery_mode)
        if date_from:
            q = q.where(TrainingEngagement.planned_start_date >= date_from)
        if date_to:
            q = q.where(TrainingEngagement.planned_start_date <= date_to)
        if search:
            q = q.where(
                func.lower(TrainingEngagement.program_name).like(f"%{search.lower()}%")
            )
        return q
