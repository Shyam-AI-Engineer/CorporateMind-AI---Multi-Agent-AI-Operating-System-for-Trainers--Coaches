"""HR discovery service.

Phase 1 operations:
  import_contacts()  — batch import with opt-in gate + LLM field extraction
  list_contacts()    — paginated list of contactable contacts
  get_contact()      — single contact detail
  rank_contacts()    — score a contact set against a trainer profile via LLM
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.ai.euri_client import EuriClient
from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.hr_discovery.models import HRContact
from corpmind.modules.hr_discovery.repo import CompanyRepo, ContactFilters, HRContactRepo
from corpmind.modules.hr_discovery.schemas import (
    ContactBatchImportRequest,
    ContactBatchImportResponse,
    ContactListResponse,
    HRContactEnrichment,
    HRContactOut,
    RankContactsRequest,
    RankContactsResponse,
    RankedContactOut,
)

log = structlog.get_logger(__name__)


class HRDiscoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._company_repo = CompanyRepo(session)
        self._contact_repo = HRContactRepo(session)
        self._llm = EuriClient(session=session)

    async def import_contacts(
        self, req: ContactBatchImportRequest
    ) -> ContactBatchImportResponse:
        ctx = get_tenant_context()
        imported_ids: list[uuid.UUID] = []
        imported = non_contactable = failed = 0

        for item in req.contacts:
            try:
                enrichment = await self._enrich_contact(item.raw_data)
            except Exception as exc:
                log.warning("hr.import.enrich_failed", error=str(exc))
                failed += 1
                continue

            company, _ = await self._company_repo.get_or_create(
                name=enrichment.company_name or item.company_name,
                industry=item.company_industry,
                city=item.company_city,
                country=item.company_country,
            )

            # Opt-in evidence gate — never bypassed; non-contactable contacts are
            # persisted for audit but excluded from every send segment.
            is_contactable = bool(
                item.opted_in_at and item.opt_in_evidence and item.source_type
            )
            contact = HRContact(
                tenant_id=ctx.org_id,
                company_id=company.id,
                full_name=enrichment.full_name or "Unknown",
                title=enrichment.title_normalized or enrichment.title,
                email=enrichment.email,
                phone=enrichment.phone,
                linkedin_url=enrichment.linkedin_url,
                preferred_language=enrichment.preferred_language,
                source=item.source,
                source_type=item.source_type,
                opted_in_at=item.opted_in_at,
                opt_in_evidence=item.opt_in_evidence,
                is_contactable=is_contactable,
            )
            await self._contact_repo.create(contact)
            imported_ids.append(contact.id)

            if is_contactable:
                imported += 1
            else:
                non_contactable += 1

        await self._session.commit()
        log.info(
            "hr.import.complete",
            imported=imported,
            non_contactable=non_contactable,
            failed=failed,
        )
        return ContactBatchImportResponse(
            imported=imported,
            non_contactable=non_contactable,
            failed=failed,
            contact_ids=imported_ids,
        )

    async def list_contacts(
        self,
        company_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ContactListResponse:
        filters = ContactFilters(company_id=company_id, limit=limit, offset=offset)
        contacts = await self._contact_repo.list_contacts(filters)
        return ContactListResponse(
            contacts=[HRContactOut.model_validate(c) for c in contacts],
            total=len(contacts),
            limit=limit,
            offset=offset,
        )

    async def get_contact(self, contact_id: uuid.UUID) -> HRContactOut:
        contact = await self._contact_repo.find_by_id(contact_id)
        if contact is None:
            raise NotFoundError(f"Contact {contact_id} not found.")
        return HRContactOut.model_validate(contact)

    async def rank_contacts(self, req: RankContactsRequest) -> RankContactsResponse:
        ctx = get_tenant_context()
        contacts = await self._contact_repo.find_many_by_ids(req.contact_ids)
        if not contacts:
            raise NotFoundError("No contacts found for the given IDs.")

        contacts_payload = [
            {
                "contact_id": str(c.id),
                "title": c.title or "Unknown",
                "company_id": str(c.company_id),
            }
            for c in contacts
        ]

        result = await self._llm.chat(
            task="rank_contacts",
            prompt_name="hr.rank_contacts",
            prompt_inputs={
                "trainer_niche": req.trainer_niche,
                "trainer_topics": ", ".join(req.trainer_topics),
                "trainer_target_industries": ", ".join(req.trainer_target_industries),
                "contacts_json": json.dumps(contacts_payload, ensure_ascii=False),
            },
            tenant_id=ctx.org_id,
            request_id=ctx.request_id,
            agent="hr_discovery_service",
        )

        rankings = self._parse_rankings(result["content"])
        contact_map = {c.id: c for c in contacts}

        ranked: list[RankedContactOut] = []
        for r in sorted(rankings, key=lambda x: x["score"], reverse=True):
            try:
                cid = uuid.UUID(str(r["contact_id"]))
            except (ValueError, KeyError):
                continue
            if cid not in contact_map:
                continue
            ranked.append(
                RankedContactOut(
                    contact_id=cid,
                    score=int(r["score"]),
                    reason=str(r["reason"]),
                    contact=HRContactOut.model_validate(contact_map[cid]),
                )
            )

        return RankContactsResponse(ranked=ranked)

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _enrich_contact(self, raw_data: str) -> HRContactEnrichment:
        ctx = get_tenant_context()
        result = await self._llm.chat(
            task="extract_fields",
            prompt_name="hr.extract_fields",
            prompt_inputs={"raw_data": raw_data},
            tenant_id=ctx.org_id,
            request_id=ctx.request_id,
            agent="hr_discovery_service",
        )
        return self._parse_enrichment(result["content"])

    def _parse_enrichment(self, raw: str) -> HRContactEnrichment:
        stripped = raw.strip().strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].lstrip()
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Contact enrichment returned non-JSON: {exc}") from exc
        try:
            return HRContactEnrichment.model_validate(payload)
        except PydanticValidationError as exc:
            raise ValidationError(f"Contact enrichment failed schema: {exc}") from exc

    def _parse_rankings(self, raw: str) -> list[dict[str, Any]]:
        stripped = raw.strip().strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].lstrip()
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Ranking returned non-JSON: {exc}") from exc
        if not isinstance(payload, list):
            raise ValidationError("Ranking response must be a JSON array.")
        return payload
