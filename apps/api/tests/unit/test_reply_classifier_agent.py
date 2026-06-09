"""Unit tests for ReplyClassifierAgent — pure logic, no DB, mocked EuriClient.

Covers:
  - The seven canonical intent labels round-trip from model output to ClassificationResult.
  - Parser robustness: missing key, malformed JSON, prose-wrapped JSON, out-of-range
    confidence, unrecognised label.
  - classify() propagates underlying EuriClient errors (worker is responsible
    for catching them) and never raises on parse failure.
  - LangGraph wiring: build_graph() compiles and the entry node runs.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from corpmind.agents.reply_classifier import (
    ClassificationResult,
    ReplyClassifierAgent,
    _parse_model_output,
)
from corpmind.core.exceptions import BudgetExceededError, ModelUnavailableError


# ── Parser unit tests ─────────────────────────────────────────────────────────

class TestParseModelOutput:
    def test_clean_json_interested(self):
        result = _parse_model_output(
            '{"intent": "interested", "confidence": 0.92}', "gpt-4.1-nano"
        )
        assert result.intent == "interested"
        assert result.confidence == 0.92
        assert result.model_name == "gpt-4.1-nano"

    def test_clean_json_not_interested(self):
        result = _parse_model_output(
            '{"intent": "not_interested", "confidence": 0.88}', "gpt-4.1-nano"
        )
        assert result.intent == "not_interested"

    def test_clean_json_question(self):
        result = _parse_model_output(
            '{"intent": "question", "confidence": 0.7}', "gpt-4.1-nano"
        )
        assert result.intent == "question"

    def test_clean_json_out_of_office(self):
        result = _parse_model_output(
            '{"intent": "out_of_office", "confidence": 0.95}', "gpt-4.1-nano"
        )
        assert result.intent == "out_of_office"

    def test_clean_json_bounce(self):
        result = _parse_model_output(
            '{"intent": "bounce", "confidence": 0.99}', "gpt-4.1-nano"
        )
        assert result.intent == "bounce"

    def test_clean_json_auto_reply(self):
        result = _parse_model_output(
            '{"intent": "auto_reply", "confidence": 0.86}', "gpt-4.1-nano"
        )
        assert result.intent == "auto_reply"

    def test_clean_json_unknown(self):
        result = _parse_model_output(
            '{"intent": "unknown", "confidence": 0.4}', "gpt-4.1-nano"
        )
        assert result.intent == "unknown"

    def test_unrecognised_label_coerced_to_unknown(self):
        """Model invents a label outside the allowlist — must coerce safely."""
        result = _parse_model_output(
            '{"intent": "very_interested", "confidence": 0.9}', "gpt-4.1-nano"
        )
        assert result.intent == "unknown"

    def test_label_case_insensitive(self):
        result = _parse_model_output(
            '{"intent": "INTERESTED", "confidence": 0.9}', "gpt-4.1-nano"
        )
        assert result.intent == "interested"

    def test_label_whitespace_stripped(self):
        result = _parse_model_output(
            '{"intent": "  question  ", "confidence": 0.9}', "gpt-4.1-nano"
        )
        assert result.intent == "question"

    def test_confidence_above_one_clamped(self):
        result = _parse_model_output(
            '{"intent": "interested", "confidence": 1.5}', "gpt-4.1-nano"
        )
        assert result.confidence == 1.0

    def test_confidence_below_zero_clamped(self):
        result = _parse_model_output(
            '{"intent": "interested", "confidence": -0.2}', "gpt-4.1-nano"
        )
        assert result.confidence == 0.0

    def test_missing_confidence_defaults_to_zero(self):
        result = _parse_model_output(
            '{"intent": "interested"}', "gpt-4.1-nano"
        )
        assert result.confidence == 0.0

    def test_string_confidence_parsed(self):
        result = _parse_model_output(
            '{"intent": "interested", "confidence": "0.75"}', "gpt-4.1-nano"
        )
        assert result.confidence == 0.75

    def test_non_numeric_confidence_falls_back(self):
        result = _parse_model_output(
            '{"intent": "interested", "confidence": "high"}', "gpt-4.1-nano"
        )
        assert result.confidence == 0.0

    def test_prose_wrapped_json_extracted(self):
        """Model violates the no-prose rule — parser still recovers."""
        result = _parse_model_output(
            'Here is the answer: {"intent": "question", "confidence": 0.8} — done.',
            "gpt-4.1-nano",
        )
        assert result.intent == "question"
        assert result.confidence == 0.8

    def test_markdown_fenced_json_extracted(self):
        result = _parse_model_output(
            '```json\n{"intent": "interested", "confidence": 0.9}\n```',
            "gpt-4.1-nano",
        )
        assert result.intent == "interested"

    def test_completely_malformed_falls_back_to_unknown(self):
        result = _parse_model_output("not json at all", "gpt-4.1-nano")
        assert result.intent == "unknown"
        assert result.confidence == 0.0

    def test_empty_string_falls_back_to_unknown(self):
        result = _parse_model_output("", "gpt-4.1-nano")
        assert result.intent == "unknown"
        assert result.confidence == 0.0

    def test_broken_json_falls_back_to_unknown(self):
        result = _parse_model_output(
            '{"intent": "interested", "confidence":', "gpt-4.1-nano"
        )
        assert result.intent == "unknown"

    def test_non_dict_json_falls_back_to_unknown(self):
        result = _parse_model_output('["interested", 0.9]', "gpt-4.1-nano")
        assert result.intent == "unknown"

    def test_model_name_always_preserved_on_fallback(self):
        """Even on parse failure the model name must round-trip for attribution."""
        result = _parse_model_output("garbage", "claude-haiku-4-5")
        assert result.model_name == "claude-haiku-4-5"


# ── classify() integration with mocked EuriClient ─────────────────────────────

def _make_agent(content: str, model: str = "gpt-4.1-nano") -> ReplyClassifierAgent:
    """Build an agent whose EuriClient returns a fixed response."""
    euri = AsyncMock()
    euri.chat.return_value = {"content": content, "model": model}
    return ReplyClassifierAgent(euri)


class TestClassifyHappyPath:
    """End-to-end happy-path tests for each canonical intent."""

    @pytest.mark.asyncio
    async def test_interested(self):
        agent = _make_agent('{"intent": "interested", "confidence": 0.92}')
        result = await agent.classify(
            subject="Re: Workshop",
            body_snippet="Let's schedule a call",
            from_address="cto@acme.com",
            campaign_context=None,
            tenant_id=uuid.uuid4(),
            request_id="req-1",
        )
        assert result.intent == "interested"
        assert result.confidence == 0.92

    @pytest.mark.asyncio
    async def test_not_interested(self):
        agent = _make_agent('{"intent": "not_interested", "confidence": 0.95}')
        result = await agent.classify(
            subject="Re: Workshop",
            body_snippet="Not interested, please remove me.",
            from_address="cto@acme.com",
            campaign_context=None,
            tenant_id=uuid.uuid4(),
            request_id="req-1",
        )
        assert result.intent == "not_interested"

    @pytest.mark.asyncio
    async def test_question(self):
        agent = _make_agent('{"intent": "question", "confidence": 0.85}')
        result = await agent.classify(
            subject="Re: Workshop",
            body_snippet="Can you send pricing?",
            from_address="cto@acme.com",
            campaign_context=None,
            tenant_id=uuid.uuid4(),
            request_id="req-1",
        )
        assert result.intent == "question"

    @pytest.mark.asyncio
    async def test_out_of_office(self):
        agent = _make_agent('{"intent": "out_of_office", "confidence": 0.97}')
        result = await agent.classify(
            subject="Out of office",
            body_snippet="I am out until Monday",
            from_address="cto@acme.com",
            campaign_context=None,
            tenant_id=uuid.uuid4(),
            request_id="req-1",
        )
        assert result.intent == "out_of_office"

    @pytest.mark.asyncio
    async def test_bounce(self):
        agent = _make_agent('{"intent": "bounce", "confidence": 0.99}')
        result = await agent.classify(
            subject="Delivery Status Notification",
            body_snippet="Mailbox unavailable",
            from_address="MAILER-DAEMON@gmail.com",
            campaign_context=None,
            tenant_id=uuid.uuid4(),
            request_id="req-1",
        )
        assert result.intent == "bounce"

    @pytest.mark.asyncio
    async def test_auto_reply(self):
        agent = _make_agent('{"intent": "auto_reply", "confidence": 0.9}')
        result = await agent.classify(
            subject="Automatic reply",
            body_snippet="Thank you for your message",
            from_address="cto@acme.com",
            campaign_context=None,
            tenant_id=uuid.uuid4(),
            request_id="req-1",
        )
        assert result.intent == "auto_reply"

    @pytest.mark.asyncio
    async def test_unknown(self):
        agent = _make_agent('{"intent": "unknown", "confidence": 0.3}')
        result = await agent.classify(
            subject="???",
            body_snippet="hmm",
            from_address="cto@acme.com",
            campaign_context=None,
            tenant_id=uuid.uuid4(),
            request_id="req-1",
        )
        assert result.intent == "unknown"


class TestClassifyEdgeCases:
    @pytest.mark.asyncio
    async def test_malformed_output_coerces_to_unknown_without_raising(self):
        agent = _make_agent("model said something weird")
        result = await agent.classify(
            subject="x",
            body_snippet="y",
            from_address="a@b.com",
            campaign_context=None,
            tenant_id=uuid.uuid4(),
            request_id="req-1",
        )
        assert result.intent == "unknown"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_budget_exceeded_propagates(self):
        """Worker is responsible for catching this — agent must not swallow."""
        euri = AsyncMock()
        euri.chat.side_effect = BudgetExceededError("nope")
        agent = ReplyClassifierAgent(euri)
        with pytest.raises(BudgetExceededError):
            await agent.classify(
                subject="x",
                body_snippet="y",
                from_address="a@b.com",
                campaign_context=None,
                tenant_id=uuid.uuid4(),
                request_id="req-1",
            )

    @pytest.mark.asyncio
    async def test_model_unavailable_propagates(self):
        euri = AsyncMock()
        euri.chat.side_effect = ModelUnavailableError("all models exhausted")
        agent = ReplyClassifierAgent(euri)
        with pytest.raises(ModelUnavailableError):
            await agent.classify(
                subject="x",
                body_snippet="y",
                from_address="a@b.com",
                campaign_context=None,
                tenant_id=uuid.uuid4(),
                request_id="req-1",
            )

    @pytest.mark.asyncio
    async def test_body_snippet_truncated_to_500_chars(self):
        """Defends against accidentally sending full bodies past the snippet cap."""
        euri = AsyncMock()
        euri.chat.return_value = {
            "content": '{"intent": "unknown", "confidence": 0.1}',
            "model": "gpt-4.1-nano",
        }
        agent = ReplyClassifierAgent(euri)
        long_body = "A" * 2000
        await agent.classify(
            subject="x",
            body_snippet=long_body,
            from_address="a@b.com",
            campaign_context=None,
            tenant_id=uuid.uuid4(),
            request_id="req-1",
        )
        # Inspect the actual prompt_inputs the agent passed to EuriClient.
        call_kwargs = euri.chat.await_args.kwargs
        assert len(call_kwargs["prompt_inputs"]["body_snippet"]) == 500

    @pytest.mark.asyncio
    async def test_none_subject_normalised_to_empty(self):
        agent = _make_agent('{"intent": "unknown", "confidence": 0.1}')
        await agent.classify(
            subject=None,
            body_snippet=None,
            from_address="a@b.com",
            campaign_context=None,
            tenant_id=uuid.uuid4(),
            request_id="req-1",
        )
        # No raise = success; the agent must accept None for both.


# ── LangGraph wiring smoke test ───────────────────────────────────────────────

class TestAgentGraphWiring:
    def test_build_graph_returns_state_graph(self):
        from langgraph.graph import StateGraph

        agent = ReplyClassifierAgent(AsyncMock())
        graph = agent.build_graph()
        assert isinstance(graph, StateGraph)

    def test_build_graph_compiles(self):
        agent = ReplyClassifierAgent(AsyncMock())
        compiled = agent.build_graph().compile()
        assert compiled is not None

    def test_name_attribute(self):
        agent = ReplyClassifierAgent(AsyncMock())
        assert agent.name == "ReplyClassifierAgent"


# ── ClassificationResult schema ───────────────────────────────────────────────

class TestClassificationResultSchema:
    def test_rejects_invalid_intent(self):
        with pytest.raises(Exception):
            ClassificationResult(intent="bogus", confidence=0.5, model_name="x")  # type: ignore[arg-type]

    def test_rejects_confidence_above_one(self):
        with pytest.raises(Exception):
            ClassificationResult(intent="interested", confidence=1.5, model_name="x")

    def test_rejects_confidence_below_zero(self):
        with pytest.raises(Exception):
            ClassificationResult(intent="interested", confidence=-0.1, model_name="x")

    def test_accepts_boundary_values(self):
        ClassificationResult(intent="interested", confidence=0.0, model_name="x")
        ClassificationResult(intent="interested", confidence=1.0, model_name="x")
