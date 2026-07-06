"""Training services: Engagement, Session, Attendance, Certificate, Feedback — Sprint 42–46."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.training.models import (
    TrainingAttendance,
    TrainingCertificate,
    TrainingEngagement,
    TrainingFeedback,
    TrainingSession,
)
from corpmind.modules.training.repo import (
    TrainingAttendanceRepo,
    TrainingCertificateRepo,
    TrainingEngagementRepo,
    TrainingFeedbackRepo,
    TrainingSessionRepo,
    encode_cursor,
)
from corpmind.modules.training.schemas import (
    CancelEngagement,
    CancelSession,
    CheckOutAttendance,
    CompleteEngagement,
    CompleteSession,
    IssueCertificate,
    RevokeCertificate,
    TrainingAttendanceCreate,
    TrainingAttendanceFilters,
    TrainingAttendanceListOut,
    TrainingAttendanceOut,
    TrainingAttendanceUpdate,
    TrainingCertificateCreate,
    TrainingCertificateFilters,
    TrainingCertificateListOut,
    TrainingCertificateOut,
    TrainingCertificateUpdate,
    TrainingEngagementCreate,
    TrainingEngagementFilters,
    TrainingEngagementListOut,
    TrainingEngagementOut,
    TrainingEngagementUpdate,
    TrainingFeedbackCreate,
    TrainingFeedbackFilters,
    TrainingFeedbackListOut,
    TrainingFeedbackOut,
    TrainingFeedbackUpdate,
    TrainingSessionCreate,
    TrainingSessionFilters,
    TrainingSessionListOut,
    TrainingSessionOut,
    TrainingSessionUpdate,
)

log = structlog.get_logger(__name__)

_LIST_TTL = 300
_DETAIL_TTL = 300

# Valid status transitions
_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"scheduled", "in_progress", "cancelled"},
    "scheduled": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _list_key(org_id: uuid.UUID, ws_id: uuid.UUID) -> str:
    return f"t:{org_id}:{ws_id}:training:list"


def _detail_key(org_id: uuid.UUID, engagement_id: uuid.UUID) -> str:
    return f"t:{org_id}:training:detail:{engagement_id}"


class TrainingEngagementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TrainingEngagementRepo(session)

    async def create_engagement(self, req: TrainingEngagementCreate) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        engagement = TrainingEngagement(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            customer_id=req.customer_id,
            program_name=req.program_name,
            description=req.description,
            training_type=req.training_type,
            delivery_mode=req.delivery_mode,
            status=req.status,
            priority=req.priority,
            planned_start_date=req.planned_start_date,
            planned_end_date=req.planned_end_date,
            actual_start_date=None,
            actual_end_date=None,
            estimated_participants=req.estimated_participants,
            actual_participants=None,
            assigned_trainer_id=req.assigned_trainer_id,
            coordinator_id=req.coordinator_id,
            location=req.location,
            meeting_link=req.meeting_link,
            notes=req.notes,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(engagement)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, req.workspace_id)
        log.info(
            "training.created",
            engagement_id=str(engagement.id),
            tenant_id=str(ctx.org_id),
        )
        return TrainingEngagementOut.model_validate(engagement)

    async def get_engagement(self, engagement_id: uuid.UUID) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _detail_key(ctx.org_id, engagement_id)
        try:
            cached = await redis.get(key)
            if cached:
                return TrainingEngagementOut.model_validate_json(cached)
        except Exception:
            pass

        engagement = await self._repo.find_by_id(engagement_id)
        if not engagement:
            raise NotFoundError(f"Training engagement {engagement_id} not found")

        out = TrainingEngagementOut.model_validate(engagement)
        try:
            await redis.set(key, out.model_dump_json(), ex=_DETAIL_TTL)
        except Exception:
            pass
        return out

    async def update_engagement(
        self, engagement_id: uuid.UUID, req: TrainingEngagementUpdate
    ) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        engagement = await self._repo.find_by_id(engagement_id)
        if not engagement:
            raise NotFoundError(f"Training engagement {engagement_id} not found")

        fields: dict = {"updated_at": datetime.now(UTC)}
        for field_name, value in req.model_dump(exclude_none=True).items():
            fields[field_name] = value
        await self._repo.update_fields(engagement_id, **fields)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, engagement.workspace_id)
        await self._bust_detail_cache(ctx.org_id, engagement_id)
        return await self.get_engagement(engagement_id)

    async def _transition_status(
        self,
        engagement_id: uuid.UUID,
        target_status: str,
        extra_fields: dict | None = None,
    ) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        engagement = await self._repo.find_by_id(engagement_id)
        if not engagement:
            raise NotFoundError(f"Training engagement {engagement_id} not found")

        allowed = _TRANSITIONS.get(engagement.status, set())
        if target_status not in allowed:
            raise ValidationError(
                f"Cannot transition from '{engagement.status}' to '{target_status}'"
            )

        fields: dict = {"status": target_status, "updated_at": datetime.now(UTC)}
        if extra_fields:
            fields.update(extra_fields)
        await self._repo.update_fields(engagement_id, **fields)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, engagement.workspace_id)
        await self._bust_detail_cache(ctx.org_id, engagement_id)
        return await self.get_engagement(engagement_id)

    async def start_engagement(self, engagement_id: uuid.UUID) -> TrainingEngagementOut:
        return await self._transition_status(
            engagement_id,
            "in_progress",
            {"actual_start_date": datetime.now(UTC).date()},
        )

    async def complete_engagement(
        self, engagement_id: uuid.UUID, req: CompleteEngagement
    ) -> TrainingEngagementOut:
        extra: dict = {}
        if req.actual_end_date:
            extra["actual_end_date"] = req.actual_end_date
        else:
            extra["actual_end_date"] = datetime.now(UTC).date()
        if req.actual_participants is not None:
            extra["actual_participants"] = req.actual_participants
        if req.notes is not None:
            extra["notes"] = req.notes
        return await self._transition_status(engagement_id, "completed", extra)

    async def cancel_engagement(
        self, engagement_id: uuid.UUID, req: CancelEngagement
    ) -> TrainingEngagementOut:
        extra: dict = {}
        if req.notes is not None:
            extra["notes"] = req.notes
        return await self._transition_status(engagement_id, "cancelled", extra)

    async def assign_trainer(
        self, engagement_id: uuid.UUID, trainer_id: uuid.UUID
    ) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        engagement = await self._repo.find_by_id(engagement_id)
        if not engagement:
            raise NotFoundError(f"Training engagement {engagement_id} not found")

        await self._repo.update_fields(
            engagement_id,
            assigned_trainer_id=trainer_id,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, engagement.workspace_id)
        await self._bust_detail_cache(ctx.org_id, engagement_id)
        log.info(
            "training.trainer_assigned",
            engagement_id=str(engagement_id),
            trainer_id=str(trainer_id),
        )
        return await self.get_engagement(engagement_id)

    async def assign_coordinator(
        self, engagement_id: uuid.UUID, coordinator_id: uuid.UUID
    ) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        engagement = await self._repo.find_by_id(engagement_id)
        if not engagement:
            raise NotFoundError(f"Training engagement {engagement_id} not found")

        await self._repo.update_fields(
            engagement_id,
            coordinator_id=coordinator_id,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, engagement.workspace_id)
        await self._bust_detail_cache(ctx.org_id, engagement_id)
        return await self.get_engagement(engagement_id)

    async def list_engagements(
        self, filters: TrainingEngagementFilters
    ) -> TrainingEngagementListOut:
        ctx = get_tenant_context()
        is_default_query = not any([
            filters.status,
            filters.trainer_id,
            filters.customer_id,
            filters.delivery_mode,
            filters.date_from,
            filters.date_to,
            filters.search,
            filters.cursor,
        ]) and filters.limit == 50

        if is_default_query:
            redis = get_redis()
            key = _list_key(ctx.org_id, filters.workspace_id)
            try:
                cached = await redis.get(key)
                if cached:
                    return TrainingEngagementListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._repo.count(
            filters.workspace_id,
            status=filters.status,
            trainer_id=filters.trainer_id,
            customer_id=filters.customer_id,
            delivery_mode=filters.delivery_mode,
            date_from=filters.date_from,
            date_to=filters.date_to,
            search=filters.search,
        )
        rows = await self._repo.list_page(
            filters.workspace_id,
            status=filters.status,
            trainer_id=filters.trainer_id,
            customer_id=filters.customer_id,
            delivery_mode=filters.delivery_mode,
            date_from=filters.date_from,
            date_to=filters.date_to,
            search=filters.search,
            cursor=filters.cursor,
            limit=filters.limit,
        )

        next_cursor = None
        if len(rows) == filters.limit:
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)

        out = TrainingEngagementListOut(
            items=[TrainingEngagementOut.model_validate(r) for r in rows],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            total=total,
        )

        if is_default_query:
            redis = get_redis()
            try:
                key = _list_key(ctx.org_id, filters.workspace_id)
                await redis.set(key, out.model_dump_json(), ex=_LIST_TTL)
            except Exception:
                pass
        return out

    async def search_engagements(
        self, workspace_id: uuid.UUID, query: str, limit: int = 20
    ) -> list[TrainingEngagementOut]:
        filters = TrainingEngagementFilters(
            workspace_id=workspace_id, search=query, limit=limit
        )
        result = await self.list_engagements(filters)
        return result.items

    async def _bust_list_cache(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        try:
            redis = get_redis()
            await redis.delete(_list_key(org_id, workspace_id))
        except Exception:
            pass

    async def _bust_detail_cache(self, org_id: uuid.UUID, engagement_id: uuid.UUID) -> None:
        try:
            redis = get_redis()
            await redis.delete(_detail_key(org_id, engagement_id))
        except Exception:
            pass


# ── Session cache keys ────────────────────────────────────────────────────────

def _session_list_key(org_id: uuid.UUID, engagement_id: uuid.UUID) -> str:
    return f"t:{org_id}:training:sessions:list:{engagement_id}"


def _session_detail_key(org_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return f"t:{org_id}:training:sessions:detail:{session_id}"


# Valid session status transitions
_SESSION_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"scheduled", "in_progress", "cancelled"},
    "scheduled": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


class TrainingSessionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TrainingSessionRepo(session)

    async def create_session(self, req: TrainingSessionCreate) -> TrainingSessionOut:
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        obj = TrainingSession(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            engagement_id=req.engagement_id,
            session_name=req.session_name,
            session_number=req.session_number,
            status=req.status,
            scheduled_start=req.scheduled_start,
            scheduled_end=req.scheduled_end,
            actual_start=None,
            actual_end=None,
            trainer_id=req.trainer_id,
            location=req.location,
            meeting_link=req.meeting_link,
            capacity=req.capacity,
            expected_attendees=req.expected_attendees,
            actual_attendees=None,
            notes=req.notes,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(obj)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, req.engagement_id)
        log.info(
            "training.session.created",
            session_id=str(obj.id),
            engagement_id=str(req.engagement_id),
            tenant_id=str(ctx.org_id),
        )
        return TrainingSessionOut.model_validate(obj)

    async def get_session(self, session_id: uuid.UUID) -> TrainingSessionOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _session_detail_key(ctx.org_id, session_id)
        try:
            cached = await redis.get(key)
            if cached:
                return TrainingSessionOut.model_validate_json(cached)
        except Exception:
            pass

        obj = await self._repo.find_by_id(session_id)
        if not obj:
            raise NotFoundError(f"Training session {session_id} not found")

        out = TrainingSessionOut.model_validate(obj)
        try:
            await redis.set(key, out.model_dump_json(), ex=_LIST_TTL)
        except Exception:
            pass
        return out

    async def update_session(
        self, session_id: uuid.UUID, req: TrainingSessionUpdate
    ) -> TrainingSessionOut:
        ctx = get_tenant_context()
        obj = await self._repo.find_by_id(session_id)
        if not obj:
            raise NotFoundError(f"Training session {session_id} not found")

        fields: dict = {"updated_at": datetime.now(UTC)}
        for field_name, value in req.model_dump(exclude_none=True).items():
            fields[field_name] = value
        await self._repo.update_fields(session_id, **fields)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, obj.engagement_id)
        await self._bust_detail_cache(ctx.org_id, session_id)
        return await self.get_session(session_id)

    async def _transition_status(
        self,
        session_id: uuid.UUID,
        target_status: str,
        extra_fields: dict | None = None,
    ) -> TrainingSessionOut:
        ctx = get_tenant_context()
        obj = await self._repo.find_by_id(session_id)
        if not obj:
            raise NotFoundError(f"Training session {session_id} not found")

        allowed = _SESSION_TRANSITIONS.get(obj.status, set())
        if target_status not in allowed:
            raise ValidationError(
                f"Cannot transition session from '{obj.status}' to '{target_status}'"
            )

        fields: dict = {"status": target_status, "updated_at": datetime.now(UTC)}
        if extra_fields:
            fields.update(extra_fields)
        await self._repo.update_fields(session_id, **fields)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, obj.engagement_id)
        await self._bust_detail_cache(ctx.org_id, session_id)
        return await self.get_session(session_id)

    async def start_session(self, session_id: uuid.UUID) -> TrainingSessionOut:
        return await self._transition_status(
            session_id,
            "in_progress",
            {"actual_start": datetime.now(UTC)},
        )

    async def complete_session(
        self, session_id: uuid.UUID, req: CompleteSession
    ) -> TrainingSessionOut:
        extra: dict = {"actual_end": req.actual_end or datetime.now(UTC)}
        if req.actual_attendees is not None:
            extra["actual_attendees"] = req.actual_attendees
        if req.notes is not None:
            extra["notes"] = req.notes
        return await self._transition_status(session_id, "completed", extra)

    async def cancel_session(
        self, session_id: uuid.UUID, req: CancelSession
    ) -> TrainingSessionOut:
        extra: dict = {}
        if req.notes is not None:
            extra["notes"] = req.notes
        return await self._transition_status(session_id, "cancelled", extra)

    async def assign_trainer(
        self, session_id: uuid.UUID, trainer_id: uuid.UUID
    ) -> TrainingSessionOut:
        ctx = get_tenant_context()
        obj = await self._repo.find_by_id(session_id)
        if not obj:
            raise NotFoundError(f"Training session {session_id} not found")

        await self._repo.update_fields(
            session_id,
            trainer_id=trainer_id,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, obj.engagement_id)
        await self._bust_detail_cache(ctx.org_id, session_id)
        log.info(
            "training.session.trainer_assigned",
            session_id=str(session_id),
            trainer_id=str(trainer_id),
        )
        return await self.get_session(session_id)

    async def list_sessions(self, filters: TrainingSessionFilters) -> TrainingSessionListOut:
        ctx = get_tenant_context()
        no_extra_filters = not any([
            filters.trainer_id, filters.status,
            filters.date_from, filters.date_to, filters.cursor,
        ])
        is_engagement_only = (
            filters.engagement_id is not None
            and no_extra_filters
            and filters.limit == 50
        )

        if is_engagement_only:
            redis = get_redis()
            key = _session_list_key(ctx.org_id, filters.engagement_id)  # type: ignore[arg-type]
            try:
                cached = await redis.get(key)
                if cached:
                    return TrainingSessionListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._repo.count(
            filters.workspace_id,
            engagement_id=filters.engagement_id,
            trainer_id=filters.trainer_id,
            status=filters.status,
            date_from=filters.date_from,
            date_to=filters.date_to,
        )
        rows = await self._repo.list_page(
            filters.workspace_id,
            engagement_id=filters.engagement_id,
            trainer_id=filters.trainer_id,
            status=filters.status,
            date_from=filters.date_from,
            date_to=filters.date_to,
            cursor=filters.cursor,
            limit=filters.limit,
        )

        next_cursor = None
        if len(rows) == filters.limit:
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)

        out = TrainingSessionListOut(
            items=[TrainingSessionOut.model_validate(r) for r in rows],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            total=total,
        )

        if is_engagement_only and filters.engagement_id:
            redis = get_redis()
            try:
                await redis.set(
                    _session_list_key(ctx.org_id, filters.engagement_id),
                    out.model_dump_json(),
                    ex=_LIST_TTL,
                )
            except Exception:
                pass
        return out

    async def list_by_engagement(self, engagement_id: uuid.UUID) -> list[TrainingSessionOut]:
        rows = await self._repo.list_by_engagement(engagement_id)
        return [TrainingSessionOut.model_validate(r) for r in rows]

    async def list_by_trainer(
        self, workspace_id: uuid.UUID, trainer_id: uuid.UUID
    ) -> list[TrainingSessionOut]:
        rows = await self._repo.list_by_trainer(workspace_id, trainer_id)
        return [TrainingSessionOut.model_validate(r) for r in rows]

    async def _bust_list_cache(self, org_id: uuid.UUID, engagement_id: uuid.UUID) -> None:
        try:
            redis = get_redis()
            await redis.delete(_session_list_key(org_id, engagement_id))
        except Exception:
            pass

    async def _bust_detail_cache(self, org_id: uuid.UUID, session_id: uuid.UUID) -> None:
        try:
            redis = get_redis()
            await redis.delete(_session_detail_key(org_id, session_id))
        except Exception:
            pass


# ── Attendance cache keys ─────────────────────────────────────────────────────

def _attendance_list_key(org_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return f"t:{org_id}:training:attendance:list:{session_id}"


def _attendance_detail_key(org_id: uuid.UUID, attendance_id: uuid.UUID) -> str:
    return f"t:{org_id}:training:attendance:detail:{attendance_id}"


class TrainingAttendanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TrainingAttendanceRepo(session)

    async def register_participant(
        self, req: TrainingAttendanceCreate
    ) -> TrainingAttendanceOut:
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        obj = TrainingAttendance(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            session_id=req.session_id,
            participant_name=req.participant_name,
            participant_email=req.participant_email,
            participant_phone=req.participant_phone,
            company=req.company,
            designation=req.designation,
            attendance_status=req.attendance_status,
            check_in_time=req.check_in_time,
            check_out_time=None,
            completion_percent=req.completion_percent,
            certificate_eligible=req.certificate_eligible,
            remarks=req.remarks,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(obj)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, req.session_id)
        log.info(
            "training.attendance.registered",
            attendance_id=str(obj.id),
            session_id=str(req.session_id),
            tenant_id=str(ctx.org_id),
        )
        return TrainingAttendanceOut.model_validate(obj)

    async def get_participant(self, attendance_id: uuid.UUID) -> TrainingAttendanceOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _attendance_detail_key(ctx.org_id, attendance_id)
        try:
            cached = await redis.get(key)
            if cached:
                return TrainingAttendanceOut.model_validate_json(cached)
        except Exception:
            pass

        obj = await self._repo.find_by_id(attendance_id)
        if not obj:
            raise NotFoundError(f"Attendance record {attendance_id} not found")

        out = TrainingAttendanceOut.model_validate(obj)
        try:
            await redis.set(key, out.model_dump_json(), ex=_DETAIL_TTL)
        except Exception:
            pass
        return out

    async def update_participant(
        self, attendance_id: uuid.UUID, req: TrainingAttendanceUpdate
    ) -> TrainingAttendanceOut:
        ctx = get_tenant_context()
        obj = await self._repo.find_by_id(attendance_id)
        if not obj:
            raise NotFoundError(f"Attendance record {attendance_id} not found")

        fields: dict = {"updated_at": datetime.now(UTC)}
        for field_name, value in req.model_dump(exclude_none=True).items():
            fields[field_name] = value
        await self._repo.update_fields(attendance_id, **fields)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, obj.session_id)
        await self._bust_detail_cache(ctx.org_id, attendance_id)
        return await self.get_participant(attendance_id)

    async def _set_status(
        self,
        attendance_id: uuid.UUID,
        status: str,
        extra_fields: dict | None = None,
    ) -> TrainingAttendanceOut:
        ctx = get_tenant_context()
        obj = await self._repo.find_by_id(attendance_id)
        if not obj:
            raise NotFoundError(f"Attendance record {attendance_id} not found")

        fields: dict = {"attendance_status": status, "updated_at": datetime.now(UTC)}
        if extra_fields:
            fields.update(extra_fields)
        await self._repo.update_fields(attendance_id, **fields)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, obj.session_id)
        await self._bust_detail_cache(ctx.org_id, attendance_id)
        return await self.get_participant(attendance_id)

    async def mark_present(self, attendance_id: uuid.UUID) -> TrainingAttendanceOut:
        return await self._set_status(attendance_id, "present")

    async def mark_late(self, attendance_id: uuid.UUID) -> TrainingAttendanceOut:
        return await self._set_status(attendance_id, "late")

    async def mark_absent(self, attendance_id: uuid.UUID) -> TrainingAttendanceOut:
        return await self._set_status(attendance_id, "absent")

    async def mark_left_early(self, attendance_id: uuid.UUID) -> TrainingAttendanceOut:
        return await self._set_status(attendance_id, "left_early")

    async def check_out(
        self, attendance_id: uuid.UUID, req: CheckOutAttendance
    ) -> TrainingAttendanceOut:
        obj = await self._repo.find_by_id(attendance_id)
        if not obj:
            raise NotFoundError(f"Attendance record {attendance_id} not found")

        extra: dict = {
            "check_out_time": req.check_out_time or datetime.now(UTC),
        }
        if req.completion_percent is not None:
            extra["completion_percent"] = req.completion_percent
        if req.certificate_eligible is not None:
            extra["certificate_eligible"] = req.certificate_eligible
        return await self._set_status(attendance_id, "left_early", extra)

    async def list_attendance(
        self, filters: TrainingAttendanceFilters
    ) -> TrainingAttendanceListOut:
        ctx = get_tenant_context()
        is_session_only = (
            filters.session_id is not None
            and filters.attendance_status is None
            and filters.company is None
            and filters.search is None
            and filters.cursor is None
            and filters.limit == 50
        )

        if is_session_only:
            redis = get_redis()
            key = _attendance_list_key(ctx.org_id, filters.session_id)  # type: ignore[arg-type]
            try:
                cached = await redis.get(key)
                if cached:
                    return TrainingAttendanceListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._repo.count(
            filters.workspace_id,
            session_id=filters.session_id,
            attendance_status=filters.attendance_status,
            company=filters.company,
            search=filters.search,
        )
        rows = await self._repo.list_page(
            filters.workspace_id,
            session_id=filters.session_id,
            attendance_status=filters.attendance_status,
            company=filters.company,
            search=filters.search,
            cursor=filters.cursor,
            limit=filters.limit,
        )

        next_cursor = None
        if len(rows) == filters.limit:
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)

        out = TrainingAttendanceListOut(
            items=[TrainingAttendanceOut.model_validate(r) for r in rows],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            total=total,
        )

        if is_session_only and filters.session_id:
            redis = get_redis()
            try:
                await redis.set(
                    _attendance_list_key(ctx.org_id, filters.session_id),
                    out.model_dump_json(),
                    ex=_LIST_TTL,
                )
            except Exception:
                pass
        return out

    async def list_by_session(self, session_id: uuid.UUID) -> list[TrainingAttendanceOut]:
        rows = await self._repo.list_by_session(session_id)
        return [TrainingAttendanceOut.model_validate(r) for r in rows]

    async def search_participants(
        self, workspace_id: uuid.UUID, session_id: uuid.UUID, query: str, limit: int = 20
    ) -> list[TrainingAttendanceOut]:
        rows = await self._repo.search_participants(workspace_id, session_id, query, limit)
        return [TrainingAttendanceOut.model_validate(r) for r in rows]

    async def _bust_list_cache(self, org_id: uuid.UUID, session_id: uuid.UUID) -> None:
        try:
            redis = get_redis()
            await redis.delete(_attendance_list_key(org_id, session_id))
        except Exception:
            pass

    async def _bust_detail_cache(self, org_id: uuid.UUID, attendance_id: uuid.UUID) -> None:
        try:
            redis = get_redis()
            await redis.delete(_attendance_detail_key(org_id, attendance_id))
        except Exception:
            pass


# ── Certificate cache keys ────────────────────────────────────────────────────

def _cert_list_key(org_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return f"t:{org_id}:training:certificates:list:{session_id}"


def _cert_detail_key(org_id: uuid.UUID, cert_id: uuid.UUID) -> str:
    return f"t:{org_id}:training:certificates:detail:{cert_id}"


class TrainingCertificateService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TrainingCertificateRepo(session)
        self._attendance_repo = TrainingAttendanceRepo(session)

    async def create_certificate(
        self, req: TrainingCertificateCreate
    ) -> TrainingCertificateOut:
        ctx = get_tenant_context()

        attendance = await self._attendance_repo.find_by_id(req.attendance_id)
        if not attendance:
            raise NotFoundError(f"Attendance record {req.attendance_id} not found")
        if not attendance.certificate_eligible:
            raise ValidationError(
                "attendance record is not marked certificate_eligible"
            )

        now = datetime.now(UTC)
        verification_code = secrets.token_urlsafe(12)
        cert = TrainingCertificate(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            attendance_id=req.attendance_id,
            session_id=req.session_id,
            participant_name=attendance.participant_name,
            participant_email=attendance.participant_email,
            certificate_title=req.certificate_title,
            status="draft",
            download_count=0,
            verification_code=verification_code,
            notes=req.notes,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(cert)
        await self._session.commit()
        await self._bust_cert_list_cache(ctx.org_id, req.session_id)

        log.info(
            "certificate.created",
            certificate_id=str(cert.id),
            attendance_id=str(req.attendance_id),
            tenant_id=str(ctx.org_id),
        )
        return TrainingCertificateOut.model_validate(cert)

    async def get_certificate(self, cert_id: uuid.UUID) -> TrainingCertificateOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _cert_detail_key(ctx.org_id, cert_id)
        try:
            cached = await redis.get(key)
            if cached:
                return TrainingCertificateOut.model_validate_json(cached)
        except Exception:
            pass

        cert = await self._repo.find_by_id(cert_id)
        if not cert:
            raise NotFoundError(f"Certificate {cert_id} not found")

        out = TrainingCertificateOut.model_validate(cert)
        try:
            await redis.set(key, out.model_dump_json(), ex=_DETAIL_TTL)
        except Exception:
            pass
        return out

    async def update_certificate(
        self, cert_id: uuid.UUID, req: TrainingCertificateUpdate
    ) -> TrainingCertificateOut:
        ctx = get_tenant_context()
        cert = await self._repo.find_by_id(cert_id)
        if not cert:
            raise NotFoundError(f"Certificate {cert_id} not found")
        if cert.status != "draft":
            raise ValidationError("only draft certificates can be updated")

        fields: dict = {"updated_at": datetime.now(UTC)}
        for field_name, value in req.model_dump(exclude_none=True).items():
            fields[field_name] = value
        await self._repo.update_fields(cert_id, **fields)
        await self._session.commit()
        await self._bust_cert_detail_cache(ctx.org_id, cert_id)
        await self._bust_cert_list_cache(ctx.org_id, cert.session_id)
        return await self.get_certificate(cert_id)

    async def issue_certificate(
        self, cert_id: uuid.UUID, req: IssueCertificate
    ) -> TrainingCertificateOut:
        ctx = get_tenant_context()
        cert = await self._repo.find_by_id(cert_id)
        if not cert:
            raise NotFoundError(f"Certificate {cert_id} not found")
        if cert.status != "draft":
            raise ValidationError("only draft certificates can be issued")

        fields: dict = {"status": "issued", "updated_at": datetime.now(UTC)}
        if req.issue_date is not None:
            fields["issue_date"] = req.issue_date
        if req.issued_by is not None:
            fields["issued_by"] = req.issued_by
        if req.certificate_number is not None:
            fields["certificate_number"] = req.certificate_number
        if req.certificate_title is not None:
            fields["certificate_title"] = req.certificate_title

        await self._repo.update_fields(cert_id, **fields)
        await self._session.commit()
        await self._bust_cert_detail_cache(ctx.org_id, cert_id)
        await self._bust_cert_list_cache(ctx.org_id, cert.session_id)

        log.info(
            "certificate.issued",
            certificate_id=str(cert_id),
            tenant_id=str(ctx.org_id),
        )
        return await self.get_certificate(cert_id)

    async def revoke_certificate(
        self, cert_id: uuid.UUID, req: RevokeCertificate
    ) -> TrainingCertificateOut:
        ctx = get_tenant_context()
        cert = await self._repo.find_by_id(cert_id)
        if not cert:
            raise NotFoundError(f"Certificate {cert_id} not found")
        if cert.status == "revoked":
            raise ValidationError("certificate is already revoked")

        fields: dict = {"status": "revoked", "updated_at": datetime.now(UTC)}
        if req.notes is not None:
            fields["notes"] = req.notes

        await self._repo.update_fields(cert_id, **fields)
        await self._session.commit()
        await self._bust_cert_detail_cache(ctx.org_id, cert_id)
        await self._bust_cert_list_cache(ctx.org_id, cert.session_id)

        log.info(
            "certificate.revoked",
            certificate_id=str(cert_id),
            tenant_id=str(ctx.org_id),
        )
        return await self.get_certificate(cert_id)

    async def list_certificates(
        self, filters: TrainingCertificateFilters
    ) -> TrainingCertificateListOut:
        ctx = get_tenant_context()
        is_session_only = (
            filters.session_id is not None
            and filters.status is None
            and filters.issued_by is None
            and filters.search is None
            and filters.cursor is None
            and filters.limit == 50
        )

        if is_session_only:
            redis = get_redis()
            key = _cert_list_key(ctx.org_id, filters.session_id)  # type: ignore[arg-type]
            try:
                cached = await redis.get(key)
                if cached:
                    return TrainingCertificateListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._repo.count(
            filters.workspace_id,
            session_id=filters.session_id,
            status=filters.status,
            issued_by=filters.issued_by,
            search=filters.search,
        )
        rows = await self._repo.list_page(
            filters.workspace_id,
            session_id=filters.session_id,
            status=filters.status,
            issued_by=filters.issued_by,
            search=filters.search,
            cursor=filters.cursor,
            limit=filters.limit,
        )

        next_cursor = None
        if len(rows) == filters.limit:
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)

        out = TrainingCertificateListOut(
            items=[TrainingCertificateOut.model_validate(r) for r in rows],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            total=total,
        )

        if is_session_only and filters.session_id:
            redis = get_redis()
            try:
                await redis.set(
                    _cert_list_key(ctx.org_id, filters.session_id),
                    out.model_dump_json(),
                    ex=_LIST_TTL,
                )
            except Exception:
                pass
        return out

    async def verify_certificate(self, verification_code: str) -> TrainingCertificateOut:
        cert = await self._repo.find_by_verification_code(verification_code)
        if not cert:
            raise NotFoundError(f"Certificate with code {verification_code!r} not found")
        return TrainingCertificateOut.model_validate(cert)

    async def _bust_cert_list_cache(
        self, org_id: uuid.UUID, session_id: uuid.UUID
    ) -> None:
        try:
            redis = get_redis()
            await redis.delete(_cert_list_key(org_id, session_id))
        except Exception:
            pass

    async def _bust_cert_detail_cache(
        self, org_id: uuid.UUID, cert_id: uuid.UUID
    ) -> None:
        try:
            redis = get_redis()
            await redis.delete(_cert_detail_key(org_id, cert_id))
        except Exception:
            pass


# ── Feedback cache keys ───────────────────────────────────────────────────────

def _feedback_list_key(org_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return f"t:{org_id}:training:feedback:list:{session_id}"


def _feedback_detail_key(org_id: uuid.UUID, feedback_id: uuid.UUID) -> str:
    return f"t:{org_id}:training:feedback:detail:{feedback_id}"


class TrainingFeedbackService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TrainingFeedbackRepo(session)
        self._attendance_repo = TrainingAttendanceRepo(session)

    async def create_feedback(
        self, req: TrainingFeedbackCreate
    ) -> TrainingFeedbackOut:
        ctx = get_tenant_context()

        attendance = await self._attendance_repo.find_by_id(req.attendance_id)
        if not attendance:
            raise NotFoundError(f"Attendance record {req.attendance_id} not found")

        existing = await self._repo.find_by_attendance_id(req.attendance_id)
        if existing:
            raise ValidationError(
                f"Feedback already exists for attendance {req.attendance_id}"
            )

        now = datetime.now(UTC)
        feedback = TrainingFeedback(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            attendance_id=req.attendance_id,
            session_id=req.session_id,
            customer_id=req.customer_id,
            trainer_id=req.trainer_id,
            overall_rating=req.overall_rating,
            trainer_rating=req.trainer_rating,
            content_rating=req.content_rating,
            materials_rating=req.materials_rating,
            venue_rating=req.venue_rating,
            would_recommend=req.would_recommend,
            comments=req.comments,
            submitted_at=req.submitted_at or now,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(feedback)
        await self._session.commit()
        await self._bust_feedback_list_cache(ctx.org_id, req.session_id)

        log.info(
            "training.feedback.created",
            feedback_id=str(feedback.id),
            session_id=str(req.session_id),
            tenant_id=str(ctx.org_id),
        )
        return TrainingFeedbackOut.model_validate(feedback)

    async def get_feedback(self, feedback_id: uuid.UUID) -> TrainingFeedbackOut:
        ctx = get_tenant_context()
        key = _feedback_detail_key(ctx.org_id, feedback_id)
        redis = get_redis()
        try:
            cached = await redis.get(key)
            if cached:
                return TrainingFeedbackOut.model_validate_json(cached)
        except Exception:
            pass

        feedback = await self._repo.find_by_id(feedback_id)
        if not feedback:
            raise NotFoundError(f"Feedback {feedback_id} not found")

        out = TrainingFeedbackOut.model_validate(feedback)
        try:
            await redis.set(key, out.model_dump_json(), ex=_DETAIL_TTL)
        except Exception:
            pass
        return out

    async def update_feedback(
        self, feedback_id: uuid.UUID, req: TrainingFeedbackUpdate
    ) -> TrainingFeedbackOut:
        ctx = get_tenant_context()
        feedback = await self._repo.find_by_id(feedback_id)
        if not feedback:
            raise NotFoundError(f"Feedback {feedback_id} not found")

        fields: dict = {"updated_at": datetime.now(UTC)}
        for attr in (
            "overall_rating",
            "trainer_rating",
            "content_rating",
            "materials_rating",
            "venue_rating",
            "would_recommend",
            "comments",
        ):
            val = getattr(req, attr)
            if val is not None:
                fields[attr] = val

        await self._repo.update_fields(feedback_id, **fields)
        await self._session.commit()
        await self._bust_feedback_detail_cache(ctx.org_id, feedback_id)
        await self._bust_feedback_list_cache(ctx.org_id, feedback.session_id)

        log.info(
            "training.feedback.updated",
            feedback_id=str(feedback_id),
            tenant_id=str(ctx.org_id),
        )
        return await self.get_feedback(feedback_id)

    async def list_feedback(
        self, filters: TrainingFeedbackFilters
    ) -> TrainingFeedbackListOut:
        ctx = get_tenant_context()
        is_session_only = (
            filters.session_id is not None
            and filters.customer_id is None
            and filters.trainer_id is None
            and filters.min_rating is None
            and filters.search is None
            and filters.cursor is None
            and filters.limit == 50
        )

        if is_session_only:
            redis = get_redis()
            key = _feedback_list_key(ctx.org_id, filters.session_id)  # type: ignore[arg-type]
            try:
                cached = await redis.get(key)
                if cached:
                    return TrainingFeedbackListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._repo.count(
            filters.workspace_id,
            session_id=filters.session_id,
            customer_id=filters.customer_id,
            trainer_id=filters.trainer_id,
            min_rating=filters.min_rating,
            search=filters.search,
        )
        rows = await self._repo.list_page(
            filters.workspace_id,
            session_id=filters.session_id,
            customer_id=filters.customer_id,
            trainer_id=filters.trainer_id,
            min_rating=filters.min_rating,
            search=filters.search,
            cursor=filters.cursor,
            limit=filters.limit,
        )

        next_cursor = None
        if len(rows) == filters.limit:
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)

        out = TrainingFeedbackListOut(
            items=[TrainingFeedbackOut.model_validate(r) for r in rows],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            total=total,
        )

        if is_session_only and filters.session_id:
            redis = get_redis()
            try:
                await redis.set(
                    _feedback_list_key(ctx.org_id, filters.session_id),
                    out.model_dump_json(),
                    ex=_LIST_TTL,
                )
            except Exception:
                pass
        return out

    async def list_by_session(
        self, session_id: uuid.UUID
    ) -> list[TrainingFeedbackOut]:
        rows = await self._repo.list_by_session(session_id)
        return [TrainingFeedbackOut.model_validate(r) for r in rows]

    async def list_by_customer(
        self, workspace_id: uuid.UUID, customer_id: uuid.UUID
    ) -> list[TrainingFeedbackOut]:
        rows = await self._repo.list_by_customer(workspace_id, customer_id)
        return [TrainingFeedbackOut.model_validate(r) for r in rows]

    async def list_by_trainer(
        self, workspace_id: uuid.UUID, trainer_id: uuid.UUID
    ) -> list[TrainingFeedbackOut]:
        rows = await self._repo.list_by_trainer(workspace_id, trainer_id)
        return [TrainingFeedbackOut.model_validate(r) for r in rows]

    async def _bust_feedback_list_cache(
        self, org_id: uuid.UUID, session_id: uuid.UUID
    ) -> None:
        try:
            redis = get_redis()
            await redis.delete(_feedback_list_key(org_id, session_id))
        except Exception:
            pass

    async def _bust_feedback_detail_cache(
        self, org_id: uuid.UUID, feedback_id: uuid.UUID
    ) -> None:
        try:
            redis = get_redis()
            await redis.delete(_feedback_detail_key(org_id, feedback_id))
        except Exception:
            pass
