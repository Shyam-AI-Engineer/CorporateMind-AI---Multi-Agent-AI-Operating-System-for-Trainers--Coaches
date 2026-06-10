"""Unit tests for OutreachService.generate_followup (Sprint 8A, ADR-0008).

Mocks the DB session, EuriClient, and compliance so tests run with no Postgres
or LLM provider.  Focus areas (per the Sprint 8A brief):
  • prompt routing        — task_type → (task class, prompt_name)
  • context building      — _build_followup_inputs slots + safe fallbacks
  • needs_human_review    — fail-safe behaviour for question follow-ups
  • draft creation        — status/channel/prompt_version + persistence + commit

The cold path (generate_message / _parse_copy) is intentionally not touched by
this suite — it has its own coverage in test_outreach_service.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import (
    NotFoundError,
    OptInRequiredError,
    ValidationError,
)
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.compliance.schemas import ComplianceCheckResult, ComplianceOutcome
from corpmind.modules.outreach.schemas import GenerateFollowupRequest
from corpmind.modules.outreach.service import OutreachService, _build_followup_inputs

# ── Shared fixtures ─────────────────────────────────────────────────────────────

_ORG_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_CONTACT_ID = uuid.uuid4()
_MESSAGE_ID = uuid.uuid4()

_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="trainer",
    request_id="req-followup-001",
)

_CONTACT_ROW = {
    "id": _CONTACT_ID,
    "full_name": "Priya Sharma",
    "title": "VP-HR",
    "email": "priya@hdfc.example",
    "is_contactable": True,
    "preferred_language": "en",
    "company_name": "HDFC Life Insurance",
    "industry": "Insurance",
}

_TRAINER_ROW = {
    "niche": "Leadership Development",
    "topics": ["leadership", "coaching"],
    "tone": "semi_formal",
    "pricing_min_inr": 50000,
    "pricing_max_inr": 150000,
    "bio": "10 years in L&D.",
    "usp": "Cuts promotion-readiness time by 6 months.",
    "target_industries": ["Insurance", "BFSI"],
}

_ALLOWED = ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)
_BLOCKED_OPT_IN = ComplianceCheckResult(
    outcome=ComplianceOutcome.BLOCKED,
    reason="Contact has no current opt-in",
    blocked_by="opt_in",
)

# LLM outputs
_Q_ANSWERED = json.dumps({
    "subject": "Re: Building HDFC Life's leadership bench",
    "body": "Hi Priya, yes — first-time-manager transitions are a core part of the "
            "leadership track I run, covering delegation and difficult conversations. "
            "Happy to walk you through how I'd shape it for your AVP cohort. Would 15 "
            "minutes this week work?",
    "answered": True,
    "needs_human_review": False,
    "language_used": "en",
})
_Q_DEFER = json.dumps({
    "subject": "Re: Building HDFC Life's leadership bench",
    "body": "Great question — let me confirm exact pricing for that format and revert.",
    "answered": False,
    "needs_human_review": True,
    "language_used": "en",
})
_Q_MISSING_FLAG = json.dumps({
    "subject": "Re: Building HDFC Life's leadership bench",
    "body": "Yes, I cover that.",
    "answered": True,
    "language_used": "en",
})  # needs_human_review absent → must fail safe to True
_NUDGE_OK = json.dumps({
    "subject": "Re: Building HDFC Life's leadership bench",
    "body": "Hi Priya, I caught your out-of-office a couple of weeks back — hope you "
            "had a good break. I'd dropped a note about accelerating promotion-readiness "
            "for your AVP cohort. No urgency, but if it's still relevant I'd love 15 "
            "minutes. Would later this week suit you?",
    "language_used": "en",
})


def _make_session(contact_row=_CONTACT_ROW, trainer_row=_TRAINER_ROW):
    """Mock AsyncSession: first execute() → contact mapping, then → trainer mapping."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    def _make_mapping_result(row_dict):
        mapping_result = MagicMock()
        mapping_result.mappings.return_value.one_or_none.return_value = (
            row_dict if row_dict else None
        )
        return mapping_result

    call_index = {"n": 0}

    async def _execute(stmt, params=None):
        n = call_index["n"]
        call_index["n"] += 1
        return _make_mapping_result(contact_row if n == 0 else trainer_row)

    session.execute = _execute
    return session


def _svc_with_stubbed_create(session) -> OutreachService:
    svc = OutreachService(session)

    async def _create(msg):
        msg.id = _MESSAGE_ID
        msg.created_at = datetime.now(UTC)
        return msg

    svc._repo.create = _create  # type: ignore[method-assign]
    svc._session.commit = AsyncMock()
    return svc


def _req(task_type: str, **kwargs) -> GenerateFollowupRequest:
    base = dict(
        contact_id=_CONTACT_ID,
        task_type=task_type,
        reply_text="Do you cover first-time managers?",
        original_subject="Building HDFC Life's leadership bench",
        original_body="Hi Priya, I help HR teams accelerate promotion-readiness.",
        lead_stage="engaged",
    )
    base.update(kwargs)
    return GenerateFollowupRequest(**base)


def _patch_llm(content: str):
    return patch(
        "corpmind.modules.outreach.service.EuriClient.chat",
        new_callable=AsyncMock,
        return_value={"content": content},
    )


def _patch_opt_in(result=_ALLOWED):
    return patch(
        "corpmind.modules.outreach.service.ComplianceService.check_opt_in",
        new_callable=AsyncMock,
        return_value=result,
    )


# ── Prompt routing ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_question_routes_to_question_task_and_prompt():
    """question_followup → task='followup_question', prompt='outreach.followup.question'."""
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    with _patch_opt_in(), _patch_llm(_Q_ANSWERED) as mock_chat:
        await svc.generate_followup(_req("question_followup"))

    clear_tenant_context(token)

    kwargs = mock_chat.await_args.kwargs
    assert kwargs["task"] == "followup_question"
    assert kwargs["prompt_name"] == "outreach.followup.question"
    assert kwargs["agent"] == "outreach_followup_service"


@pytest.mark.asyncio
async def test_nudge_routes_to_nudge_task_and_prompt():
    """out_of_office_followup → task='followup_nudge', prompt='outreach.followup.nudge'."""
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    with _patch_opt_in(), _patch_llm(_NUDGE_OK) as mock_chat:
        await svc.generate_followup(_req("out_of_office_followup", days_since=14))

    clear_tenant_context(token)

    kwargs = mock_chat.await_args.kwargs
    assert kwargs["task"] == "followup_nudge"
    assert kwargs["prompt_name"] == "outreach.followup.nudge"


@pytest.mark.asyncio
async def test_unknown_task_type_raises_validation_error():
    """A task_type that bypasses schema validation hits the defensive guard."""
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    # model_construct bypasses the pydantic pattern constraint.
    bogus = GenerateFollowupRequest.model_construct(
        contact_id=_CONTACT_ID, task_type="not_a_real_type"
    )

    with pytest.raises(ValidationError, match="Unknown follow-up task type"):
        await svc.generate_followup(bogus)

    clear_tenant_context(token)


# ── Context building ──────────────────────────────────────────────────────────

def test_build_followup_inputs_includes_all_context_keys():
    """Every placeholder the prompts reference is present in the inputs dict."""
    req = _req("question_followup", days_since=7)
    inputs = _build_followup_inputs(req, _CONTACT_ROW, _TRAINER_ROW)

    # follow-up-specific keys
    for key in ("reply_text", "original_subject", "original_body", "lead_stage", "days_since"):
        assert key in inputs
    # inherited trainer/contact block
    for key in ("trainer_niche", "trainer_pricing", "contact_name", "contact_language"):
        assert key in inputs

    assert inputs["reply_text"] == "Do you cover first-time managers?"
    assert inputs["lead_stage"] == "engaged"
    assert inputs["days_since"] == "7"


def test_build_followup_inputs_uses_safe_placeholders_for_missing_context():
    """None context fields become explicit placeholders, never literal braces."""
    req = GenerateFollowupRequest(contact_id=_CONTACT_ID, task_type="question_followup")
    inputs = _build_followup_inputs(req, _CONTACT_ROW, _TRAINER_ROW)

    assert inputs["reply_text"] == "(no reply text available)"
    assert inputs["original_subject"] == "(original subject unavailable)"
    assert inputs["original_body"] == "(original email body unavailable)"
    assert inputs["lead_stage"] == "unknown"
    assert inputs["days_since"] == "a few"  # None days_since fallback


# ── needs_human_review behaviour ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_question_answered_does_not_need_review():
    """answered=true + needs_human_review=false → auto-eligible signal."""
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    with _patch_opt_in(), _patch_llm(_Q_ANSWERED):
        out = await svc.generate_followup(_req("question_followup"))

    clear_tenant_context(token)
    assert out.needs_human_review is False
    assert out.answered is True


@pytest.mark.asyncio
async def test_question_deferred_needs_review():
    """answered=false + needs_human_review=true → routed to human."""
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    with _patch_opt_in(), _patch_llm(_Q_DEFER):
        out = await svc.generate_followup(_req("question_followup"))

    clear_tenant_context(token)
    assert out.needs_human_review is True
    assert out.answered is False


@pytest.mark.asyncio
async def test_question_missing_flag_fails_safe_to_review():
    """Absent needs_human_review flag must default to True (fail-safe)."""
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    with _patch_opt_in(), _patch_llm(_Q_MISSING_FLAG):
        out = await svc.generate_followup(_req("question_followup"))

    clear_tenant_context(token)
    assert out.needs_human_review is True


@pytest.mark.asyncio
async def test_question_answered_false_forces_review_even_if_flag_false():
    """If the model claims answered=false but needs_human_review=false, we override to True."""
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    contradictory = json.dumps({
        "subject": "Re: x",
        "body": "Let me get back to you.",
        "answered": False,
        "needs_human_review": False,
        "language_used": "en",
    })

    with _patch_opt_in(), _patch_llm(contradictory):
        out = await svc.generate_followup(_req("question_followup"))

    clear_tenant_context(token)
    assert out.needs_human_review is True
    assert out.answered is False


@pytest.mark.asyncio
async def test_nudge_never_needs_review_and_answered_is_none():
    """Nudge drafts carry no question, so answered is None and review is False."""
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    with _patch_opt_in(), _patch_llm(_NUDGE_OK):
        out = await svc.generate_followup(_req("out_of_office_followup", days_since=10))

    clear_tenant_context(token)
    assert out.needs_human_review is False
    assert out.answered is None


# ── Draft creation ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_draft_created_with_expected_fields():
    """Persisted draft is email/draft with the follow-up prompt_version and parsed copy."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = _svc_with_stubbed_create(session)

    with _patch_opt_in(), _patch_llm(_Q_ANSWERED):
        out = await svc.generate_followup(_req("question_followup"))

    clear_tenant_context(token)

    msg = out.message
    assert msg.status == "draft"
    assert msg.channel == "email"
    assert msg.contact_id == _CONTACT_ID
    assert msg.prompt_version == "outreach.followup.question.v1"
    assert msg.subject == "Re: Building HDFC Life's leadership bench"
    assert msg.body.startswith("Hi Priya")
    svc._session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_nudge_draft_uses_nudge_prompt_version():
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    with _patch_opt_in(), _patch_llm(_NUDGE_OK):
        out = await svc.generate_followup(_req("out_of_office_followup", days_since=14))

    clear_tenant_context(token)
    assert out.message.prompt_version == "outreach.followup.nudge.v1"


@pytest.mark.asyncio
async def test_contact_not_found_raises():
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session(contact_row=None))

    with pytest.raises(NotFoundError):
        await svc.generate_followup(_req("question_followup"))

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_opt_in_blocked_raises_before_llm_call():
    """Opt-in fail-fast prevents the premium LLM call entirely."""
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    with _patch_opt_in(_BLOCKED_OPT_IN), _patch_llm(_Q_ANSWERED) as mock_chat:
        with pytest.raises(OptInRequiredError):
            await svc.generate_followup(_req("question_followup"))

    clear_tenant_context(token)
    mock_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_json_raises_validation_error():
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    with _patch_opt_in(), _patch_llm("Sure! Here is your follow-up: ..."):
        with pytest.raises(ValidationError, match="non-JSON"):
            await svc.generate_followup(_req("question_followup"))

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_nudge_empty_body_raises_validation_error():
    """A nudge with an empty body is invalid (no human-review fallback for nudges)."""
    token = set_tenant_context(_CTX)
    svc = _svc_with_stubbed_create(_make_session())

    empty_body = json.dumps({"subject": "Re: x", "body": "", "language_used": "en"})

    with _patch_opt_in(), _patch_llm(empty_body):
        with pytest.raises(ValidationError, match="body"):
            await svc.generate_followup(_req("out_of_office_followup", days_since=5))

    clear_tenant_context(token)
