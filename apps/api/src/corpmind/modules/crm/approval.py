"""FollowUpApprovalService — Sprint 8C HITL surface for awaiting_approval follow-ups.

A follow-up parked by the Sprint 8B cadence (every question follow-up, plus any
out-of-office follow-up during training-wheels / with auto_send off) lands in
status='awaiting_approval' with result_outbound_message_id pointing at a draft
OutboundMessage.  This service lets a human review and act on it:

  • get_review  — assemble reply ↔ draft + lead context in one round trip.
  • edit_draft  — refine the AI-drafted answer (only while awaiting_approval).
  • approve     — send the draft through the FULL compliance gate (ComplianceGuard
                  runs inside OutreachService.send_message) → task 'done'.
  • reject      — cancel the task; the draft is retained but never sent.

Question auto-send stays OFF (ADR-0008): there is no path here that sends without
an explicit human approve.  approve dispatches via OutreachService — a cross-module
service call (DI), never a repo/model import.  Audit rows are written through
ComplianceService.record_audit_event (the audit owner), again respecting the
module boundary.  CRM activity rows are written in this module (own table).
"""

from __future__ import annotations

import hashlib
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import ConflictError, NotFoundError
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.compliance.service import ComplianceService
from corpmind.modules.crm.models import Activity
from corpmind.modules.crm.repo import ActivityRepo, FollowUpTaskRepo
from corpmind.modules.crm.schemas import (
    FollowupApproveResponse,
    FollowupDraftView,
    FollowupReplyView,
    FollowupReviewOut,
    FollowUpTaskOut,
)
from corpmind.modules.inbox.service import InboxService
from corpmind.modules.outreach.service import OutreachService

log = structlog.get_logger(__name__)

_APPROVABLE = "awaiting_approval"

# Activity vocabulary for HITL actions (mirrors crm/automation.py constants).
ACTIVITY_FOLLOWUP_APPROVED = "followup_approved"
ACTIVITY_FOLLOWUP_REJECTED = "followup_rejected"
ACTIVITY_FOLLOWUP_BLOCKED = "automation_failed"


class FollowUpApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = FollowUpTaskRepo(session)
        self._activity = ActivityRepo(session)
        self._outreach = OutreachService(session)
        self._inbox = InboxService(session)
        self._compliance = ComplianceService(session)

    # ── Review payload ─────────────────────────────────────────────────────────

    async def get_review(self, task_id: uuid.UUID) -> FollowupReviewOut:
        """Assemble reply + draft + original subject + lead stage in one call."""
        task = await self._require_task(task_id)

        draft: FollowupDraftView | None = None
        if task.result_outbound_message_id is not None:
            try:
                d = await self._outreach.get_message(task.result_outbound_message_id)
                draft = FollowupDraftView(
                    id=d.id, subject=d.subject, body=d.body, status=d.status
                )
            except NotFoundError:
                draft = None

        reply: FollowupReplyView | None = None
        try:
            im = await self._inbox.get_message(task.source_inbox_message_id)
            reply = FollowupReplyView(
                from_address=im.from_address,
                subject=im.subject,
                snippet=im.body_snippet,
                received_at=im.received_at,
            )
        except NotFoundError:
            reply = None

        original_subject = await self._original_subject(task.source_outbound_message_id)
        lead_stage = await self._lead_stage(task.lead_id)

        return FollowupReviewOut(
            task=FollowUpTaskOut.model_validate(task),
            draft=draft,
            reply=reply,
            original_subject=original_subject,
            lead_stage=lead_stage,
        )

    # ── Edit ─────────────────────────────────────────────────────────────────

    async def edit_draft(
        self, task_id: uuid.UUID, *, subject: str | None, body: str
    ) -> FollowupDraftView:
        """Edit the draft body/subject before approval.

        Guarded twice: the task must be awaiting_approval AND the draft must still
        be in 'draft' status (OutreachService.update_draft_content enforces the latter).
        """
        task = await self._require_task(task_id)
        if task.result_outbound_message_id is None:
            raise ConflictError("Follow-up has no draft to edit.")

        draft = await self._outreach.update_draft_content(
            task.result_outbound_message_id, subject=subject, body=body
        )  # validates draft status + commits

        await self._compliance.record_audit_event(
            event_type="followup.edited",
            outcome="allowed",
            content_hash=hashlib.sha256(body.encode()).hexdigest(),
            event_data={
                "task_id": str(task_id),
                "message_id": str(task.result_outbound_message_id),
            },
        )
        await self._session.commit()
        log.info("crm.followup.edited", task_id=str(task_id))
        return FollowupDraftView(
            id=draft.id, subject=draft.subject, body=draft.body, status=draft.status
        )

    # ── Approve (the only send path — full compliance gate) ──────────────────────

    async def approve(self, task_id: uuid.UUID) -> FollowupApproveResponse:
        """Send the draft via OutreachService (ComplianceGuard runs there).

        On a compliance block at send time the task is cancelled with the reason
        and the block is surfaced to the caller — nothing is sent.
        """
        task = await self._require_task(task_id)
        if task.result_outbound_message_id is None:
            raise ConflictError("Follow-up has no draft to approve.")

        # Capture identifiers before any commit so later audit/activity writes are
        # not exposed to stale-attribute access after bulk UPDATEs.
        draft_id = task.result_outbound_message_id
        original_outbound_id = task.source_outbound_message_id

        anchor = await self._threading_anchor(original_outbound_id)

        resp = await self._outreach.send_message(draft_id, in_reply_to=anchor)

        if resp.status == "blocked":
            await self._repo.mark_cancelled(
                task_id, reason=f"compliance:{resp.compliance_reason or 'blocked'}"
            )
            await self._compliance.record_audit_event(
                event_type="followup.blocked_on_approve",
                outcome="blocked",
                reason=resp.compliance_reason,
                event_data={"task_id": str(task_id), "message_id": str(draft_id)},
            )
            await self._write_activity(
                task,
                ACTIVITY_FOLLOWUP_BLOCKED,
                f"Approval blocked by compliance: {resp.compliance_reason}.",
            )
            await self._session.commit()
            log.warning(
                "crm.followup.blocked_on_approve",
                task_id=str(task_id),
                reason=resp.compliance_reason,
            )
            return FollowupApproveResponse(
                task_id=task_id, status="blocked", compliance_reason=resp.compliance_reason
            )

        await self._repo.mark_done(task_id, result_outbound_message_id=draft_id)
        await self._compliance.record_audit_event(
            event_type="followup.approved",
            outcome="allowed",
            event_data={"task_id": str(task_id), "message_id": str(draft_id)},
        )
        await self._write_activity(
            task, ACTIVITY_FOLLOWUP_APPROVED, "Follow-up approved and sent."
        )
        await self._session.commit()
        log.info("crm.followup.approved", task_id=str(task_id), message_id=str(draft_id))
        return FollowupApproveResponse(task_id=task_id, status="done")

    # ── Reject ─────────────────────────────────────────────────────────────────

    async def reject(self, task_id: uuid.UUID, *, reason: str | None = None) -> FollowUpTaskOut:
        """Cancel a parked follow-up; the draft is retained but never sent."""
        task = await self._require_task(task_id)
        await self._repo.mark_cancelled(task_id, reason=f"rejected: {reason or 'no reason given'}")
        await self._compliance.record_audit_event(
            event_type="followup.rejected",
            outcome="allowed",
            reason=reason,
            event_data={
                "task_id": str(task_id),
                "message_id": str(task.result_outbound_message_id)
                if task.result_outbound_message_id
                else None,
            },
        )
        await self._write_activity(
            task, ACTIVITY_FOLLOWUP_REJECTED, "Follow-up rejected by reviewer."
        )
        await self._session.commit()
        log.info("crm.followup.rejected", task_id=str(task_id))

        refreshed = await self._repo.find_by_id(task_id)
        assert refreshed is not None  # just updated it
        return FollowUpTaskOut.model_validate(refreshed)

    # ── Helpers ─────────────────────────────────────────────────────────────────

    async def _require_task(self, task_id: uuid.UUID):
        task = await self._repo.find_by_id(task_id)
        if task is None:
            raise NotFoundError(f"Follow-up task {task_id} not found")
        if task.status != _APPROVABLE:
            raise ConflictError(
                f"Follow-up is in status '{task.status}', not '{_APPROVABLE}'."
            )
        return task

    async def _threading_anchor(self, outbound_id: uuid.UUID | None) -> str | None:
        if outbound_id is None:
            return None
        try:
            original = await self._outreach.get_message(outbound_id)
        except NotFoundError:
            return None
        return original.smtp_message_id

    async def _original_subject(self, outbound_id: uuid.UUID | None) -> str | None:
        if outbound_id is None:
            return None
        try:
            original = await self._outreach.get_message(outbound_id)
        except NotFoundError:
            return None
        return original.subject

    async def _lead_stage(self, lead_id: uuid.UUID | None) -> str | None:
        if lead_id is None:
            return None
        ctx = get_tenant_context()
        result = await self._session.execute(
            text("SELECT stage FROM leads WHERE id = :lid AND tenant_id = :tid"),
            {"lid": str(lead_id), "tid": str(ctx.org_id)},
        )
        row = result.one_or_none()
        return row[0] if row else None

    async def _write_activity(self, task, activity_type: str, summary: str) -> None:
        ctx = get_tenant_context()
        await self._activity.create(
            Activity(
                tenant_id=ctx.org_id,
                workspace_id=task.workspace_id,
                lead_id=task.lead_id,
                contact_id=task.contact_id,
                type=activity_type,
                summary=summary,
                source_inbox_message_id=task.source_inbox_message_id,
                source_outbound_message_id=task.result_outbound_message_id,
            )
        )
