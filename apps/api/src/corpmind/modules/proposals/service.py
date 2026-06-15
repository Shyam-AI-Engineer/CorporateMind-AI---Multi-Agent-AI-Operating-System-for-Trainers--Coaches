"""Proposals service — AI-generated proposal lifecycle.

Lifecycle
─────────
draft ──approve──► draft (approval_status: pending_approval → approved)
draft ──reject──►  draft (approval_status: pending_approval → rejected)
draft ──mark_sent──► sent  (requires approval_status = 'approved')

Proposals are generated for leads in 'meeting_completed' or 'booked' stage.
Re-generating creates a new proposal; old ones are preserved.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.ai.euri_client import EuriClient
from corpmind.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from corpmind.core.tenancy import TenantContext, get_tenant_context
from corpmind.modules.compliance.service import ComplianceService
from corpmind.modules.crm.schemas import LeadOut
from corpmind.modules.proposals.events import (
    ProposalApproved,
    ProposalGenerated,
    ProposalRejected,
    ProposalSent,
)
from corpmind.modules.proposals.models import Proposal
from corpmind.modules.proposals.repo import ProposalRepo
from corpmind.modules.proposals.schemas import (
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
        return ProposalOut.model_validate(await self._require_proposal(proposal_id))

    async def list_proposals(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        approval_status: str | None = None,
    ) -> ProposalListOut:
        proposals, total = await asyncio.gather(
            self._repo.list_by_workspace(
                workspace_id, limit=limit, offset=offset, approval_status=approval_status
            ),
            self._repo.count_by_workspace(workspace_id, approval_status=approval_status),
        )
        return ProposalListOut(
            items=[ProposalOut.model_validate(p) for p in proposals],
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

    # ── State transition ────────────────────────────────────────────────────────

    async def mark_sent(self, proposal_id: uuid.UUID) -> ProposalOut:
        """Transition a draft proposal to 'sent' and record the sent timestamp.

        Requires approval_status = 'approved' before transitioning.
        """
        proposal = await self._require_proposal(proposal_id)
        if proposal.status == "sent":
            raise ConflictError(f"Proposal {proposal_id} has already been sent.")
        if proposal.approval_status != "approved":
            raise ConflictError(
                f"Proposal {proposal_id} must be approved before sending "
                f"(current approval_status: '{proposal.approval_status}')."
            )

        sent_at = datetime.now(UTC)
        await self._repo.update_fields(proposal_id, status="sent", sent_at=sent_at)
        await self._session.commit()

        log.info("proposals.sent", proposal_id=str(proposal_id))
        _log_event(ProposalSent(proposal_id=proposal_id, tenant_id=proposal.tenant_id))

        proposal.status = "sent"
        proposal.sent_at = sent_at
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
