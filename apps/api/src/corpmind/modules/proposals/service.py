"""Proposals service — AI-generated proposal lifecycle.

Lifecycle
─────────
draft ──approve──► draft (approval_status: pending_approval → approved)
draft ──reject──►  draft (approval_status: pending_approval → rejected)
draft ──deliver──► sent  (requires approval_status = 'approved')
                   Proposal.status = 'sent' signals the trainer committed to delivery.
                   Delivery execution state lives in OutboundMessage.status, surfaced
                   as ProposalOut.delivery_status (a derived field, never stored).

Proposals are generated for leads in 'meeting_completed' or 'booked' stage.
Re-generating creates a new proposal; old ones are preserved.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.ai.euri_client import EuriClient
from corpmind.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from corpmind.core.tenancy import TenantContext, get_tenant_context
from corpmind.modules.compliance.service import ComplianceService
from corpmind.modules.crm.schemas import LeadOut
from corpmind.modules.proposals.events import (
    ProposalAccepted,
    ProposalApproved,
    ProposalDeclined,
    ProposalDeliveryBlocked,
    ProposalDeliveryQueued,
    ProposalGenerated,
    ProposalRejected,
)
from corpmind.modules.proposals.models import Proposal
from corpmind.modules.proposals.repo import ProposalRepo
from corpmind.modules.proposals.schemas import (
    AcceptProposalRequest,
    DeclineProposalRequest,
    GenerateProposalRequest,
    ProposalListOut,
    ProposalOut,
)

log = structlog.get_logger(__name__)

# Lead must have progressed past the meeting before a proposal is meaningful
_ELIGIBLE_STAGES = frozenset({"meeting_completed", "booked"})

# Roles that can approve or reject proposals
_APPROVER_ROLES = frozenset({"OrgAdmin", "org_admin"})


class ProposalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ProposalRepo(session)
        self._compliance = ComplianceService(session)

    # ── Generation ─────────────────────────────────────────────────────────────

    async def generate(self, req: GenerateProposalRequest, lead: LeadOut) -> ProposalOut:
        """Generate an AI proposal document for a CRM lead.

        The lead must be in 'meeting_completed' or 'booked' stage.
        Multiple proposals per lead are allowed (re-generation creates a new record).
        """
        if lead.stage not in _ELIGIBLE_STAGES:
            raise ValidationError(
                f"Cannot generate a proposal for lead in stage '{lead.stage}'. "
                f"Lead must be in {sorted(_ELIGIBLE_STAGES)}."
            )

        ctx = get_tenant_context()

        ai_result = await EuriClient(self._session).chat(
            task="proposal_generation",
            prompt_name="proposals.generate",
            prompt_inputs={
                "contact_id": str(lead.contact_id),
                "lead_stage": lead.stage,
                "lead_score": lead.score,
                "lead_notes": lead.notes or "",
                "meeting_at": (
                    lead.meeting_scheduled_at.isoformat()
                    if lead.meeting_scheduled_at else ""
                ),
            },
            tenant_id=ctx.org_id,
            request_id=ctx.request_id,
            agent="ProposalAgent",
        )

        content = _parse_content(ai_result["content"])
        title = str(content.get("title", f"Proposal for contact {lead.contact_id}"))

        proposal = Proposal(
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            contact_id=lead.contact_id,
            title=title,
            status="draft",
            content=content,
            approval_status="pending_approval",
            # Sprint 18A: attribute the proposal to the lead for revenue tracing
            lead_id=req.lead_id,
            expected_value_inr=req.expected_value_inr,
        )
        await self._repo.create(proposal)

        await self._compliance.record_audit_event(
            event_type="proposal.submitted",
            outcome="allowed",
            event_data={
                "proposal_id": str(proposal.id),
                "contact_id": str(lead.contact_id),
                "workspace_id": str(req.workspace_id),
            },
        )

        await self._session.commit()

        log.info(
            "proposals.generated",
            proposal_id=str(proposal.id),
            contact_id=str(lead.contact_id),
            workspace_id=str(req.workspace_id),
        )
        _log_event(ProposalGenerated(
            proposal_id=proposal.id,
            tenant_id=ctx.org_id,
            contact_id=lead.contact_id,
        ))

        return ProposalOut.model_validate(proposal)

    # ── Read ────────────────────────────────────────────────────────────────────

    async def get_proposal(self, proposal_id: uuid.UUID) -> ProposalOut:
        proposal = await self._require_proposal(proposal_id)
        out = ProposalOut.model_validate(proposal)
        out.delivery_status = await self._fetch_delivery_status(proposal.outbound_message_id)
        return out

    async def list_proposals(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        approval_status: str | None = None,
        contact_id: uuid.UUID | None = None,
    ) -> ProposalListOut:
        proposals, total = await asyncio.gather(
            self._repo.list_by_workspace(
                workspace_id,
                limit=limit,
                offset=offset,
                approval_status=approval_status,
                contact_id=contact_id,
            ),
            self._repo.count_by_workspace(
                workspace_id,
                approval_status=approval_status,
                contact_id=contact_id,
            ),
        )
        items: list[ProposalOut] = []
        for p in proposals:
            out = ProposalOut.model_validate(p)
            out.delivery_status = await self._fetch_delivery_status(p.outbound_message_id)
            items.append(out)
        return ProposalListOut(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    # ── Approval ────────────────────────────────────────────────────────────────

    async def approve(self, proposal_id: uuid.UUID) -> ProposalOut:
        """Transition proposal approval_status: pending_approval → approved.

        Requires OrgAdmin role. Uses SELECT FOR UPDATE to prevent concurrent
        double-approval races.
        """
        ctx = get_tenant_context()
        _require_approver_role(ctx)

        proposal = await self._require_proposal_for_update(proposal_id)
        if proposal.approval_status != "pending_approval":
            raise ConflictError(
                f"Proposal {proposal_id} cannot be approved "
                f"(current approval_status: '{proposal.approval_status}')."
            )

        now = datetime.now(UTC)
        await self._repo.update_fields(
            proposal_id,
            approval_status="approved",
            approved_by=ctx.user_id,
            approved_at=now,
        )

        await self._compliance.record_audit_event(
            event_type="proposal.approved",
            outcome="allowed",
            event_data={
                "proposal_id": str(proposal_id),
                "approved_by": str(ctx.user_id),
            },
        )

        await self._session.commit()

        log.info(
            "proposals.approved",
            proposal_id=str(proposal_id),
            approved_by=str(ctx.user_id),
        )
        _log_event(ProposalApproved(
            proposal_id=proposal_id,
            tenant_id=ctx.org_id,
            approved_by=ctx.user_id,
        ))

        proposal.approval_status = "approved"
        proposal.approved_by = ctx.user_id
        proposal.approved_at = now
        return ProposalOut.model_validate(proposal)

    async def reject(self, proposal_id: uuid.UUID, *, reason: str) -> ProposalOut:
        """Transition proposal approval_status: pending_approval → rejected.

        Requires OrgAdmin role. Uses SELECT FOR UPDATE to prevent concurrent
        double-rejection races.
        """
        ctx = get_tenant_context()
        _require_approver_role(ctx)

        proposal = await self._require_proposal_for_update(proposal_id)
        if proposal.approval_status != "pending_approval":
            raise ConflictError(
                f"Proposal {proposal_id} cannot be rejected "
                f"(current approval_status: '{proposal.approval_status}')."
            )

        await self._repo.update_fields(
            proposal_id,
            approval_status="rejected",
            rejected_reason=reason,
        )

        await self._compliance.record_audit_event(
            event_type="proposal.rejected",
            outcome="blocked",
            reason=reason,
            event_data={
                "proposal_id": str(proposal_id),
                "rejected_by": str(ctx.user_id),
            },
        )

        await self._session.commit()

        log.info(
            "proposals.rejected",
            proposal_id=str(proposal_id),
            rejected_by=str(ctx.user_id),
        )
        _log_event(ProposalRejected(
            proposal_id=proposal_id,
            tenant_id=ctx.org_id,
            rejected_by=ctx.user_id,
            rejected_reason=reason,
        ))

        proposal.approval_status = "rejected"
        proposal.rejected_reason = reason
        return ProposalOut.model_validate(proposal)

    # ── Delivery ────────────────────────────────────────────────────────────────

    async def deliver(self, proposal_id: uuid.UUID) -> ProposalOut:
        """Initiate email delivery of an approved proposal.

        Creates an OutboundMessage linked to this proposal, runs the full
        ComplianceGuard pipeline via OutreachService.send_message(), writes a
        CRM activity, and records an audit event.

        Idempotency: proposal.status == 'sent' is the guard.  Once set it is
        never cleared — concurrent duplicate requests both hit the SELECT FOR
        UPDATE and the second sees status='sent', raising ConflictError before
        any OutboundMessage is created.

        Proposal.status transitions to 'sent' regardless of compliance outcome.
        The execution state (queued / blocked / sent / failed) is owned by
        OutboundMessage and surfaced as ProposalOut.delivery_status.
        """
        ctx = get_tenant_context()

        proposal = await self._require_proposal_for_update(proposal_id)

        if proposal.approval_status != "approved":
            raise ConflictError(
                f"Proposal {proposal_id} must be approved before sending "
                f"(current approval_status: '{proposal.approval_status}')."
            )
        if proposal.status == "sent":
            raise ConflictError(f"Proposal {proposal_id} has already been sent.")

        # Verify contact email exists before creating any records.
        contact_email = await self._fetch_contact_email(proposal.contact_id, ctx.org_id)
        if not contact_email:
            raise NotFoundError(
                f"Contact {proposal.contact_id} not found or has no email address."
            )

        # Extract email content from proposal JSONB.
        # When the LLM returns a rich structured dict (executive_summary,
        # proposed_training, etc.) there may be no flat "body" key — in that
        # case serialize the full content so the email body is never empty.
        subject: str = str(proposal.content.get("subject") or proposal.title)
        body: str = str(
            proposal.content.get("body")
            or json.dumps(proposal.content, indent=2, ensure_ascii=False)
        )
        if not body:
            raise ValidationError("Proposal content is empty — cannot generate email body.")

        # ── Atomic step 1: create OutboundMessage + transition proposal ──────
        # Both writes in one transaction so a crash between them leaves no
        # orphan — the migration is expand-only and the row has no FK constraint
        # back to proposals.
        outbound_id = uuid.uuid4()
        now = datetime.now(UTC)

        # Raw SQL INSERT — no cross-module ORM model import (module boundary rule).
        await self._session.execute(
            text(
                "INSERT INTO outbound_messages"
                " (id, tenant_id, contact_id, channel, subject, body, status, created_at)"
                " VALUES (:id, :tid, :cid, 'email', :subject, :body, 'draft', now())"
            ),
            {
                "id": str(outbound_id),
                "tid": str(ctx.org_id),
                "cid": str(proposal.contact_id),
                "subject": subject,
                "body": body,
            },
        )
        await self._repo.update_fields(
            proposal_id,
            outbound_message_id=outbound_id,
            status="sent",
            sent_at=now,
        )
        await self._session.commit()

        # ── Step 2: compliance gate + Celery enqueue (or block) ──────────────
        # Imported inside method to avoid circular import at module-load time
        # (same pattern as OutreachService importing the Celery task).
        from corpmind.modules.outreach.service import OutreachService  # noqa: PLC0415

        send_resp = await OutreachService(self._session).send_message(outbound_id)

        # ── Step 3: audit event + CRM activity (single transaction) ──────────
        queued = send_resp.status == "queued"

        await self._compliance.record_audit_event(
            event_type="proposal.delivery_queued" if queued else "proposal.delivery_blocked",
            outcome="allowed" if queued else "blocked",
            reason=None if queued else (send_resp.compliance_reason or "compliance"),
            event_data={
                "proposal_id": str(proposal_id),
                "outbound_message_id": str(outbound_id),
                "contact_id": str(proposal.contact_id),
            },
        )

        summary = (
            "Proposal sent — delivery queued."
            if queued
            else f"Proposal send blocked: {send_resp.compliance_reason or 'compliance policy'}."
        )
        # Raw SQL INSERT into crm_activities — no cross-module ORM import.
        await self._session.execute(
            text(
                "INSERT INTO crm_activities"
                " (id, tenant_id, workspace_id, contact_id, type, summary,"
                "  source_outbound_message_id, created_at)"
                " VALUES (:id, :tid, :wsid, :cid, 'proposal_sent', :summary, :omid, now())"
            ),
            {
                "id": str(uuid.uuid4()),
                "tid": str(ctx.org_id),
                "wsid": str(proposal.workspace_id),
                "cid": str(proposal.contact_id),
                "summary": summary,
                "omid": str(outbound_id),
            },
        )
        await self._session.commit()

        log.info(
            "proposals.delivered",
            proposal_id=str(proposal_id),
            outbound_message_id=str(outbound_id),
            delivery_status=send_resp.status,
        )
        _log_event(
            ProposalDeliveryQueued(
                proposal_id=proposal_id,
                tenant_id=ctx.org_id,
                outbound_message_id=outbound_id,
            )
            if queued
            else ProposalDeliveryBlocked(
                proposal_id=proposal_id,
                tenant_id=ctx.org_id,
                outbound_message_id=outbound_id,
                compliance_reason=send_resp.compliance_reason,
            )
        )

        proposal.status = "sent"
        proposal.sent_at = now
        proposal.outbound_message_id = outbound_id
        out = ProposalOut.model_validate(proposal)
        out.delivery_status = send_resp.status
        return out

    # ── Client response ─────────────────────────────────────────────────────────

    async def record_acceptance(
        self, proposal_id: uuid.UUID, req: AcceptProposalRequest
    ) -> ProposalOut:
        """Record the client's acceptance of a sent proposal.

        Guards: proposal must be in status='sent' with no prior client response.
        Sets client_status='accepted', client_accepted_at, actual_value_inr.
        If proposal.lead_id is set, advances the lead to 'booked' (idempotent).
        Writes a CRM activity and audit event; emits ProposalAccepted.
        """
        ctx = get_tenant_context()
        proposal = await self._require_proposal_for_update(proposal_id)

        if proposal.status != "sent":
            raise ConflictError(
                f"Proposal {proposal_id} cannot be accepted "
                f"(status must be 'sent', current: '{proposal.status}')."
            )
        if proposal.client_status is not None:
            raise ConflictError(
                f"Proposal {proposal_id} already has a client response "
                f"(client_status: '{proposal.client_status}')."
            )

        now = datetime.now(UTC)
        update_values: dict[str, object] = {
            "client_status": "accepted",
            "client_accepted_at": now,
            "actual_value_inr": req.actual_value_inr,
        }
        if req.expected_value_inr is not None:
            update_values["expected_value_inr"] = req.expected_value_inr

        await self._repo.update_fields(proposal_id, **update_values)

        # Advance lead to 'booked' if it isn't already terminal.
        # Raw SQL — no cross-module ORM import (module boundary rule).
        if proposal.lead_id is not None:
            await self._session.execute(
                text(
                    "UPDATE leads SET stage = 'booked', booked_at = now(),"
                    " updated_at = now()"
                    " WHERE id = :lid AND tenant_id = :tid"
                    " AND stage NOT IN ('booked', 'lost')"
                ),
                {"lid": str(proposal.lead_id), "tid": str(ctx.org_id)},
            )

        value_str = f"₹{req.actual_value_inr:,.0f}"
        await self._session.execute(
            text(
                "INSERT INTO crm_activities"
                " (id, tenant_id, workspace_id, contact_id, type, summary,"
                "  source_outbound_message_id, created_at)"
                " VALUES (:id, :tid, :wsid, :cid, 'proposal_accepted', :summary,"
                "  :omid, now())"
            ),
            {
                "id": str(uuid.uuid4()),
                "tid": str(ctx.org_id),
                "wsid": str(proposal.workspace_id),
                "cid": str(proposal.contact_id),
                "summary": f"Booking confirmed — {value_str}",
                "omid": str(proposal.outbound_message_id) if proposal.outbound_message_id else None,
            },
        )

        await self._compliance.record_audit_event(
            event_type="proposal.accepted",
            outcome="allowed",
            event_data={
                "proposal_id": str(proposal_id),
                "actual_value_inr": str(req.actual_value_inr),
                "contact_id": str(proposal.contact_id),
            },
        )
        await self._session.commit()

        log.info(
            "proposals.accepted",
            proposal_id=str(proposal_id),
            actual_value_inr=str(req.actual_value_inr),
            contact_id=str(proposal.contact_id),
        )
        _log_event(ProposalAccepted(
            proposal_id=proposal_id,
            tenant_id=ctx.org_id,
            contact_id=proposal.contact_id,
            actual_value_inr=req.actual_value_inr,
        ))

        proposal.client_status = "accepted"
        proposal.client_accepted_at = now
        proposal.actual_value_inr = req.actual_value_inr
        if req.expected_value_inr is not None:
            proposal.expected_value_inr = req.expected_value_inr
        return ProposalOut.model_validate(proposal)

    async def record_declination(
        self, proposal_id: uuid.UUID, req: DeclineProposalRequest
    ) -> ProposalOut:
        """Record the client's declination of a sent proposal.

        Guards: proposal must be in status='sent' with no prior client response.
        Sets client_status='declined', client_declined_at.
        Writes a CRM activity and audit event; emits ProposalDeclined.
        The lead stage is NOT changed — a declined proposal leaves the lead in
        whatever stage it was in so the trainer can re-engage.
        """
        ctx = get_tenant_context()
        proposal = await self._require_proposal_for_update(proposal_id)

        if proposal.status != "sent":
            raise ConflictError(
                f"Proposal {proposal_id} cannot be declined "
                f"(status must be 'sent', current: '{proposal.status}')."
            )
        if proposal.client_status is not None:
            raise ConflictError(
                f"Proposal {proposal_id} already has a client response "
                f"(client_status: '{proposal.client_status}')."
            )

        now = datetime.now(UTC)
        await self._repo.update_fields(
            proposal_id,
            client_status="declined",
            client_declined_at=now,
        )

        summary = "Client declined proposal"
        if req.reason:
            summary = f"Client declined proposal: {req.reason}"

        await self._session.execute(
            text(
                "INSERT INTO crm_activities"
                " (id, tenant_id, workspace_id, contact_id, type, summary,"
                "  source_outbound_message_id, created_at)"
                " VALUES (:id, :tid, :wsid, :cid, 'proposal_declined', :summary,"
                "  :omid, now())"
            ),
            {
                "id": str(uuid.uuid4()),
                "tid": str(ctx.org_id),
                "wsid": str(proposal.workspace_id),
                "cid": str(proposal.contact_id),
                "summary": summary,
                "omid": str(proposal.outbound_message_id) if proposal.outbound_message_id else None,
            },
        )

        await self._compliance.record_audit_event(
            event_type="proposal.declined",
            outcome="allowed",
            event_data={
                "proposal_id": str(proposal_id),
                "reason": req.reason or "",
                "contact_id": str(proposal.contact_id),
            },
        )
        await self._session.commit()

        log.info(
            "proposals.declined",
            proposal_id=str(proposal_id),
            contact_id=str(proposal.contact_id),
        )
        _log_event(ProposalDeclined(
            proposal_id=proposal_id,
            tenant_id=ctx.org_id,
            contact_id=proposal.contact_id,
            reason=req.reason,
        ))

        proposal.client_status = "declined"
        proposal.client_declined_at = now
        return ProposalOut.model_validate(proposal)

    # ── Helpers ─────────────────────────────────────────────────────────────────

    async def _require_proposal(self, proposal_id: uuid.UUID) -> Proposal:
        proposal = await self._repo.find_by_id(proposal_id)
        if not proposal:
            raise NotFoundError(f"Proposal {proposal_id} not found")
        return proposal

    async def _require_proposal_for_update(self, proposal_id: uuid.UUID) -> Proposal:
        proposal = await self._repo.find_by_id_for_update(proposal_id)
        if not proposal:
            raise NotFoundError(f"Proposal {proposal_id} not found")
        return proposal

    async def _fetch_contact_email(
        self, contact_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> str | None:
        """Raw SQL lookup for contact email — no cross-module ORM import."""
        result = await self._session.execute(
            text(
                "SELECT email FROM hr_contacts"
                " WHERE id = :cid AND tenant_id = :tid"
            ),
            {"cid": str(contact_id), "tid": str(tenant_id)},
        )
        row = result.one_or_none()
        return row[0] if row and row[0] else None

    async def _fetch_delivery_status(
        self, outbound_message_id: uuid.UUID | None
    ) -> str | None:
        """Derive delivery_status from OutboundMessage.status via raw SQL."""
        if outbound_message_id is None:
            return None
        ctx = get_tenant_context()
        result = await self._session.execute(
            text(
                "SELECT status FROM outbound_messages"
                " WHERE id = :mid AND tenant_id = :tid"
            ),
            {"mid": str(outbound_message_id), "tid": str(ctx.org_id)},
        )
        row = result.one_or_none()
        return row[0] if row else None


def _require_approver_role(ctx: TenantContext) -> None:
    if ctx.role not in _APPROVER_ROLES:
        raise PermissionDeniedError("Only OrgAdmin can approve or reject proposals.")


def _parse_content(raw: str) -> dict[str, object]:
    """Extract a JSON dict from the model output.

    Falls back to a title+body stub so a proposal record is always created
    even if the model returns malformed JSON.
    """
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return {"title": raw[:200], "body": raw}


def _log_event(event: object) -> None:
    """Structured-log a domain event until a real event bus is wired up."""
    log.info("proposals.domain_event", event_type=type(event).__name__, payload=repr(event))
