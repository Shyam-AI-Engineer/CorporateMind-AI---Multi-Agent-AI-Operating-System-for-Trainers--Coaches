"""ReplyAutomationService — consumes ReplyClassified, drives CRM updates.

This service is the single in-process consumer of the inbox.ReplyClassified
event.  It is invoked directly by the inbox sync worker after a message is
classified (Sprint 4B).  There is no event bus yet — same convention as every
other module.

Pipeline
────────
  1. Idempotency gate: AutomationLogRepo.reserve(inbox_message_id, intent, outcome)
       on conflict → return "already_applied" with no further work.
  2. Validation gates (in order, fail-fast):
       outbound_message_id is not None     → no_outbound_match
       outbound → contact resolvable        → contact_not_found
       contact exists in this tenant        → contact_not_found
       contact has an active Lead           → lead_not_found (warn-only for bounce)
  3. Intent dispatch:
       interested      → CRMService.advance_stage if stage='discovered'
                         else log "already_engaged_or_later"
       not_interested  → CRMService.mark_lost (skip if already terminal)
       question        → FollowUpTask(scheduled_for=None)
       out_of_office   → FollowUpTask(scheduled_for=now+3d)
       bounce          → HRContact.email_deliverable=False
       auto_reply      → activity only
       unknown         → activity only
  4. Activity log row written for every outcome (including no-op skips).
  5. Domain event emitted via structlog (no event bus yet).

All four steps run in the same DB transaction the worker holds; one final
commit at the end keeps the row, the activity, and the idempotency log
atomic.  Any exception inside this service is caught by the worker and logged
as automation_failed(reason="internal_error") — message persistence is not
affected.

Cross-module rule: this service is in the CRM module and may not import the
outreach or hr_discovery repos / models.  outbound_message_id → contact_id
and HRContact updates are done via raw SQL — same pattern as
inbox.service.match_reply.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import ConflictError
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.crm.events import (
    AutomationFailed,
    ContactBounced,
    FollowUpRequired,
    FollowUpScheduled,
    LeadCold,
    LeadEngaged,
)
from corpmind.modules.crm.models import Activity, FollowUpTask
from corpmind.modules.crm.repo import (
    ActivityRepo,
    AutomationLogRepo,
    FollowUpTaskRepo,
    LeadRepo,
)
from corpmind.modules.crm.service import CRMService

log = structlog.get_logger(__name__)


# Hours to wait before following up on an out-of-office reply.
# Future Sprint 4D may parse the actual return date from the body and override
# this; the conservative default is 72h so we don't fire before the OoO ends.
_OOO_FOLLOWUP_HOURS = 72

# Activity type vocabulary — kept here as the single source of truth for
# the strings written to crm_activities.type.
ACTIVITY_LEAD_ENGAGED = "lead_engaged"
ACTIVITY_LEAD_COLD = "lead_cold"
ACTIVITY_FOLLOWUP_REQUIRED = "followup_required"
ACTIVITY_FOLLOWUP_SCHEDULED = "followup_scheduled"
ACTIVITY_CONTACT_BOUNCED = "contact_bounced"
ACTIVITY_AUTO_REPLY = "auto_reply_logged"
ACTIVITY_UNKNOWN = "unknown_intent_logged"
ACTIVITY_AUTOMATION_FAILED = "automation_failed"
ACTIVITY_AUTOMATION_SKIPPED = "automation_skipped"


@dataclass(frozen=True)
class AutomationResult:
    """Returned to the worker for logging / metrics.

    `outcome`:
      applied         — CRM mutation succeeded (or activity-only for auto/unknown).
      already_applied — Idempotency gate fired; no work done.
      failed          — Validation gate fired; AutomationFailed event emitted.
    """

    outcome: str
    reason: str | None = None
    activity_id: uuid.UUID | None = None


class ReplyAutomationService:
    """Consume a classified reply and drive the corresponding CRM updates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._log_repo = AutomationLogRepo(session)
        self._activity_repo = ActivityRepo(session)
        self._followup_repo = FollowUpTaskRepo(session)
        self._lead_repo = LeadRepo(session)
        self._crm = CRMService(session)

    # ── Entry point ───────────────────────────────────────────────────────────

    async def handle_classified(
        self,
        *,
        inbox_message_id: uuid.UUID,
        tenant_id: uuid.UUID,
        intent: str,
        outbound_message_id: uuid.UUID | None,
    ) -> AutomationResult:
        """Process one ReplyClassified event.

        The caller is responsible for setting TenantContext and the RLS GUC
        before invoking — the service inherits both via get_tenant_context()
        and the existing session.  `tenant_id` parameter is used to assert
        the context matches (defense-in-depth).
        """
        ctx = get_tenant_context()
        if ctx.org_id != tenant_id:
            # Caller bug: TenantContext doesn't match the event payload.
            # Emit failure and return — never touch CRM under a wrong identity.
            return await self._fail(
                inbox_message_id=inbox_message_id,
                intent=intent,
                reason="tenant_mismatch",
                lead_id=None,
                contact_id=None,
                workspace_id=None,
                outbound_message_id=outbound_message_id,
            )

        # ── 1. Idempotency gate ─────────────────────────────────────────────
        # Reserve OPTIMISTICALLY with outcome="applied"; if anything fails
        # downstream the row stays as "applied" (we don't re-process), which
        # is correct: a partial failure is still a "do not retry" signal.
        reserved = await self._log_repo.reserve(
            inbox_message_id=inbox_message_id,
            intent=intent,
            outcome="applied",
        )
        if not reserved:
            log.info(
                "crm.automation.skipped",
                reason="already_applied",
                inbox_message_id=str(inbox_message_id),
                tenant_id=str(tenant_id),
            )
            return AutomationResult(outcome="already_applied")

        # ── 2. Validation gates ─────────────────────────────────────────────
        if outbound_message_id is None:
            return await self._fail(
                inbox_message_id=inbox_message_id,
                intent=intent,
                reason="no_outbound_match",
                lead_id=None,
                contact_id=None,
                workspace_id=None,
                outbound_message_id=None,
            )

        outbound = await self._resolve_outbound(outbound_message_id)
        if outbound is None:
            return await self._fail(
                inbox_message_id=inbox_message_id,
                intent=intent,
                reason="contact_not_found",
                lead_id=None,
                contact_id=None,
                workspace_id=None,
                outbound_message_id=outbound_message_id,
            )
        contact_id, resolved_workspace_id = outbound

        # The lead lookup is tenant-wide because the outbound→workspace mapping
        # is unreliable for ad-hoc sends (no campaign).  RLS still enforces the
        # tenant boundary; we just allow any workspace within this tenant.
        lead = await self._lead_repo.find_active_by_contact_any_workspace(contact_id)

        # Prefer the lead's workspace_id over the outbound fallback — it is the
        # source of truth for where the activity / follow-up should live.
        workspace_id = lead.workspace_id if lead is not None else resolved_workspace_id

        # `bounce` bypasses the lead-required gate — we still want to flag
        # the contact as unreachable even if no live lead exists.
        if intent == "bounce":
            return await self._handle_bounce(
                inbox_message_id=inbox_message_id,
                contact_id=contact_id,
                workspace_id=workspace_id,
                outbound_message_id=outbound_message_id,
                lead=lead,
            )

        # Intents that REQUIRE a live lead
        if intent in {"interested", "not_interested"} and lead is None:
            return await self._fail(
                inbox_message_id=inbox_message_id,
                intent=intent,
                reason="lead_not_found",
                lead_id=None,
                contact_id=contact_id,
                workspace_id=workspace_id,
                outbound_message_id=outbound_message_id,
            )

        # ── 3. Intent dispatch ──────────────────────────────────────────────
        if intent == "interested":
            assert lead is not None  # narrowed by guard above
            return await self._handle_interested(
                inbox_message_id=inbox_message_id,
                lead=lead,
                contact_id=contact_id,
                workspace_id=workspace_id,
                outbound_message_id=outbound_message_id,
            )

        if intent == "not_interested":
            assert lead is not None
            return await self._handle_not_interested(
                inbox_message_id=inbox_message_id,
                lead=lead,
                contact_id=contact_id,
                workspace_id=workspace_id,
                outbound_message_id=outbound_message_id,
            )

        if intent == "question":
            return await self._handle_question(
                inbox_message_id=inbox_message_id,
                lead=lead,
                contact_id=contact_id,
                workspace_id=workspace_id,
                outbound_message_id=outbound_message_id,
            )

        if intent == "out_of_office":
            return await self._handle_out_of_office(
                inbox_message_id=inbox_message_id,
                lead=lead,
                contact_id=contact_id,
                workspace_id=workspace_id,
                outbound_message_id=outbound_message_id,
            )

        if intent == "auto_reply":
            return await self._handle_activity_only(
                inbox_message_id=inbox_message_id,
                lead=lead,
                contact_id=contact_id,
                workspace_id=workspace_id,
                outbound_message_id=outbound_message_id,
                activity_type=ACTIVITY_AUTO_REPLY,
                summary="Auto-reply received; no CRM action taken.",
            )

        if intent == "unknown":
            return await self._handle_activity_only(
                inbox_message_id=inbox_message_id,
                lead=lead,
                contact_id=contact_id,
                workspace_id=workspace_id,
                outbound_message_id=outbound_message_id,
                activity_type=ACTIVITY_UNKNOWN,
                summary="Reply classified as unknown intent; no CRM action.",
            )

        # Unknown intent label — should never happen since the agent allowlist
        # is enforced upstream, but defensively coerce to unknown-style log.
        return await self._fail(
            inbox_message_id=inbox_message_id,
            intent=intent,
            reason="internal_error",
            lead_id=None,
            contact_id=contact_id,
            workspace_id=workspace_id,
            outbound_message_id=outbound_message_id,
        )

    # ── Per-intent handlers ───────────────────────────────────────────────────

    async def _handle_interested(
        self,
        *,
        inbox_message_id: uuid.UUID,
        lead,  # Lead — typed loosely to avoid an import cycle in narrow scope
        contact_id: uuid.UUID,
        workspace_id: uuid.UUID,
        outbound_message_id: uuid.UUID | None,
    ) -> AutomationResult:
        """Advance lead `discovered → engaged`; no-op if already past discovered."""
        transition = "advanced"
        summary = "Interested reply — advanced lead from discovered → engaged."

        if lead.stage == "discovered":
            try:
                await self._crm.advance_stage(lead.id)
            except ConflictError as exc:
                # Race window — another worker advanced between find and update.
                log.warning(
                    "crm.automation.advance_conflict",
                    lead_id=str(lead.id),
                    error=str(exc),
                )
                transition = "already_engaged_or_later"
                summary = (
                    "Interested reply — lead already past discovered; logged as no-op."
                )
        else:
            # discovered is the only stage where we auto-advance.  Anything past
            # that is treated as a no-op so we don't accidentally skip stages.
            transition = "already_engaged_or_later"
            summary = (
                f"Interested reply — lead already in '{lead.stage}'; logged as no-op."
            )

        activity = await self._write_activity(
            type=ACTIVITY_LEAD_ENGAGED,
            summary=summary,
            lead_id=lead.id,
            contact_id=contact_id,
            workspace_id=workspace_id,
            inbox_message_id=inbox_message_id,
            outbound_message_id=outbound_message_id,
        )
        await self._session.commit()

        _emit(
            LeadEngaged(
                lead_id=lead.id,
                tenant_id=lead.tenant_id,
                contact_id=contact_id,
                source_inbox_message_id=inbox_message_id,
                transition=transition,
            )
        )
        return AutomationResult(outcome="applied", activity_id=activity.id)

    async def _handle_not_interested(
        self,
        *,
        inbox_message_id: uuid.UUID,
        lead,
        contact_id: uuid.UUID,
        workspace_id: uuid.UUID,
        outbound_message_id: uuid.UUID | None,
    ) -> AutomationResult:
        """Mark lead lost; no-op if already terminal."""
        summary = "Not-interested reply — marked lead lost (cold)."

        if lead.stage in {"booked", "lost"}:
            summary = (
                f"Not-interested reply — lead already terminal '{lead.stage}'; "
                "logged as no-op."
            )
        else:
            try:
                await self._crm.mark_lost(lead.id)
            except ConflictError as exc:
                log.warning(
                    "crm.automation.mark_lost_conflict",
                    lead_id=str(lead.id),
                    error=str(exc),
                )
                summary = (
                    "Not-interested reply — lead concurrently terminal; logged as no-op."
                )

        activity = await self._write_activity(
            type=ACTIVITY_LEAD_COLD,
            summary=summary,
            lead_id=lead.id,
            contact_id=contact_id,
            workspace_id=workspace_id,
            inbox_message_id=inbox_message_id,
            outbound_message_id=outbound_message_id,
        )
        await self._session.commit()

        _emit(
            LeadCold(
                lead_id=lead.id,
                tenant_id=lead.tenant_id,
                contact_id=contact_id,
                source_inbox_message_id=inbox_message_id,
            )
        )
        return AutomationResult(outcome="applied", activity_id=activity.id)

    async def _handle_question(
        self,
        *,
        inbox_message_id: uuid.UUID,
        lead,
        contact_id: uuid.UUID,
        workspace_id: uuid.UUID,
        outbound_message_id: uuid.UUID | None,
    ) -> AutomationResult:
        """Persist a FollowUpTask with no scheduled time (do-asap)."""
        ctx = get_tenant_context()
        task = FollowUpTask(
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            lead_id=lead.id if lead else None,
            contact_id=contact_id,
            type="question_followup",
            status="pending",
            scheduled_for=None,
            source_inbox_message_id=inbox_message_id,
            source_outbound_message_id=outbound_message_id,
            notes="Question from reply — answer requested.",
        )
        await self._followup_repo.create(task)

        activity = await self._write_activity(
            type=ACTIVITY_FOLLOWUP_REQUIRED,
            summary="Question reply — follow-up task queued.",
            lead_id=lead.id if lead else None,
            contact_id=contact_id,
            workspace_id=workspace_id,
            inbox_message_id=inbox_message_id,
            outbound_message_id=outbound_message_id,
        )
        await self._session.commit()

        _emit(
            FollowUpRequired(
                follow_up_task_id=task.id,
                tenant_id=ctx.org_id,
                contact_id=contact_id,
                lead_id=lead.id if lead else None,
                source_inbox_message_id=inbox_message_id,
            )
        )
        return AutomationResult(outcome="applied", activity_id=activity.id)

    async def _handle_out_of_office(
        self,
        *,
        inbox_message_id: uuid.UUID,
        lead,
        contact_id: uuid.UUID,
        workspace_id: uuid.UUID,
        outbound_message_id: uuid.UUID | None,
    ) -> AutomationResult:
        """Persist a FollowUpTask scheduled for now + _OOO_FOLLOWUP_HOURS."""
        ctx = get_tenant_context()
        scheduled_for = datetime.now(UTC) + timedelta(hours=_OOO_FOLLOWUP_HOURS)
        task = FollowUpTask(
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            lead_id=lead.id if lead else None,
            contact_id=contact_id,
            type="out_of_office_followup",
            status="pending",
            scheduled_for=scheduled_for,
            source_inbox_message_id=inbox_message_id,
            source_outbound_message_id=outbound_message_id,
            notes="Out-of-office reply — follow up after return.",
        )
        await self._followup_repo.create(task)

        activity = await self._write_activity(
            type=ACTIVITY_FOLLOWUP_SCHEDULED,
            summary=(
                "Out-of-office reply — follow-up scheduled for "
                f"{scheduled_for.isoformat()}."
            ),
            lead_id=lead.id if lead else None,
            contact_id=contact_id,
            workspace_id=workspace_id,
            inbox_message_id=inbox_message_id,
            outbound_message_id=outbound_message_id,
        )
        await self._session.commit()

        _emit(
            FollowUpScheduled(
                follow_up_task_id=task.id,
                tenant_id=ctx.org_id,
                contact_id=contact_id,
                lead_id=lead.id if lead else None,
                scheduled_for=scheduled_for,
                source_inbox_message_id=inbox_message_id,
            )
        )
        return AutomationResult(outcome="applied", activity_id=activity.id)

    async def _handle_bounce(
        self,
        *,
        inbox_message_id: uuid.UUID,
        contact_id: uuid.UUID,
        workspace_id: uuid.UUID,
        outbound_message_id: uuid.UUID | None,
        lead=None,
    ) -> AutomationResult:
        """Flip HRContact.email_deliverable=False; log activity even if contact
        has no active lead.

        Uses raw SQL to update hr_contacts because cross-module ORM imports
        are forbidden (CLAUDE.md backend-python rule).  The update is
        tenant-scoped via the WHERE clause AND via RLS.

        `lead` is passed in by the caller (resolved tenant-wide); it may be
        None — bounce processing does not require an active lead.
        """
        ctx = get_tenant_context()
        await self._session.execute(
            text(
                "UPDATE hr_contacts SET email_deliverable = false"
                " WHERE id = :cid AND tenant_id = :tid"
            ),
            {"cid": str(contact_id), "tid": str(ctx.org_id)},
        )

        activity = await self._write_activity(
            type=ACTIVITY_CONTACT_BOUNCED,
            summary="Bounce reply — contact marked email_deliverable=False.",
            lead_id=lead.id if lead else None,
            contact_id=contact_id,
            workspace_id=workspace_id,
            inbox_message_id=inbox_message_id,
            outbound_message_id=outbound_message_id,
        )
        await self._session.commit()

        _emit(
            ContactBounced(
                contact_id=contact_id,
                tenant_id=ctx.org_id,
                source_inbox_message_id=inbox_message_id,
            )
        )
        return AutomationResult(outcome="applied", activity_id=activity.id)

    async def _handle_activity_only(
        self,
        *,
        inbox_message_id: uuid.UUID,
        lead,
        contact_id: uuid.UUID,
        workspace_id: uuid.UUID,
        outbound_message_id: uuid.UUID | None,
        activity_type: str,
        summary: str,
    ) -> AutomationResult:
        """auto_reply + unknown share this shape: log only, no CRM mutation."""
        activity = await self._write_activity(
            type=activity_type,
            summary=summary,
            lead_id=lead.id if lead else None,
            contact_id=contact_id,
            workspace_id=workspace_id,
            inbox_message_id=inbox_message_id,
            outbound_message_id=outbound_message_id,
        )
        await self._session.commit()
        return AutomationResult(outcome="applied", activity_id=activity.id)

    # ── Cross-module data access (raw SQL — boundary rule) ────────────────────

    async def _resolve_outbound(
        self, outbound_message_id: uuid.UUID
    ) -> tuple[uuid.UUID, uuid.UUID] | None:
        """Return (contact_id, workspace_id) for an outbound row in this tenant.

        Raw SQL — outbound_messages lives in the outreach module and we are
        forbidden from importing its ORM model or repo.  workspace_id is
        derived via campaigns since outbound_messages does not carry it
        directly; campaign_id may be NULL for ad-hoc sends, in which case
        we fall back to the tenant's default workspace.

        Returns None when the outbound row is not visible (different tenant,
        deleted, or the contact_id null).
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            text(
                "SELECT om.contact_id, COALESCE(c.workspace_id, om.tenant_id) AS workspace_id"
                " FROM outbound_messages om"
                " LEFT JOIN campaigns c ON c.id = om.campaign_id"
                " WHERE om.id = :oid AND om.tenant_id = :tid"
                " LIMIT 1"
            ),
            {"oid": str(outbound_message_id), "tid": str(ctx.org_id)},
        )
        row = result.one_or_none()
        if row is None:
            return None
        return uuid.UUID(str(row[0])), uuid.UUID(str(row[1]))

    # ── Activity helper ───────────────────────────────────────────────────────

    async def _write_activity(
        self,
        *,
        type: str,
        summary: str,
        lead_id: uuid.UUID | None,
        contact_id: uuid.UUID,
        workspace_id: uuid.UUID,
        inbox_message_id: uuid.UUID,
        outbound_message_id: uuid.UUID | None,
    ) -> Activity:
        ctx = get_tenant_context()
        activity = Activity(
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            lead_id=lead_id,
            contact_id=contact_id,
            type=type,
            summary=summary,
            source_inbox_message_id=inbox_message_id,
            source_outbound_message_id=outbound_message_id,
        )
        await self._activity_repo.create(activity)
        return activity

    # ── Failure path ──────────────────────────────────────────────────────────

    async def _fail(
        self,
        *,
        inbox_message_id: uuid.UUID,
        intent: str,
        reason: str,
        lead_id: uuid.UUID | None,
        contact_id: uuid.UUID | None,
        workspace_id: uuid.UUID | None,
        outbound_message_id: uuid.UUID | None,
    ) -> AutomationResult:
        """Validation gate fired — record a "failed" activity if we know who
        to attribute it to, emit AutomationFailed, and return.

        We DO NOT roll back the automation-log reservation: the reservation
        records "we tried", and the failure reason is captured in the log row
        (intent stays as the original).  This prevents retries from re-running
        the same validation failure cascade.
        """
        ctx = get_tenant_context()
        activity_id: uuid.UUID | None = None
        if contact_id is not None and workspace_id is not None:
            try:
                activity = await self._write_activity(
                    type=ACTIVITY_AUTOMATION_FAILED,
                    summary=f"Automation failed: {reason}.",
                    lead_id=lead_id,
                    contact_id=contact_id,
                    workspace_id=workspace_id,
                    inbox_message_id=inbox_message_id,
                    outbound_message_id=outbound_message_id,
                )
                activity_id = activity.id
            except Exception as exc:
                # An activity write failure must not mask the original gate
                # failure — log and continue.
                log.error(
                    "crm.automation.activity_write_failed",
                    error=str(exc),
                    inbox_message_id=str(inbox_message_id),
                )

        await self._session.commit()

        _emit(
            AutomationFailed(
                inbox_message_id=inbox_message_id,
                tenant_id=ctx.org_id,
                intent=intent,
                reason=reason,
            )
        )
        log.warning(
            "crm.automation.failed",
            reason=reason,
            intent=intent,
            inbox_message_id=str(inbox_message_id),
            tenant_id=str(ctx.org_id),
        )
        return AutomationResult(outcome="failed", reason=reason, activity_id=activity_id)


def _emit(event: object) -> None:
    """Structured-log a domain event.  Same convention as crm.service._log_event."""
    log.info("crm.domain_event", event_type=type(event).__name__, payload=repr(event))
