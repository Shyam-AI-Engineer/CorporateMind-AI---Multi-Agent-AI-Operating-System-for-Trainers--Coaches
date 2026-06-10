"""CRM service — lead pipeline lifecycle management.

State machine
─────────────
discovered ──advance──► engaged ──advance──► meeting_scheduled
           ──advance──► meeting_completed ──advance──► booked
any-non-terminal ──mark_lost──► lost

One active lead per contact per workspace.  Terminal stages: booked | lost.
Re-engagement creates a new lead once the prior one is terminal.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.crm.events import LeadStageChanged, MeetingBooked
from corpmind.modules.crm.models import Lead
from corpmind.modules.crm.repo import ActivityRepo, FollowUpTaskRepo, LeadRepo
from corpmind.modules.crm.schemas import (
    ActivityListOut,
    ActivityOut,
    FollowUpTaskListOut,
    FollowUpTaskOut,
    LeadCreate,
    LeadListOut,
    LeadOut,
    PipelineStageCount,
    PipelineStats,
    StageAdvanceResponse,
)

log = structlog.get_logger(__name__)

# Forward-only transition map: current stage → next stage
_STAGE_TRANSITIONS: dict[str, str] = {
    "discovered": "engaged",
    "engaged": "meeting_scheduled",
    "meeting_scheduled": "meeting_completed",
    "meeting_completed": "booked",
}

_TERMINAL_STAGES = frozenset({"booked", "lost"})

# Canonical order for the funnel stats display
_ALL_STAGES = ("discovered", "engaged", "meeting_scheduled", "meeting_completed", "booked", "lost")


class CRMService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = LeadRepo(session)

    # ── Creation ──────────────────────────────────────────────────────────────

    async def create_lead(self, req: LeadCreate) -> LeadOut:
        """Create a new lead for a contact.

        Idempotent per workspace: raises ConflictError if the contact already
        has an active (non-terminal) lead.  Allows re-engagement after
        booked/lost.
        """
        ctx = get_tenant_context()
        existing = await self._repo.find_active_by_contact(req.contact_id, req.workspace_id)
        if existing:
            raise ConflictError(
                f"Contact {req.contact_id} already has an active lead "
                f"({existing.id}) in stage '{existing.stage}'."
            )
        lead = Lead(
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            contact_id=req.contact_id,
            stage="discovered",
            score=req.score,
            notes=req.notes,
        )
        await self._repo.create(lead)
        await self._session.commit()
        log.info(
            "crm.lead_created",
            lead_id=str(lead.id),
            contact_id=str(req.contact_id),
            workspace_id=str(req.workspace_id),
        )
        return LeadOut.model_validate(lead)

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_lead(self, lead_id: uuid.UUID) -> LeadOut:
        return LeadOut.model_validate(await self._require_lead(lead_id))

    async def list_pipeline(
        self,
        workspace_id: uuid.UUID,
        *,
        stage: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> LeadListOut:
        if stage and stage not in (*_ALL_STAGES,):
            raise ValidationError(
                f"Invalid stage '{stage}'. Valid values: {', '.join(_ALL_STAGES)}"
            )
        leads, total = await asyncio.gather(
            self._repo.list_pipeline(workspace_id, stage=stage, limit=limit, offset=offset),
            self._repo.count_pipeline(workspace_id, stage=stage),
        )
        return LeadListOut(
            items=[LeadOut.model_validate(lead) for lead in leads],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_pipeline_stats(self, workspace_id: uuid.UUID) -> PipelineStats:
        """Return per-stage counts in canonical funnel order."""
        counts = await self._repo.count_by_stage(workspace_id)
        stages = [
            PipelineStageCount(stage=s, count=counts.get(s, 0))
            for s in _ALL_STAGES
        ]
        return PipelineStats(
            workspace_id=workspace_id,
            stages=stages,
            total=sum(sc.count for sc in stages),
        )

    # ── State transitions ─────────────────────────────────────────────────────

    async def advance_stage(
        self, lead_id: uuid.UUID, *, notes: str | None = None
    ) -> StageAdvanceResponse:
        """Advance the lead to the next stage in sequence.

        Cannot skip stages.  Raises ConflictError if already terminal.
        Automatically sets booked_at when transitioning to 'booked'.
        """
        lead = await self._require_lead(lead_id)
        if lead.stage in _TERMINAL_STAGES:
            raise ConflictError(
                f"Lead is in terminal stage '{lead.stage}' and cannot be advanced."
            )
        next_stage = _STAGE_TRANSITIONS.get(lead.stage)
        if next_stage is None:
            raise ConflictError(f"No forward transition defined from stage '{lead.stage}'.")

        from_stage = lead.stage
        values: dict[str, object] = {"stage": next_stage}
        if notes is not None:
            values["notes"] = notes
        if next_stage == "booked":
            values["booked_at"] = datetime.now(UTC)

        await self._repo.update_fields(lead_id, **values)
        await self._session.commit()

        log.info(
            "crm.lead_advanced",
            lead_id=str(lead_id),
            from_stage=from_stage,
            to_stage=next_stage,
        )
        # Emit domain events (bus to be wired in Phase 2)
        _log_event(LeadStageChanged(
            lead_id=lead_id, tenant_id=lead.tenant_id,
            from_stage=from_stage, to_stage=next_stage,
        ))
        if next_stage == "booked":
            _log_event(MeetingBooked(
                lead_id=lead_id, tenant_id=lead.tenant_id, contact_id=lead.contact_id,
            ))

        return StageAdvanceResponse(lead_id=lead_id, from_stage=from_stage, to_stage=next_stage)

    async def mark_lost(
        self, lead_id: uuid.UUID, *, notes: str | None = None
    ) -> LeadOut:
        """Transition a lead to 'lost' from any non-terminal stage."""
        lead = await self._require_lead(lead_id)
        if lead.stage in _TERMINAL_STAGES:
            raise ConflictError(
                f"Lead is already in terminal stage '{lead.stage}'."
            )
        from_stage = lead.stage
        # Capture tenant_id before commit expires ORM attributes
        tenant_id = lead.tenant_id
        values: dict[str, object] = {"stage": "lost"}
        if notes is not None:
            values["notes"] = notes

        # Apply updates in-memory so model_validate sees the new state
        for k, v in values.items():
            setattr(lead, k, v)
        response = LeadOut.model_validate(lead)

        await self._repo.update_fields(lead_id, **values)
        await self._session.commit()

        log.info("crm.lead_lost", lead_id=str(lead_id), from_stage=from_stage)
        _log_event(LeadStageChanged(
            lead_id=lead_id, tenant_id=tenant_id,
            from_stage=from_stage, to_stage="lost",
        ))

        return response

    # ── Metadata updates ──────────────────────────────────────────────────────

    async def update_score(self, lead_id: uuid.UUID, score: int) -> LeadOut:
        lead = await self._require_lead(lead_id)
        lead.score = score
        response = LeadOut.model_validate(lead)
        await self._repo.update_fields(lead_id, score=score)
        await self._session.commit()
        return response

    async def add_note(self, lead_id: uuid.UUID, notes: str) -> LeadOut:
        lead = await self._require_lead(lead_id)
        lead.notes = notes
        response = LeadOut.model_validate(lead)
        await self._repo.update_fields(lead_id, notes=notes)
        await self._session.commit()
        return response

    async def schedule_meeting(
        self, lead_id: uuid.UUID, meeting_at: datetime
    ) -> LeadOut:
        """Record the meeting datetime for a lead in 'meeting_scheduled' stage."""
        lead = await self._require_lead(lead_id)
        if lead.stage != "meeting_scheduled":
            raise ConflictError(
                f"Cannot set meeting time for a lead in stage '{lead.stage}'. "
                "Advance to 'meeting_scheduled' first."
            )
        lead.meeting_scheduled_at = meeting_at
        response = LeadOut.model_validate(lead)
        await self._repo.update_fields(lead_id, meeting_scheduled_at=meeting_at)
        await self._session.commit()
        return response

    # ── Activity + follow-up read surface (Sprint 5 prerequisite) ─────────────

    async def list_activities(
        self,
        *,
        workspace_id: uuid.UUID | None = None,
        lead_id: uuid.UUID | None = None,
        contact_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ActivityListOut:
        """Paginated CRM activity list — used by the Activity Timeline UI.

        Tenant-scope is enforced by ActivityRepo via TenantContext.  At least
        one of workspace_id / lead_id / contact_id must be set; the route
        validates that, not this method.
        """
        repo = ActivityRepo(self._session)
        items, total = await asyncio.gather(
            repo.list_filtered(
                workspace_id=workspace_id,
                lead_id=lead_id,
                contact_id=contact_id,
                limit=limit,
                offset=offset,
            ),
            repo.count_filtered(
                workspace_id=workspace_id,
                lead_id=lead_id,
                contact_id=contact_id,
            ),
        )
        return ActivityListOut(
            items=[ActivityOut.model_validate(a) for a in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_follow_up_tasks(
        self,
        *,
        workspace_id: uuid.UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> FollowUpTaskListOut:
        """Paginated follow-up task list — used by the Follow-Up Queue UI."""
        repo = FollowUpTaskRepo(self._session)
        items, total = await asyncio.gather(
            repo.list_filtered(
                workspace_id=workspace_id,
                status=status,
                limit=limit,
                offset=offset,
            ),
            repo.count_filtered(workspace_id=workspace_id, status=status),
        )
        return FollowUpTaskListOut(
            items=[FollowUpTaskOut.model_validate(t) for t in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _require_lead(self, lead_id: uuid.UUID) -> Lead:
        lead = await self._repo.find_by_id(lead_id)
        if not lead:
            raise NotFoundError(f"Lead {lead_id} not found")
        return lead


def _log_event(event: object) -> None:
    """Structured-log a domain event until a real event bus is wired up."""
    log.info("crm.domain_event", event_type=type(event).__name__, payload=repr(event))
