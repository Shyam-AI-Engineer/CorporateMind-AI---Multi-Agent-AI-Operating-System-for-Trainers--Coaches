"""Training Engagement, Session, Attendance, Certificate, and Feedback repositories — Sprint 42–46."""

from __future__ import annotations

import base64
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.training.models import (
    TrainingAttendance,
    TrainingCertificate,
    TrainingEngagement,
    TrainingFeedback,
    TrainingSession,
)


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


class TrainingSessionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, session_obj: TrainingSession) -> TrainingSession:
        self._session.add(session_obj)
        return session_obj

    async def find_by_id(self, session_id: uuid.UUID) -> Optional[TrainingSession]:
        result = await self._session.execute(
            select(TrainingSession).where(TrainingSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def update_fields(self, session_id: uuid.UUID, **values: Any) -> None:
        obj = await self.find_by_id(session_id)
        if obj:
            for key, value in values.items():
                setattr(obj, key, value)

    async def count(
        self,
        workspace_id: uuid.UUID,
        *,
        engagement_id: Optional[uuid.UUID] = None,
        trainer_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> int:
        q = select(func.count()).select_from(TrainingSession).where(
            TrainingSession.workspace_id == workspace_id
        )
        q = self._apply_session_filters(q, engagement_id, trainer_id, status, date_from, date_to)
        result = await self._session.execute(q)
        return result.scalar_one()

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        engagement_id: Optional[uuid.UUID] = None,
        trainer_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> list[TrainingSession]:
        q = select(TrainingSession).where(TrainingSession.workspace_id == workspace_id)
        q = self._apply_session_filters(q, engagement_id, trainer_id, status, date_from, date_to)
        if cursor:
            cursor_ts, cursor_id = decode_cursor(cursor)
            q = q.where(
                (TrainingSession.created_at < cursor_ts)
                | (
                    (TrainingSession.created_at == cursor_ts)
                    & (TrainingSession.id < cursor_id)
                )
            )
        q = q.order_by(
            TrainingSession.created_at.desc(), TrainingSession.id.desc()
        ).limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def list_by_engagement(self, engagement_id: uuid.UUID) -> list[TrainingSession]:
        result = await self._session.execute(
            select(TrainingSession)
            .where(TrainingSession.engagement_id == engagement_id)
            .order_by(
                TrainingSession.session_number.asc().nulls_last(),
                TrainingSession.scheduled_start.asc().nulls_last(),
                TrainingSession.created_at.asc(),
            )
        )
        return list(result.scalars().all())

    async def list_by_trainer(
        self, workspace_id: uuid.UUID, trainer_id: uuid.UUID
    ) -> list[TrainingSession]:
        result = await self._session.execute(
            select(TrainingSession)
            .where(
                TrainingSession.workspace_id == workspace_id,
                TrainingSession.trainer_id == trainer_id,
            )
            .order_by(TrainingSession.scheduled_start.asc().nulls_last())
        )
        return list(result.scalars().all())

    def _apply_session_filters(
        self,
        q: Any,
        engagement_id: Optional[uuid.UUID],
        trainer_id: Optional[uuid.UUID],
        status: Optional[str],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> Any:
        if engagement_id:
            q = q.where(TrainingSession.engagement_id == engagement_id)
        if trainer_id:
            q = q.where(TrainingSession.trainer_id == trainer_id)
        if status:
            q = q.where(TrainingSession.status == status)
        if date_from:
            q = q.where(TrainingSession.scheduled_start >= date_from)
        if date_to:
            q = q.where(TrainingSession.scheduled_start <= date_to)
        return q


class TrainingAttendanceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, attendance: TrainingAttendance) -> TrainingAttendance:
        self._session.add(attendance)
        return attendance

    async def find_by_id(self, attendance_id: uuid.UUID) -> Optional[TrainingAttendance]:
        result = await self._session.execute(
            select(TrainingAttendance).where(TrainingAttendance.id == attendance_id)
        )
        return result.scalar_one_or_none()

    async def update_fields(self, attendance_id: uuid.UUID, **values: Any) -> None:
        obj = await self.find_by_id(attendance_id)
        if obj:
            for key, value in values.items():
                setattr(obj, key, value)

    async def delete(self, attendance_id: uuid.UUID) -> bool:
        obj = await self.find_by_id(attendance_id)
        if obj:
            await self._session.delete(obj)
            return True
        return False

    async def count(
        self,
        workspace_id: uuid.UUID,
        *,
        session_id: Optional[uuid.UUID] = None,
        attendance_status: Optional[str] = None,
        company: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        q = select(func.count()).select_from(TrainingAttendance).where(
            TrainingAttendance.workspace_id == workspace_id
        )
        q = self._apply_filters(q, session_id, attendance_status, company, search)
        result = await self._session.execute(q)
        return result.scalar_one()

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        session_id: Optional[uuid.UUID] = None,
        attendance_status: Optional[str] = None,
        company: Optional[str] = None,
        search: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> list[TrainingAttendance]:
        q = select(TrainingAttendance).where(
            TrainingAttendance.workspace_id == workspace_id
        )
        q = self._apply_filters(q, session_id, attendance_status, company, search)
        if cursor:
            cursor_ts, cursor_id = decode_cursor(cursor)
            q = q.where(
                (TrainingAttendance.created_at < cursor_ts)
                | (
                    (TrainingAttendance.created_at == cursor_ts)
                    & (TrainingAttendance.id < cursor_id)
                )
            )
        q = q.order_by(
            TrainingAttendance.created_at.desc(), TrainingAttendance.id.desc()
        ).limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def list_by_session(self, session_id: uuid.UUID) -> list[TrainingAttendance]:
        result = await self._session.execute(
            select(TrainingAttendance)
            .where(TrainingAttendance.session_id == session_id)
            .order_by(
                TrainingAttendance.participant_name.asc(),
                TrainingAttendance.created_at.asc(),
            )
        )
        return list(result.scalars().all())

    async def search_participants(
        self,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        query: str,
        limit: int = 20,
    ) -> list[TrainingAttendance]:
        term = f"%{query.lower()}%"
        result = await self._session.execute(
            select(TrainingAttendance)
            .where(
                TrainingAttendance.workspace_id == workspace_id,
                TrainingAttendance.session_id == session_id,
                or_(
                    func.lower(TrainingAttendance.participant_name).like(term),
                    func.lower(TrainingAttendance.participant_email).like(term),
                    func.lower(TrainingAttendance.company).like(term),
                ),
            )
            .order_by(TrainingAttendance.participant_name.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    def _apply_filters(
        self,
        q: Any,
        session_id: Optional[uuid.UUID],
        attendance_status: Optional[str],
        company: Optional[str],
        search: Optional[str],
    ) -> Any:
        if session_id:
            q = q.where(TrainingAttendance.session_id == session_id)
        if attendance_status:
            q = q.where(TrainingAttendance.attendance_status == attendance_status)
        if company:
            q = q.where(
                func.lower(TrainingAttendance.company).like(f"%{company.lower()}%")
            )
        if search:
            term = f"%{search.lower()}%"
            q = q.where(
                or_(
                    func.lower(TrainingAttendance.participant_name).like(term),
                    func.lower(TrainingAttendance.participant_email).like(term),
                    func.lower(TrainingAttendance.company).like(term),
                )
            )
        return q


class TrainingCertificateRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, cert: TrainingCertificate) -> TrainingCertificate:
        self._session.add(cert)
        return cert

    async def find_by_id(self, cert_id: uuid.UUID) -> Optional[TrainingCertificate]:
        result = await self._session.execute(
            select(TrainingCertificate).where(TrainingCertificate.id == cert_id)
        )
        return result.scalar_one_or_none()

    async def find_by_verification_code(
        self, code: str
    ) -> Optional[TrainingCertificate]:
        result = await self._session.execute(
            select(TrainingCertificate).where(
                TrainingCertificate.verification_code == code
            )
        )
        return result.scalar_one_or_none()

    async def update_fields(self, cert_id: uuid.UUID, **values: Any) -> None:
        obj = await self.find_by_id(cert_id)
        if obj:
            for key, value in values.items():
                setattr(obj, key, value)

    async def count(
        self,
        workspace_id: uuid.UUID,
        *,
        session_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        issued_by: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        q = select(func.count()).select_from(TrainingCertificate).where(
            TrainingCertificate.workspace_id == workspace_id
        )
        q = self._apply_cert_filters(q, session_id, status, issued_by, search)
        result = await self._session.execute(q)
        return result.scalar_one()

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        session_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        issued_by: Optional[str] = None,
        search: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> list[TrainingCertificate]:
        q = select(TrainingCertificate).where(
            TrainingCertificate.workspace_id == workspace_id
        )
        q = self._apply_cert_filters(q, session_id, status, issued_by, search)
        if cursor:
            cursor_ts, cursor_id = decode_cursor(cursor)
            q = q.where(
                (TrainingCertificate.created_at < cursor_ts)
                | (
                    (TrainingCertificate.created_at == cursor_ts)
                    & (TrainingCertificate.id < cursor_id)
                )
            )
        q = q.order_by(
            TrainingCertificate.created_at.desc(), TrainingCertificate.id.desc()
        ).limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    def _apply_cert_filters(
        self,
        q: Any,
        session_id: Optional[uuid.UUID],
        status: Optional[str],
        issued_by: Optional[str],
        search: Optional[str],
    ) -> Any:
        if session_id:
            q = q.where(TrainingCertificate.session_id == session_id)
        if status:
            q = q.where(TrainingCertificate.status == status)
        if issued_by:
            q = q.where(
                func.lower(TrainingCertificate.issued_by).like(
                    f"%{issued_by.lower()}%"
                )
            )
        if search:
            term = f"%{search.lower()}%"
            q = q.where(
                or_(
                    func.lower(TrainingCertificate.participant_name).like(term),
                    func.lower(TrainingCertificate.participant_email).like(term),
                    func.lower(TrainingCertificate.certificate_number).like(term),
                )
            )
        return q


class TrainingFeedbackRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, feedback: TrainingFeedback) -> TrainingFeedback:
        self._session.add(feedback)
        return feedback

    async def find_by_id(self, feedback_id: uuid.UUID) -> Optional[TrainingFeedback]:
        result = await self._session.execute(
            select(TrainingFeedback).where(TrainingFeedback.id == feedback_id)
        )
        return result.scalar_one_or_none()

    async def find_by_attendance_id(
        self, attendance_id: uuid.UUID
    ) -> Optional[TrainingFeedback]:
        result = await self._session.execute(
            select(TrainingFeedback).where(
                TrainingFeedback.attendance_id == attendance_id
            )
        )
        return result.scalar_one_or_none()

    async def update_fields(self, feedback_id: uuid.UUID, **values: Any) -> None:
        obj = await self.find_by_id(feedback_id)
        if obj:
            for key, value in values.items():
                setattr(obj, key, value)

    async def count(
        self,
        workspace_id: uuid.UUID,
        *,
        session_id: Optional[uuid.UUID] = None,
        customer_id: Optional[uuid.UUID] = None,
        trainer_id: Optional[uuid.UUID] = None,
        min_rating: Optional[int] = None,
        search: Optional[str] = None,
    ) -> int:
        q = select(func.count()).select_from(TrainingFeedback).where(
            TrainingFeedback.workspace_id == workspace_id
        )
        q = self._apply_filters(q, session_id, customer_id, trainer_id, min_rating, search)
        result = await self._session.execute(q)
        return result.scalar_one()

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        session_id: Optional[uuid.UUID] = None,
        customer_id: Optional[uuid.UUID] = None,
        trainer_id: Optional[uuid.UUID] = None,
        min_rating: Optional[int] = None,
        search: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> list[TrainingFeedback]:
        q = select(TrainingFeedback).where(
            TrainingFeedback.workspace_id == workspace_id
        )
        q = self._apply_filters(q, session_id, customer_id, trainer_id, min_rating, search)
        if cursor:
            cursor_ts, cursor_id = decode_cursor(cursor)
            q = q.where(
                (TrainingFeedback.created_at < cursor_ts)
                | (
                    (TrainingFeedback.created_at == cursor_ts)
                    & (TrainingFeedback.id < cursor_id)
                )
            )
        q = q.order_by(
            TrainingFeedback.created_at.desc(), TrainingFeedback.id.desc()
        ).limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def list_by_session(self, session_id: uuid.UUID) -> list[TrainingFeedback]:
        result = await self._session.execute(
            select(TrainingFeedback)
            .where(TrainingFeedback.session_id == session_id)
            .order_by(TrainingFeedback.submitted_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_customer(
        self, workspace_id: uuid.UUID, customer_id: uuid.UUID
    ) -> list[TrainingFeedback]:
        result = await self._session.execute(
            select(TrainingFeedback)
            .where(
                TrainingFeedback.workspace_id == workspace_id,
                TrainingFeedback.customer_id == customer_id,
            )
            .order_by(TrainingFeedback.submitted_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_trainer(
        self, workspace_id: uuid.UUID, trainer_id: uuid.UUID
    ) -> list[TrainingFeedback]:
        result = await self._session.execute(
            select(TrainingFeedback)
            .where(
                TrainingFeedback.workspace_id == workspace_id,
                TrainingFeedback.trainer_id == trainer_id,
            )
            .order_by(TrainingFeedback.submitted_at.desc())
        )
        return list(result.scalars().all())

    def _apply_filters(
        self,
        q: Any,
        session_id: Optional[uuid.UUID],
        customer_id: Optional[uuid.UUID],
        trainer_id: Optional[uuid.UUID],
        min_rating: Optional[int],
        search: Optional[str],
    ) -> Any:
        if session_id:
            q = q.where(TrainingFeedback.session_id == session_id)
        if customer_id:
            q = q.where(TrainingFeedback.customer_id == customer_id)
        if trainer_id:
            q = q.where(TrainingFeedback.trainer_id == trainer_id)
        if min_rating is not None:
            q = q.where(TrainingFeedback.overall_rating >= min_rating)
        if search:
            term = f"%{search.lower()}%"
            q = q.where(func.lower(TrainingFeedback.comments).like(term))
        return q
