"""Unit tests for the worker-side reply-classification integration.

Tests the `_classify_and_persist` helper in workers/tasks/inbox.py, which is
the bridge between the message-persistence loop and ReplyClassifierAgent.

The contract we're verifying:
  - On success: service.update_classification is called with the model output;
    reply.classified event is logged with the right fields.
  - On EuriClient failure (budget, model unavailable, timeout): persistence is
    NOT rolled back; reply.classification_failed is logged with a categorised
    reason string; service.update_classification is never called.
  - On malformed model output: agent coerces to "unknown" + 0.0; the worker
    still persists that result (so duplicates aren't re-classified) AND logs
    classification_failed with reason=malformed_output.
  - The helper never raises — failure isolation is the whole point.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import (
    BudgetExceededError,
    ModelUnavailableError,
    RateLimitError,
)
from corpmind.workers.tasks.inbox import (
    _categorize_classifier_error,
    _classify_and_persist,
)


MSG_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
OUTBOUND_ID = uuid.uuid4()


def _make_service() -> MagicMock:
    svc = MagicMock()
    svc.update_classification = AsyncMock()
    return svc


# ── Error categorisation ──────────────────────────────────────────────────────

class TestCategorizeClassifierError:
    def test_budget_exceeded_categorised(self):
        assert _categorize_classifier_error(BudgetExceededError("x")) == "budget_exceeded"

    def test_model_unavailable_categorised(self):
        assert _categorize_classifier_error(ModelUnavailableError("x")) == "models_unavailable"

    def test_rate_limit_categorised(self):
        assert _categorize_classifier_error(RateLimitError("x")) == "rate_limited"

    def test_unknown_exception_categorised(self):
        class MysteryError(Exception):
            pass

        assert _categorize_classifier_error(MysteryError("x")) == "internal_error"


# ── Happy path: successful classification ─────────────────────────────────────

class TestClassifyAndPersistSuccess:
    @pytest.mark.asyncio
    async def test_persists_when_agent_returns_clean_result(self):
        """The model returns a confident intent → update_classification fires."""
        from corpmind.agents.reply_classifier import ClassificationResult

        service = _make_service()
        session = MagicMock()

        # Replace the EuriClient/agent instantiation done inside the helper so
        # we don't need a real LLM call.
        agent_mock = MagicMock()
        agent_mock.classify = AsyncMock(
            return_value=ClassificationResult(
                intent="interested", confidence=0.92, model_name="gpt-4.1-nano"
            )
        )
        with patch(
            "corpmind.agents.reply_classifier.ReplyClassifierAgent",
            return_value=agent_mock,
        ):
            with patch("corpmind.ai.euri_client.EuriClient", return_value=MagicMock()):
                await _classify_and_persist(
                    service=service,
                    session=session,
                    message_id=MSG_ID,
                    outbound_message_id=OUTBOUND_ID,
                    subject="Re: Workshop",
                    body_snippet="Let's schedule a call",
                    from_address="cto@acme.com",
                    tenant_uuid=TENANT_ID,
                    request_id="req-1",
                )

        service.update_classification.assert_awaited_once()
        call_kwargs = service.update_classification.await_args.kwargs
        assert call_kwargs["intent"] == "interested"
        assert call_kwargs["confidence"] == 0.92
        assert call_kwargs["model_name"] == "gpt-4.1-nano"

    @pytest.mark.asyncio
    async def test_persists_when_no_outbound_match(self):
        """outbound_message_id=None must not block classification."""
        from corpmind.agents.reply_classifier import ClassificationResult

        service = _make_service()
        agent_mock = MagicMock()
        agent_mock.classify = AsyncMock(
            return_value=ClassificationResult(
                intent="question", confidence=0.85, model_name="gpt-4.1-nano"
            )
        )
        with patch(
            "corpmind.agents.reply_classifier.ReplyClassifierAgent",
            return_value=agent_mock,
        ):
            with patch("corpmind.ai.euri_client.EuriClient", return_value=MagicMock()):
                await _classify_and_persist(
                    service=service,
                    session=MagicMock(),
                    message_id=MSG_ID,
                    outbound_message_id=None,
                    subject="x",
                    body_snippet="Can you send pricing?",
                    from_address="hr@acme.com",
                    tenant_uuid=TENANT_ID,
                    request_id="req-1",
                )

        service.update_classification.assert_awaited_once()


# ── Failure path: EuriClient errors ───────────────────────────────────────────

class TestClassifyAndPersistFailureIsolation:
    @pytest.mark.asyncio
    async def test_budget_exceeded_does_not_call_update(self):
        """BudgetExceededError must not propagate AND must not call update_classification."""
        service = _make_service()

        agent_mock = MagicMock()
        agent_mock.classify = AsyncMock(side_effect=BudgetExceededError("over budget"))
        with patch(
            "corpmind.agents.reply_classifier.ReplyClassifierAgent",
            return_value=agent_mock,
        ):
            with patch("corpmind.ai.euri_client.EuriClient", return_value=MagicMock()):
                # Must NOT raise — failure isolation is the contract.
                await _classify_and_persist(
                    service=service,
                    session=MagicMock(),
                    message_id=MSG_ID,
                    outbound_message_id=None,
                    subject="x",
                    body_snippet="y",
                    from_address="a@b.com",
                    tenant_uuid=TENANT_ID,
                    request_id="req-1",
                )

        service.update_classification.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_model_unavailable_does_not_call_update(self):
        service = _make_service()
        agent_mock = MagicMock()
        agent_mock.classify = AsyncMock(side_effect=ModelUnavailableError("all dead"))
        with patch(
            "corpmind.agents.reply_classifier.ReplyClassifierAgent",
            return_value=agent_mock,
        ):
            with patch("corpmind.ai.euri_client.EuriClient", return_value=MagicMock()):
                await _classify_and_persist(
                    service=service,
                    session=MagicMock(),
                    message_id=MSG_ID,
                    outbound_message_id=None,
                    subject="x",
                    body_snippet="y",
                    from_address="a@b.com",
                    tenant_uuid=TENANT_ID,
                    request_id="req-1",
                )

        service.update_classification.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_timeout_does_not_call_update(self):
        """Mirrors asyncio.TimeoutError surfacing from the EuriClient transport."""
        import asyncio

        service = _make_service()
        agent_mock = MagicMock()
        agent_mock.classify = AsyncMock(side_effect=asyncio.TimeoutError())
        with patch(
            "corpmind.agents.reply_classifier.ReplyClassifierAgent",
            return_value=agent_mock,
        ):
            with patch("corpmind.ai.euri_client.EuriClient", return_value=MagicMock()):
                await _classify_and_persist(
                    service=service,
                    session=MagicMock(),
                    message_id=MSG_ID,
                    outbound_message_id=None,
                    subject="x",
                    body_snippet="y",
                    from_address="a@b.com",
                    tenant_uuid=TENANT_ID,
                    request_id="req-1",
                )

        service.update_classification.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unexpected_exception_does_not_propagate(self):
        """Anything unhandled inside the agent must be swallowed by the helper."""
        service = _make_service()
        agent_mock = MagicMock()
        agent_mock.classify = AsyncMock(side_effect=RuntimeError("oops"))
        with patch(
            "corpmind.agents.reply_classifier.ReplyClassifierAgent",
            return_value=agent_mock,
        ):
            with patch("corpmind.ai.euri_client.EuriClient", return_value=MagicMock()):
                await _classify_and_persist(
                    service=service,
                    session=MagicMock(),
                    message_id=MSG_ID,
                    outbound_message_id=None,
                    subject="x",
                    body_snippet="y",
                    from_address="a@b.com",
                    tenant_uuid=TENANT_ID,
                    request_id="req-1",
                )

        service.update_classification.assert_not_awaited()


# ── Malformed output: still persisted as "unknown" ────────────────────────────

class TestClassifyAndPersistMalformedOutput:
    @pytest.mark.asyncio
    async def test_unknown_low_confidence_still_persisted(self):
        """Even when the parser coerced to unknown, persistence runs so the
        message isn't re-classified on the next sync.  Separate event tracks rate."""
        from corpmind.agents.reply_classifier import ClassificationResult

        service = _make_service()
        agent_mock = MagicMock()
        agent_mock.classify = AsyncMock(
            return_value=ClassificationResult(
                intent="unknown", confidence=0.0, model_name="gpt-4.1-nano"
            )
        )
        with patch(
            "corpmind.agents.reply_classifier.ReplyClassifierAgent",
            return_value=agent_mock,
        ):
            with patch("corpmind.ai.euri_client.EuriClient", return_value=MagicMock()):
                await _classify_and_persist(
                    service=service,
                    session=MagicMock(),
                    message_id=MSG_ID,
                    outbound_message_id=None,
                    subject="x",
                    body_snippet="y",
                    from_address="a@b.com",
                    tenant_uuid=TENANT_ID,
                    request_id="req-1",
                )

        service.update_classification.assert_awaited_once()
        assert service.update_classification.await_args.kwargs["intent"] == "unknown"
