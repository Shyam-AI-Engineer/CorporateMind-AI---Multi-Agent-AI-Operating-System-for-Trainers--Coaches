"""Unit tests for TrainerIntelService.

These tests mock EuriClient + repo so they exercise:
  - JSON parsing (clean, fenced, malformed)
  - Pydantic schema validation of the extraction
  - Service-level branching (locked → ConflictError, no profile → NotFoundError)
  - The contract passed to EuriClient.chat (task, prompt_name, prompt_inputs)

Per .claude/rules/testing.md, we NEVER assert exact LLM text — we assert shape
and the contract the service expects from the model.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.core.tenancy import clear_tenant_context, set_tenant_context
from corpmind.modules.trainer_intel.schemas import (
    TrainerProfileExtraction,
    TrainerProfileUpdate,
)
from corpmind.modules.trainer_intel.service import TrainerIntelService
from tests.conftest import make_tenant_ctx


# ── Fixtures ──────────────────────────────────────────────────────────────────

_VALID_EXTRACTION_JSON = """
{
  "niche": "Leadership coaching for mid-market BFSI",
  "topics": ["Executive Presence", "Team Dynamics"],
  "tone": "authoritative",
  "pricing_min_inr": 50000,
  "pricing_max_inr": 200000,
  "bio": "15 years coaching CXOs at HDFC, Kotak, Axis.",
  "usp": "Only coach combining behavioural science + balance-sheet literacy.",
  "target_industries": ["BFSI", "Insurance"],
  "languages": ["en", "hi"]
}
"""


@pytest.fixture
def bound_tenant():
    """Bind a tenant context for the test body and clear it after."""
    ctx = make_tenant_ctx()
    token = set_tenant_context(ctx)
    yield ctx
    clear_tenant_context(token)


def _make_service_with_mocks(
    *,
    llm_content: str = _VALID_EXTRACTION_JSON,
    existing_profile=None,
) -> tuple[TrainerIntelService, AsyncMock, AsyncMock]:
    """Build a TrainerIntelService whose EuriClient + repo are mocked.

    Returns (service, llm_chat_mock, repo_upsert_mock) so individual tests can
    assert call args.
    """
    session = MagicMock()
    session.commit = AsyncMock()

    svc = TrainerIntelService(session)

    chat_mock = AsyncMock(return_value={"content": llm_content})
    svc._llm.chat = chat_mock  # type: ignore[method-assign]

    svc._repo.find_for_workspace = AsyncMock(return_value=existing_profile)  # type: ignore[method-assign]

    upsert_mock = AsyncMock(return_value=_fake_profile())
    svc._repo.upsert_extraction = upsert_mock  # type: ignore[method-assign]

    return svc, chat_mock, upsert_mock


def _fake_profile(**overrides):
    """Build an object that quacks like a TrainerProfile for from_attributes validation."""
    base = dict(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        niche="Leadership coaching for mid-market BFSI",
        topics=["Executive Presence", "Team Dynamics"],
        tone="authoritative",
        pricing_min_inr=50000,
        pricing_max_inr=200000,
        bio="15 years coaching CXOs at HDFC, Kotak, Axis.",
        usp="Only coach combining behavioural science + balance-sheet literacy.",
        target_industries=["BFSI", "Insurance"],
        languages=["en", "hi"],
        is_locked=False,
        locked_at=None,
        created_at=datetime.now(UTC),
    )
    base.update(overrides)
    obj = MagicMock(spec=list(base.keys()))
    for k, v in base.items():
        setattr(obj, k, v)
    return obj


# ── _parse_extraction ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_extraction_accepts_clean_json(bound_tenant) -> None:
    """Plain JSON object → validated TrainerProfileExtraction."""
    svc, _, _ = _make_service_with_mocks()
    parsed = svc._parse_extraction(_VALID_EXTRACTION_JSON)
    assert isinstance(parsed, TrainerProfileExtraction)
    assert parsed.niche.startswith("Leadership")  # type: ignore[union-attr]
    assert "BFSI" in parsed.target_industries
    assert parsed.languages == ["en", "hi"]


@pytest.mark.asyncio
async def test_parse_extraction_strips_json_fence(bound_tenant) -> None:
    """```json fenced``` output is tolerated — defensive against model misbehavior."""
    svc, _, _ = _make_service_with_mocks()
    fenced = "```json\n" + _VALID_EXTRACTION_JSON + "\n```"
    parsed = svc._parse_extraction(fenced)
    assert parsed.tone == "authoritative"


@pytest.mark.asyncio
async def test_parse_extraction_rejects_non_json(bound_tenant) -> None:
    """Free-text prose from a misbehaving model → ValidationError, not a silent default."""
    svc, _, _ = _make_service_with_mocks()
    with pytest.raises(ValidationError, match="non-JSON"):
        svc._parse_extraction("I'm sorry, here is your profile: ...")


@pytest.mark.asyncio
async def test_parse_extraction_rejects_wrong_types(bound_tenant) -> None:
    """JSON with wrong field types fails Pydantic — caller sees a typed error."""
    svc, _, _ = _make_service_with_mocks()
    bad = '{"niche": 42, "topics": "not a list", "languages": [1, 2]}'
    with pytest.raises(ValidationError, match="schema"):
        svc._parse_extraction(bad)


@pytest.mark.asyncio
async def test_parse_extraction_fills_defaults(bound_tenant) -> None:
    """Partial JSON: missing keys use schema defaults (no fabricated values)."""
    svc, _, _ = _make_service_with_mocks()
    parsed = svc._parse_extraction('{"niche": "Sales training"}')
    assert parsed.niche == "Sales training"
    assert parsed.topics == []
    assert parsed.languages == []
    assert parsed.pricing_min_inr is None


# ── extract_from_text ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_from_text_calls_llm_with_correct_contract(bound_tenant) -> None:
    """The EuriClient.chat call uses the task + prompt name the routing matrix knows about."""
    svc, chat_mock, upsert_mock = _make_service_with_mocks()
    await svc.extract_from_text("I am a leadership coach with 15 years of experience...")

    chat_mock.assert_awaited_once()
    kwargs = chat_mock.await_args.kwargs
    assert kwargs["task"] == "trainer_extraction"
    assert kwargs["prompt_name"] == "trainer.extraction"
    assert kwargs["tenant_id"] == bound_tenant.org_id
    assert kwargs["request_id"] == bound_tenant.request_id
    assert kwargs["agent"] == "trainer_intel_service"
    assert "content" in kwargs["prompt_inputs"]

    upsert_mock.assert_awaited_once()
    upsert_kwargs = upsert_mock.await_args.kwargs
    assert upsert_kwargs["workspace_id"] == bound_tenant.workspace_id
    assert upsert_kwargs["fields"]["niche"].startswith("Leadership")
    assert upsert_kwargs["extraction_metadata"]["source"] == "pasted_text"


@pytest.mark.asyncio
async def test_extract_from_text_blocks_when_locked(bound_tenant) -> None:
    """A locked profile cannot be re-extracted — surfaces ConflictError."""
    locked = _fake_profile(is_locked=True)
    svc, chat_mock, upsert_mock = _make_service_with_mocks(existing_profile=locked)

    with pytest.raises(ConflictError, match="locked"):
        await svc.extract_from_text("new bio content...")

    chat_mock.assert_not_awaited()
    upsert_mock.assert_not_awaited()


# ── update_profile / lock_profile ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_profile_missing_raises_not_found(bound_tenant) -> None:
    svc, _, _ = _make_service_with_mocks(existing_profile=None)
    with pytest.raises(NotFoundError):
        await svc.update_profile(TrainerProfileUpdate(niche="x"))


@pytest.mark.asyncio
async def test_update_profile_locked_raises_conflict(bound_tenant) -> None:
    svc, _, _ = _make_service_with_mocks(existing_profile=_fake_profile(is_locked=True))
    with pytest.raises(ConflictError):
        await svc.update_profile(TrainerProfileUpdate(niche="x"))
