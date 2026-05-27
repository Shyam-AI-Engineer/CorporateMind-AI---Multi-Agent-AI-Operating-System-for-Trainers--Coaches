"""Proposals service — AI-generated proposal lifecycle.

Lifecycle
─────────
draft ──mark_sent──► sent

Proposals are generated for leads in 'meeting_completed' or 'booked' stage.
Re-generating creates a new proposal; old ones are preserved.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.ai.euri_client import EuriClient
from corpmind.core.exceptions import ConflictError, NotFoundError
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.crm.schemas import LeadOut
from corpmind.modules.proposals.events import ProposalGenerated, ProposalSent
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


class ProposalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ProposalRepo(session)

    # ── Generation ─────────────────────────────────────────────────────────────

    async def generate(self, req: GenerateProposalRequest, lead: LeadOut) -> ProposalOut:
        """Generate an AI proposal document for a CRM lead.

        The lead must be in 'meeting_completed' or 'booked' stage.
        Multiple proposals per lead are allowed (re-generation creates a new record).
        """
        if lead.stage not in _ELIGIBLE_STAGES:
            raise ConflictError(
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
        )
        await self._repo.create(proposal)
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
    ) -> ProposalListOut:
        proposals = await self._repo.list_by_workspace(
            workspace_id, limit=limit, offset=offset
        )
        return ProposalListOut(
            items=[ProposalOut.model_validate(p) for p in proposals],
            total=len(proposals),
            limit=limit,
            offset=offset,
        )

    # ── State transition ────────────────────────────────────────────────────────

    async def mark_sent(self, proposal_id: uuid.UUID) -> ProposalOut:
        """Transition a draft proposal to 'sent' and record the sent timestamp."""
        proposal = await self._require_proposal(proposal_id)
        if proposal.status == "sent":
            raise ConflictError(f"Proposal {proposal_id} has already been sent.")

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
