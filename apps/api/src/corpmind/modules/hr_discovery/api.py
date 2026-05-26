"""HR discovery module REST API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.hr_discovery.schemas import (
    ContactBatchImportRequest,
    ContactBatchImportResponse,
    ContactListResponse,
    HRContactOut,
    RankContactsRequest,
    RankContactsResponse,
)
from corpmind.modules.hr_discovery.service import HRDiscoveryService

router = APIRouter()


@router.post(
    "/contacts/import",
    response_model=ContactBatchImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_contacts(
    req: ContactBatchImportRequest,
    session: AsyncSession = Depends(get_session),
) -> ContactBatchImportResponse:
    """Batch import HR contacts with LLM field extraction and opt-in enforcement.

    Each contact's raw_data is enriched via EuriClient(task='extract_fields').
    Contacts missing opted_in_at or opt_in_evidence are persisted as
    non_contactable and excluded from all outreach segments.
    """
    svc = HRDiscoveryService(session)
    return await svc.import_contacts(req)


@router.get("/contacts", response_model=ContactListResponse)
async def list_contacts(
    company_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ContactListResponse:
    svc = HRDiscoveryService(session)
    return await svc.list_contacts(company_id=company_id, limit=limit, offset=offset)


@router.get("/contacts/{contact_id}", response_model=HRContactOut)
async def get_contact(
    contact_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> HRContactOut:
    svc = HRDiscoveryService(session)
    return await svc.get_contact(contact_id)


@router.post("/contacts/rank", response_model=RankContactsResponse)
async def rank_contacts(
    req: RankContactsRequest,
    session: AsyncSession = Depends(get_session),
) -> RankContactsResponse:
    """Score and rank contacts by fit for the given trainer profile snapshot.

    Contact IDs and the trainer's niche/topics/industries come from the caller —
    fetch GET /trainer/profile first, then pass the relevant fields here.
    """
    svc = HRDiscoveryService(session)
    return await svc.rank_contacts(req)
