"""Proposals module REST API."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.crm.service import CRMService
from corpmind.modules.proposals.schemas import (
    AcceptProposalRequest,
    DeclineProposalRequest,
    GenerateProposalRequest,
    ProposalListOut,
    ProposalOut,
    ProposalRejectRequest,
    ProposalSendRequest,
)
from corpmind.modules.proposals.service import ProposalService

router = APIRouter()

_VALID_APPROVAL_STATUSES = {"pending_approval", "approved", "rejected"}


@router.post(
    "/",
    response_model=ProposalOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate an AI proposal document for a CRM lead",
)
async def generate_proposal(
    req: GenerateProposalRequest,
    session: AsyncSession = Depends(get_session),
) -> ProposalOut:
    lead = await CRMService(session).get_lead(req.lead_id)
    return await ProposalService(session).generate(req, lead)


@router.get(
    "/",
    response_model=ProposalListOut,
    summary="List proposals for a workspace",
)
async def list_proposals(
    workspace_id: uuid.UUID = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    approval_status: str | None = Query(default=None),
    contact_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> ProposalListOut:
    validated_status: str | None = None
    if approval_status is not None:
        if approval_status not in _VALID_APPROVAL_STATUSES:
            from corpmind.core.exceptions import ValidationError
            raise ValidationError(
                f"approval_status must be one of {sorted(_VALID_APPROVAL_STATUSES)}"
            )
        validated_status = approval_status

    return await ProposalService(session).list_proposals(
        workspace_id,
        limit=limit,
        offset=offset,
        approval_status=validated_status,
        contact_id=contact_id,
    )


@router.get(
    "/{proposal_id}",
    response_model=ProposalOut,
    summary="Get a proposal by ID",
)
async def get_proposal(
    proposal_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ProposalOut:
    return await ProposalService(session).get_proposal(proposal_id)


@router.post(
    "/{proposal_id}/approve",
    response_model=ProposalOut,
    summary="Approve a proposal (OrgAdmin only)",
)
async def approve_proposal(
    proposal_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ProposalOut:
    return await ProposalService(session).approve(proposal_id)


@router.post(
    "/{proposal_id}/reject",
    response_model=ProposalOut,
    summary="Reject a proposal with a reason (OrgAdmin only)",
)
async def reject_proposal(
    proposal_id: uuid.UUID,
    req: ProposalRejectRequest,
    session: AsyncSession = Depends(get_session),
) -> ProposalOut:
    return await ProposalService(session).reject(proposal_id, reason=req.reason)


@router.post(
    "/{proposal_id}/send",
    response_model=ProposalOut,
    summary="Deliver an approved proposal via email (requires prior approval)",
)
async def send_proposal(
    proposal_id: uuid.UUID,
    _req: ProposalSendRequest = ProposalSendRequest(),
    session: AsyncSession = Depends(get_session),
) -> ProposalOut:
    return await ProposalService(session).deliver(proposal_id)


@router.post(
    "/{proposal_id}/accept",
    response_model=ProposalOut,
    summary="Record client acceptance and confirmed deal value (Sprint 18A)",
)
async def accept_proposal(
    proposal_id: uuid.UUID,
    req: AcceptProposalRequest,
    session: AsyncSession = Depends(get_session),
) -> ProposalOut:
    return await ProposalService(session).record_acceptance(proposal_id, req)


@router.post(
    "/{proposal_id}/decline",
    response_model=ProposalOut,
    summary="Record client declination of a sent proposal (Sprint 18A)",
)
async def decline_proposal(
    proposal_id: uuid.UUID,
    req: DeclineProposalRequest,
    session: AsyncSession = Depends(get_session),
) -> ProposalOut:
    return await ProposalService(session).record_declination(proposal_id, req)
