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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.crm.events import (
    BookingWebhookReceived,
    LeadStageChanged,
    MeetingAutoScheduled,
    MeetingBooked,
)
from corpmind.modules.crm.models import Activity, Lead
from corpmind.modules.crm.repo import (
    ActivityRepo,
    BookingWebhookEventRepo,
    FollowUpTaskRepo,
    LeadRepo,
)
from corpmind.modules.crm.schemas import (
    ActivityListOut,
    ActivityOut,
    BookingWebhookPayload,
    FollowUpTaskListOut,
    FollowUpTaskOut,
    IndustryAnalysisItem,
    IndustryAnalysisOut,
    LeadConversionOut,
    LeadCreate,
    LeadListOut,
    LeadOut,
    LeadPipelineSummaryOut,
    PipelineStageCount,
    PipelineStats,
    SourceAnalysisItem,
    SourceAnalysisOut,
    StageAdvanceResponse,
    StageAnalysisItem,
    StageAnalysisOut,
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

    # ── Booking webhook automation (Sprint 14 — ADR-0009) ────────────────────

    async def process_booking_event(
        self,
        workspace_id: uuid.UUID,
        payload: BookingWebhookPayload,
    ) -> None:
        """Process a verified inbound booking webhook event.

        Idempotency: BookingWebhookEventRepo.reserve() inserts a row with
        UNIQUE(tenant_id, provider, provider_event_id); duplicates return early.

        Contact matching: cross-module read via raw SQL (module boundary rule
        forbids importing hr_discovery.repo / hr_discovery.models directly).
        """
        ctx = get_tenant_context()
        booking_repo = BookingWebhookEventRepo(self._session)

        _log_event(BookingWebhookReceived(
            workspace_id=workspace_id,
            tenant_id=ctx.org_id,
            provider=payload.provider,
            provider_event_id=payload.provider_event_id,
            event_type=payload.event_type,
        ))

        event_id = await booking_repo.reserve(
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            provider=payload.provider,
            provider_event_id=payload.provider_event_id,
            event_type=payload.event_type,
            invitee_email=payload.invitee_email,
            scheduled_at=payload.scheduled_at,
            raw_payload=payload.model_dump(mode="json"),
        )
        if event_id is None:
            log.info(
                "booking_webhook.duplicate",
                provider=payload.provider,
                provider_event_id=payload.provider_event_id,
            )
            return

        if payload.event_type not in {"booking.created", "booking.rescheduled"}:
            await booking_repo.mark_outcome(event_id, outcome="skipped")
            log.info("booking_webhook.skipped_type", event_type=payload.event_type)
            return

        # Cross-module: find HR contact by invitee email (raw SQL).
        result = await self._session.execute(
            text(
                "SELECT id FROM hr_contacts "
                "WHERE tenant_id = :tid AND lower(email) = lower(:email) "
                "LIMIT 1"
            ),
            {"tid": str(ctx.org_id), "email": payload.invitee_email},
        )
        row = result.first()
        if not row:
            await booking_repo.mark_outcome(event_id, outcome="skipped")
            log.info(
                "booking_webhook.contact_not_found",
                provider_event_id=payload.provider_event_id,
            )
            return
        contact_id: uuid.UUID = uuid.UUID(str(row[0]))

        lead = await self._repo.find_active_by_contact_any_workspace(contact_id)
        if not lead:
            await booking_repo.mark_outcome(event_id, outcome="skipped")
            log.info(
                "booking_webhook.no_active_lead",
                contact_id=str(contact_id),
            )
            return

        await self._repo.update_fields(
            lead.id,
            meeting_scheduled_at=payload.scheduled_at,
            booking_provider_event_id=payload.provider_event_id,
        )

        scheduled_label = (
            payload.scheduled_at.strftime("%b %d, %Y at %I:%M %p")
            if payload.scheduled_at
            else "time TBD"
        )
        activity = Activity(
            tenant_id=ctx.org_id,
            workspace_id=lead.workspace_id,
            lead_id=lead.id,
            contact_id=contact_id,
            type="booking_confirmed",
            summary=f"Meeting auto-scheduled via {payload.provider} for {scheduled_label}",
        )
        await ActivityRepo(self._session).create(activity)

        await booking_repo.mark_outcome(event_id, outcome="applied", lead_id=lead.id)

        _log_event(MeetingAutoScheduled(
            lead_id=lead.id,
            tenant_id=ctx.org_id,
            contact_id=contact_id,
            scheduled_at=payload.scheduled_at,
            provider=payload.provider,
            provider_event_id=payload.provider_event_id,
        ))

        log.info(
            "booking_webhook.applied",
            lead_id=str(lead.id),
            provider=payload.provider,
            provider_event_id=payload.provider_event_id,
        )

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


# ── Lead Pipeline Analytics — Sprint 40 ───────────────────────────────────────

_PIPELINE_TTL = 900

# Stage order for funnel analysis (terminal stages handled separately)
_STAGE_ORDER = ["discovered", "engaged", "meeting_scheduled", "meeting_completed", "booked"]
_TERMINAL_STAGES = {"booked", "lost"}
_QUALIFIED_STAGES = {"meeting_completed", "booked"}


def _pipeline_summary_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:lead_pipeline_summary"


def _pipeline_stages_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:lead_pipeline_stages"


def _pipeline_sources_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:lead_pipeline_sources"


def _pipeline_industries_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:lead_pipeline_industries"


def _pipeline_conversion_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:lead_pipeline_conversion"


class LeadPipelineAnalyticsService:
    """Read-only analytics over the CRM lead pipeline.

    All methods are strictly read-only: no writes, no mutations, no AI.
    Cross-table access (hr_contacts, companies) uses raw SQL to avoid
    cross-module model imports.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_summary(self, workspace_id: uuid.UUID) -> LeadPipelineSummaryOut:
        from corpmind.core.redis import get_redis

        ctx = get_tenant_context()
        key = _pipeline_summary_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return LeadPipelineSummaryOut.model_validate_json(cached)
        except Exception:
            pass

        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        l.stage,
                        COUNT(*) AS cnt,
                        SUM(CASE WHEN l.updated_at < l.created_at THEN 1 ELSE 0 END) AS bad_ts
                    FROM leads l
                    WHERE l.tenant_id = :tenant_id
                      AND l.workspace_id = :workspace_id
                    GROUP BY l.stage
                    """
                ),
                {"tenant_id": ctx.org_id, "workspace_id": workspace_id},
            )
        ).fetchall()

        stage_counts: dict[str, int] = {}
        bad_ts_total = 0
        for row in rows:
            stage_counts[row.stage] = int(row.cnt)
            bad_ts_total += int(row.bad_ts)

        # Proposal-linked leads (subquery avoids cross-module model import)
        proposal_row = (
            await self._session.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT l.id) AS cnt
                    FROM leads l
                    JOIN proposals p ON p.lead_id = l.id AND p.tenant_id = l.tenant_id
                    WHERE l.tenant_id = :tenant_id
                      AND l.workspace_id = :workspace_id
                    """
                ),
                {"tenant_id": ctx.org_id, "workspace_id": workspace_id},
            )
        ).fetchone()

        total_leads = sum(stage_counts.values())
        won_leads = stage_counts.get("booked", 0)
        lost_leads = stage_counts.get("lost", 0)
        qualified_leads = stage_counts.get("meeting_completed", 0)
        active_leads = total_leads - won_leads - lost_leads
        proposal_leads = int(proposal_row.cnt) if proposal_row else 0
        overall_conversion_rate = round(won_leads / total_leads * 100, 2) if total_leads > 0 else 0.0
        pipeline_health_score = round(
            (won_leads + qualified_leads) / total_leads * 100, 1
        ) if total_leads > 0 else 0.0

        result = LeadPipelineSummaryOut(
            total_leads=total_leads,
            active_leads=active_leads,
            qualified_leads=qualified_leads,
            proposal_leads=proposal_leads,
            won_leads=won_leads,
            lost_leads=lost_leads,
            overall_conversion_rate=overall_conversion_rate,
            pipeline_health_score=pipeline_health_score,
            data_integrity_warning=bad_ts_total > 0,
        )
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_PIPELINE_TTL)
        except Exception:
            pass
        return result

    async def get_stage_analysis(self, workspace_id: uuid.UUID) -> StageAnalysisOut:
        from corpmind.core.redis import get_redis

        ctx = get_tenant_context()
        key = _pipeline_stages_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return StageAnalysisOut.model_validate_json(cached)
        except Exception:
            pass

        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        l.stage,
                        COUNT(*) AS cnt,
                        AVG(
                            EXTRACT(EPOCH FROM (NOW() - l.created_at)) / 86400.0
                        ) AS avg_days
                    FROM leads l
                    WHERE l.tenant_id = :tenant_id
                      AND l.workspace_id = :workspace_id
                    GROUP BY l.stage
                    """
                ),
                {"tenant_id": ctx.org_id, "workspace_id": workspace_id},
            )
        ).fetchall()

        stage_counts: dict[str, int] = {r.stage: int(r.cnt) for r in rows}
        stage_avg_days: dict[str, float] = {
            r.stage: round(float(r.avg_days or 0.0), 2) for r in rows
        }

        total = sum(stage_counts.values())
        lost_count = stage_counts.get("lost", 0)
        non_lost = total - lost_count

        items: list[StageAnalysisItem] = []
        for stage in _STAGE_ORDER:
            count = stage_counts.get(stage, 0)
            # conversion_rate: % of all non-lost leads at this stage or beyond
            stage_idx = _STAGE_ORDER.index(stage)
            at_or_beyond = sum(
                stage_counts.get(s, 0) for s in _STAGE_ORDER[stage_idx:]
            )
            conversion_rate = round(at_or_beyond / non_lost * 100, 1) if non_lost > 0 else 0.0
            # drop_off_rate: of leads that reached this stage, % that didn't advance
            next_stages = sum(
                stage_counts.get(s, 0) for s in _STAGE_ORDER[stage_idx + 1:]
            )
            at_or_beyond_count = count + next_stages
            drop_off_rate = (
                round(count / at_or_beyond_count * 100, 1)
                if at_or_beyond_count > 0
                else 0.0
            )
            items.append(
                StageAnalysisItem(
                    stage=stage,
                    count=count,
                    average_days=stage_avg_days.get(stage, 0.0),
                    conversion_rate=conversion_rate,
                    drop_off_rate=drop_off_rate,
                )
            )
        # Append lost stage
        lost_avg = stage_avg_days.get("lost", 0.0)
        items.append(
            StageAnalysisItem(
                stage="lost",
                count=lost_count,
                average_days=lost_avg,
                conversion_rate=0.0,
                drop_off_rate=100.0 if lost_count > 0 else 0.0,
            )
        )

        result = StageAnalysisOut(items=items)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_PIPELINE_TTL)
        except Exception:
            pass
        return result

    async def get_source_analysis(self, workspace_id: uuid.UUID) -> SourceAnalysisOut:
        from corpmind.core.redis import get_redis

        ctx = get_tenant_context()
        key = _pipeline_sources_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return SourceAnalysisOut.model_validate_json(cached)
        except Exception:
            pass

        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        COALESCE(hc.source, 'unknown') AS source,
                        COUNT(l.id) AS lead_count,
                        SUM(CASE WHEN l.stage IN ('meeting_completed', 'booked') THEN 1 ELSE 0 END) AS qualified,
                        SUM(CASE WHEN l.stage = 'booked' THEN 1 ELSE 0 END) AS won
                    FROM leads l
                    LEFT JOIN hr_contacts hc
                        ON l.contact_id = hc.id AND hc.tenant_id = l.tenant_id
                    WHERE l.tenant_id = :tenant_id
                      AND l.workspace_id = :workspace_id
                    GROUP BY COALESCE(hc.source, 'unknown')
                    ORDER BY COUNT(l.id) DESC
                    """
                ),
                {"tenant_id": ctx.org_id, "workspace_id": workspace_id},
            )
        ).fetchall()

        items = []
        for row in rows:
            lead_count = int(row.lead_count)
            won = int(row.won)
            conversion_rate = round(won / lead_count * 100, 2) if lead_count > 0 else 0.0
            items.append(
                SourceAnalysisItem(
                    source=row.source,
                    lead_count=lead_count,
                    qualified=int(row.qualified),
                    won=won,
                    conversion_rate=conversion_rate,
                )
            )

        result = SourceAnalysisOut(items=items)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_PIPELINE_TTL)
        except Exception:
            pass
        return result

    async def get_industry_analysis(self, workspace_id: uuid.UUID) -> IndustryAnalysisOut:
        from corpmind.core.redis import get_redis

        ctx = get_tenant_context()
        key = _pipeline_industries_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return IndustryAnalysisOut.model_validate_json(cached)
        except Exception:
            pass

        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        COALESCE(c.industry, 'unknown') AS industry,
                        COUNT(l.id) AS lead_count,
                        SUM(CASE WHEN l.stage = 'booked' THEN 1 ELSE 0 END) AS won,
                        AVG(
                            EXTRACT(EPOCH FROM (
                                COALESCE(l.booked_at, NOW()) - l.created_at
                            )) / 86400.0
                        ) AS avg_pipeline_days
                    FROM leads l
                    LEFT JOIN hr_contacts hc
                        ON l.contact_id = hc.id AND hc.tenant_id = l.tenant_id
                    LEFT JOIN companies c
                        ON hc.company_id = c.id AND c.tenant_id = l.tenant_id
                    WHERE l.tenant_id = :tenant_id
                      AND l.workspace_id = :workspace_id
                    GROUP BY COALESCE(c.industry, 'unknown')
                    ORDER BY COUNT(l.id) DESC
                    """
                ),
                {"tenant_id": ctx.org_id, "workspace_id": workspace_id},
            )
        ).fetchall()

        items = []
        for row in rows:
            lead_count = int(row.lead_count)
            won = int(row.won)
            conversion_rate = round(won / lead_count * 100, 2) if lead_count > 0 else 0.0
            items.append(
                IndustryAnalysisItem(
                    industry=row.industry,
                    lead_count=lead_count,
                    won=won,
                    conversion_rate=conversion_rate,
                    average_pipeline_days=round(float(row.avg_pipeline_days or 0.0), 2),
                )
            )

        result = IndustryAnalysisOut(items=items)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_PIPELINE_TTL)
        except Exception:
            pass
        return result

    async def get_conversion(self, workspace_id: uuid.UUID) -> LeadConversionOut:
        from corpmind.core.redis import get_redis

        ctx = get_tenant_context()
        key = _pipeline_conversion_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return LeadConversionOut.model_validate_json(cached)
        except Exception:
            pass

        # Stage counts and booked_at durations in one pass
        stage_row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        SUM(CASE WHEN stage IN ('meeting_completed', 'booked') THEN 1 ELSE 0 END) AS qualified_count,
                        SUM(CASE WHEN stage = 'booked' THEN 1 ELSE 0 END) AS won_count,
                        COUNT(*) AS total_count,
                        AVG(
                            CASE WHEN stage = 'booked' AND booked_at IS NOT NULL
                                 THEN EXTRACT(EPOCH FROM (booked_at - created_at)) / 86400.0
                            END
                        ) AS avg_days_to_win
                    FROM leads
                    WHERE tenant_id = :tenant_id
                      AND workspace_id = :workspace_id
                    """
                ),
                {"tenant_id": ctx.org_id, "workspace_id": workspace_id},
            )
        ).fetchone()

        # Proposal counts for conversion funnel
        proposal_row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        COUNT(DISTINCT l.id) AS proposal_leads,
                        SUM(CASE WHEN l.stage = 'booked' THEN 1 ELSE 0 END) AS won_with_proposal
                    FROM leads l
                    JOIN proposals p ON p.lead_id = l.id AND p.tenant_id = l.tenant_id
                    WHERE l.tenant_id = :tenant_id
                      AND l.workspace_id = :workspace_id
                    """
                ),
                {"tenant_id": ctx.org_id, "workspace_id": workspace_id},
            )
        ).fetchone()

        qualified_count = int(stage_row.qualified_count or 0) if stage_row else 0
        won_count = int(stage_row.won_count or 0) if stage_row else 0
        total_count = int(stage_row.total_count or 0) if stage_row else 0
        avg_days_to_win = round(float(stage_row.avg_days_to_win or 0.0), 2) if stage_row else 0.0

        proposal_leads = int(proposal_row.proposal_leads or 0) if proposal_row else 0
        won_with_proposal = int(proposal_row.won_with_proposal or 0) if proposal_row else 0

        qualified_to_proposal = (
            round(proposal_leads / qualified_count * 100, 2) if qualified_count > 0 else 0.0
        )
        proposal_to_win = (
            round(won_with_proposal / proposal_leads * 100, 2) if proposal_leads > 0 else 0.0
        )
        overall_win_rate = round(won_count / total_count * 100, 2) if total_count > 0 else 0.0

        result = LeadConversionOut(
            qualified_to_proposal=qualified_to_proposal,
            proposal_to_win=proposal_to_win,
            overall_win_rate=overall_win_rate,
            average_days_to_win=avg_days_to_win,
        )
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_PIPELINE_TTL)
        except Exception:
            pass
        return result
