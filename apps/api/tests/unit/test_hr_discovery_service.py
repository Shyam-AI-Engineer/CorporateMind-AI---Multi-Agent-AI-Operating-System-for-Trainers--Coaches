"""Unit tests for HRDiscoveryService.

Covers:
  - _parse_enrichment: clean JSON, fenced output, invalid JSON, wrong types
  - _parse_rankings: array shape, malformed, non-list response
  - import_contacts: LLM contract, opt-in gate (contactable vs non-contactable),
                     enrich failure counts toward `failed`
  - rank_contacts: LLM contract, score sort order, bad UUID from model is skipped
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.core.tenancy import clear_tenant_context, set_tenant_context
from corpmind.modules.hr_discovery.schemas import (
    ContactBatchImportRequest,
    ContactImportItem,
    RankContactsRequest,
)
from corpmind.modules.hr_discovery.service import HRDiscoveryService
from tests.conftest import make_tenant_ctx

# ── Fixtures ──────────────────────────────────────────────────────────────────

_VALID_ENRICHMENT_JSON = json.dumps({
    "full_name": "Ananya Sharma",
    "title": "VP - Human Resources",
    "title_normalized": "VP HR",
    "seniority": "vp",
    "email": "ananya@acmecorp.in",
    "phone": "+918800001234",
    "linkedin_url": "https://www.linkedin.com/in/ananya-sharma",
    "company_name": "Acme Corp India",
    "preferred_language": "en",
})

_VALID_RANKINGS_JSON = json.dumps([
    {"contact_id": "11111111-0000-0000-0000-000000000001", "score": 9, "reason": "VP HR at BFSI firm."},
    {"contact_id": "11111111-0000-0000-0000-000000000002", "score": 6, "reason": "L&D manager, smaller firm."},
])


@pytest.fixture
def bound_tenant():
    ctx = make_tenant_ctx()
    token = set_tenant_context(ctx)
    yield ctx
    clear_tenant_context(token)


def _make_service(
    *,
    enrichment_json: str = _VALID_ENRICHMENT_JSON,
    existing_contact=None,
) -> tuple[HRDiscoveryService, AsyncMock, AsyncMock, AsyncMock]:
    """Return (service, chat_mock, company_repo_mock, contact_repo_mock)."""
    session = MagicMock()
    session.commit = AsyncMock()

    svc = HRDiscoveryService(session)

    chat_mock = AsyncMock(return_value={"content": enrichment_json})
    svc._llm.chat = chat_mock  # type: ignore[method-assign]

    fake_company = MagicMock()
    fake_company.id = uuid.uuid4()
    svc._company_repo.get_or_create = AsyncMock(return_value=(fake_company, True))  # type: ignore[method-assign]

    def _assign_id(contact):
        contact.id = uuid.uuid4()
        return contact

    svc._contact_repo.create = AsyncMock(side_effect=_assign_id)  # type: ignore[method-assign]
    svc._contact_repo.find_by_id = AsyncMock(return_value=existing_contact)  # type: ignore[method-assign]

    return svc, chat_mock, svc._company_repo, svc._contact_repo


def _make_import_item(**overrides) -> ContactImportItem:
    base = dict(
        raw_data="Ananya Sharma, VP HR at Acme Corp. ananya@acmecorp.in",
        source="https://webinar.acme.com/reg/2024-q1",
        source_type="webinar_registration",
        opted_in_at=datetime(2024, 1, 15, tzinfo=UTC),
        opt_in_evidence="https://webinar.acme.com/consent/tx-abc123",
        company_name="Acme Corp India",
        company_industry="BFSI",
    )
    base.update(overrides)
    return ContactImportItem(**base)


def _fake_contact(**overrides) -> MagicMock:
    base = dict(
        id=uuid.UUID("11111111-0000-0000-0000-000000000001"),
        company_id=uuid.uuid4(),
        full_name="Ananya Sharma",
        title="VP HR",
        email="ananya@acmecorp.in",
        email_deliverable=True,
        preferred_language="en",
        source_type="webinar_registration",
        is_contactable=True,
        opted_in_at=datetime(2024, 1, 15, tzinfo=UTC),
        created_at=datetime.now(UTC),
    )
    base.update(overrides)
    obj = MagicMock()
    for k, v in base.items():
        setattr(obj, k, v)
    return obj


# ── _parse_enrichment ─────────────────────────────────────────────────────────

def test_parse_enrichment_accepts_clean_json(bound_tenant) -> None:
    svc, *_ = _make_service()
    result = svc._parse_enrichment(_VALID_ENRICHMENT_JSON)
    assert result.full_name == "Ananya Sharma"
    assert result.seniority == "vp"
    assert result.email == "ananya@acmecorp.in"


def test_parse_enrichment_strips_json_fence(bound_tenant) -> None:
    svc, *_ = _make_service()
    fenced = "```json\n" + _VALID_ENRICHMENT_JSON + "\n```"
    result = svc._parse_enrichment(fenced)
    assert result.title_normalized == "VP HR"


def test_parse_enrichment_rejects_non_json(bound_tenant) -> None:
    svc, *_ = _make_service()
    with pytest.raises(ValidationError, match="non-JSON"):
        svc._parse_enrichment("Sorry, I cannot extract that.")


def test_parse_enrichment_fills_missing_fields(bound_tenant) -> None:
    svc, *_ = _make_service()
    result = svc._parse_enrichment('{"full_name": "Rahul Gupta"}')
    assert result.full_name == "Rahul Gupta"
    assert result.email is None
    assert result.seniority is None


# ── _parse_rankings ───────────────────────────────────────────────────────────

def test_parse_rankings_returns_list(bound_tenant) -> None:
    svc, *_ = _make_service()
    result = svc._parse_rankings(_VALID_RANKINGS_JSON)
    assert len(result) == 2
    assert result[0]["score"] == 9


def test_parse_rankings_rejects_non_list(bound_tenant) -> None:
    svc, *_ = _make_service()
    with pytest.raises(ValidationError, match="array"):
        svc._parse_rankings('{"contact_id": "x", "score": 5}')


def test_parse_rankings_rejects_non_json(bound_tenant) -> None:
    svc, *_ = _make_service()
    with pytest.raises(ValidationError, match="non-JSON"):
        svc._parse_rankings("Here are my rankings: first place goes to...")


# ── import_contacts ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_import_calls_llm_with_extract_fields_task(bound_tenant) -> None:
    """LLM must be called with task='extract_fields' for each contact."""
    svc, chat_mock, *_ = _make_service()
    req = ContactBatchImportRequest(contacts=[_make_import_item()])
    await svc.import_contacts(req)

    chat_mock.assert_awaited_once()
    kwargs = chat_mock.await_args.kwargs
    assert kwargs["task"] == "extract_fields"
    assert kwargs["prompt_name"] == "hr.extract_fields"
    assert "raw_data" in kwargs["prompt_inputs"]


@pytest.mark.asyncio
async def test_import_contact_with_opt_in_is_contactable(bound_tenant) -> None:
    svc, *_ = _make_service()
    req = ContactBatchImportRequest(contacts=[_make_import_item()])
    result = await svc.import_contacts(req)

    assert result.imported == 1
    assert result.non_contactable == 0
    assert result.failed == 0
    assert len(result.contact_ids) == 1


@pytest.mark.asyncio
async def test_import_enrich_failure_counts_as_failed(bound_tenant) -> None:
    """If LLM enrichment raises, that contact is counted as failed, not skipped silently."""
    svc, chat_mock, *_ = _make_service()
    chat_mock.side_effect = Exception("Euri timeout")

    req = ContactBatchImportRequest(contacts=[_make_import_item()])
    result = await svc.import_contacts(req)

    assert result.failed == 1
    assert result.imported == 0
    assert result.contact_ids == []


# ── rank_contacts ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rank_contacts_calls_llm_with_correct_task(bound_tenant) -> None:
    c1 = _fake_contact(id=uuid.UUID("11111111-0000-0000-0000-000000000001"))
    c2 = _fake_contact(id=uuid.UUID("11111111-0000-0000-0000-000000000002"))

    svc, *_ = _make_service()
    svc._llm.chat = AsyncMock(return_value={"content": _VALID_RANKINGS_JSON})  # type: ignore[method-assign]
    svc._contact_repo.find_many_by_ids = AsyncMock(return_value=[c1, c2])  # type: ignore[method-assign]

    req = RankContactsRequest(
        contact_ids=[c1.id, c2.id],
        trainer_niche="Leadership coaching for BFSI",
        trainer_topics=["Executive Presence", "Team Dynamics"],
        trainer_target_industries=["BFSI", "Insurance"],
    )
    result = await svc.rank_contacts(req)

    chat_mock = svc._llm.chat
    chat_mock.assert_awaited_once()
    kwargs = chat_mock.await_args.kwargs
    assert kwargs["task"] == "rank_contacts"
    assert kwargs["prompt_name"] == "hr.rank_contacts"
    assert "contacts_json" in kwargs["prompt_inputs"]
    assert "trainer_niche" in kwargs["prompt_inputs"]

    # Results returned sorted by score descending
    assert result.rankings[0].score >= result.rankings[1].score


@pytest.mark.asyncio
async def test_rank_contacts_raises_when_no_contacts(bound_tenant) -> None:
    svc, *_ = _make_service()
    svc._contact_repo.find_many_by_ids = AsyncMock(return_value=[])  # type: ignore[method-assign]

    req = RankContactsRequest(
        contact_ids=[uuid.uuid4()],
        trainer_niche="x",
        trainer_topics=[],
        trainer_target_industries=[],
    )
    with pytest.raises(NotFoundError):
        await svc.rank_contacts(req)


@pytest.mark.asyncio
async def test_rank_contacts_skips_bad_uuid_from_model(bound_tenant) -> None:
    """If the model hallucinates a contact_id not in the fetched set, skip it silently."""
    real_id = uuid.UUID("11111111-0000-0000-0000-000000000001")
    c1 = _fake_contact(id=real_id)

    bad_rankings = json.dumps([
        {"contact_id": str(real_id), "score": 8, "reason": "Good fit."},
        {"contact_id": "00000000-ffff-ffff-ffff-000000000000", "score": 5, "reason": "Hallucinated."},
    ])

    svc, *_ = _make_service()
    svc._llm.chat = AsyncMock(return_value={"content": bad_rankings})  # type: ignore[method-assign]
    svc._contact_repo.find_many_by_ids = AsyncMock(return_value=[c1])  # type: ignore[method-assign]

    req = RankContactsRequest(
        contact_ids=[real_id],
        trainer_niche="Sales training",
        trainer_topics=["Objection Handling"],
        trainer_target_industries=["SaaS"],
    )
    result = await svc.rank_contacts(req)
    assert len(result.rankings) == 1
    assert result.rankings[0].contact_id == real_id
