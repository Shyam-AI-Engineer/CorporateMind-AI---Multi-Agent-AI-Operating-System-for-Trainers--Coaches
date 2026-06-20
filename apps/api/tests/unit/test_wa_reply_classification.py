"""Unit tests for Sprint 17B WA reply classification.

Covers:
  ReplyClassifierAgent — WA-specific behaviour
    - classify() passes prompt_name="inbox.classify_wa_reply" to EuriClient
    - 'unsubscribe' intent parses and round-trips correctly through ClassificationResult
    - WA intents (no 'bounce', no 'auto_reply') parse cleanly
    - WA prompt-name kwarg is forwarded; email callers still use default prompt
  _parse_model_output (inherited)
    - 'unsubscribe' is in the allowlist and returns correct ClassificationResult
    - WA-only intents round-trip; email-only intents still parse (allowlist is a superset)
  _classify_wa_and_persist helper
    - calls agent.classify with prompt_name=_WA_CLASSIFY_PROMPT (no subject)
    - calls service.update_classification on success
    - swallows EuriClient errors (best-effort)
    - does not call automation when intent='unknown' + confidence<0.5
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.agents.reply_classifier import (
    ReplyClassifierAgent,
    _parse_model_output,
)
from corpmind.workers.tasks.whatsapp_inbox import (
    _classify_wa_and_persist,
    _WA_CLASSIFY_PROMPT,
)


TENANT_ID = uuid.uuid4()
MESSAGE_ID = uuid.uuid4()


# ── Parser: unsubscribe intent ────────────────────────────────────────────────

class TestParseUnsubscribeIntent:
    def test_unsubscribe_stop_keyword(self):
        result = _parse_model_output(
            '{"intent": "unsubscribe", "confidence": 0.99}', "gpt-4.1-nano"
        )
        assert result.intent == "unsubscribe"
        assert result.confidence == 0.99

    def test_unsubscribe_remove_me(self):
        result = _parse_model_output(
            '{"intent": "unsubscribe", "confidence": 0.97}', "claude-haiku-4-5"
        )
        assert result.intent == "unsubscribe"
        assert result.model_name == "claude-haiku-4-5"

    def test_unsubscribe_high_confidence(self):
        result = _parse_model_output(
            '{"intent": "unsubscribe", "confidence": 1.0}', "gpt-4.1-nano"
        )
        assert result.intent == "unsubscribe"
        assert result.confidence == 1.0

    def test_wa_interested_no_subject(self):
        """WA 'interested' intent works even though there's no subject field."""
        result = _parse_model_output(
            '{"intent": "interested", "confidence": 0.65}', "gpt-4.1-nano"
        )
        assert result.intent == "interested"
        assert 0.6 <= result.confidence <= 0.7

    def test_wa_out_of_office(self):
        result = _parse_model_output(
            '{"intent": "out_of_office", "confidence": 0.86}', "gpt-4.1-nano"
        )
        assert result.intent == "out_of_office"


# ── ReplyClassifierAgent: WA prompt routing ───────────────────────────────────

class TestReplyClassifierAgentWAPrompt:
    @pytest.mark.asyncio
    async def test_wa_classify_uses_wa_prompt_name(self):
        """classify() with prompt_name kwarg must forward it to EuriClient.chat()."""
        euri = MagicMock()
        euri.chat = AsyncMock(return_value={
            "content": '{"intent": "unsubscribe", "confidence": 0.99}',
            "model": "gpt-4.1-nano",
        })
        agent = ReplyClassifierAgent(euri)

        result = await agent.classify(
            subject=None,
            body_snippet="STOP",
            from_address="+919876543210",
            campaign_context=None,
            tenant_id=TENANT_ID,
            request_id="req-wa-001",
            prompt_name=_WA_CLASSIFY_PROMPT,
        )

        assert result.intent == "unsubscribe"
        assert result.confidence == 0.99
        # Verify the WA prompt name was passed to EuriClient
        call_kwargs = euri.chat.call_args.kwargs
        assert call_kwargs["prompt_name"] == _WA_CLASSIFY_PROMPT

    @pytest.mark.asyncio
    async def test_email_classify_uses_default_prompt(self):
        """Calling classify() without prompt_name still uses the default email prompt."""
        euri = MagicMock()
        euri.chat = AsyncMock(return_value={
            "content": '{"intent": "interested", "confidence": 0.88}',
            "model": "gpt-4.1-nano",
        })
        agent = ReplyClassifierAgent(euri)

        await agent.classify(
            subject="Re: Leadership workshop",
            body_snippet="Yes let's discuss further",
            from_address="hr@company.com",
            campaign_context=None,
            tenant_id=TENANT_ID,
            request_id="req-email-001",
            # prompt_name intentionally omitted — uses default
        )

        call_kwargs = euri.chat.call_args.kwargs
        assert call_kwargs["prompt_name"] == "inbox.classify_reply"

    @pytest.mark.asyncio
    async def test_wa_classify_returns_classification_result(self):
        """Full result shape for a WA unsubscribe classification."""
        euri = MagicMock()
        euri.chat = AsyncMock(return_value={
            "content": '{"intent": "unsubscribe", "confidence": 0.97}',
            "model": "claude-haiku-4-5",
        })
        agent = ReplyClassifierAgent(euri)

        result = await agent.classify(
            subject=None,
            body_snippet="Please remove me from your list",
            from_address="+918800112233",
            campaign_context="Campaign: Leadership Bootcamp",
            tenant_id=TENANT_ID,
            request_id="req-wa-002",
            prompt_name=_WA_CLASSIFY_PROMPT,
        )

        assert result.intent == "unsubscribe"
        assert result.confidence == 0.97
        assert result.model_name == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_wa_classify_subject_is_none(self):
        """WA messages have no subject; classify() should not include a subject field."""
        euri = MagicMock()
        euri.chat = AsyncMock(return_value={
            "content": '{"intent": "question", "confidence": 0.83}',
            "model": "gpt-4.1-nano",
        })
        agent = ReplyClassifierAgent(euri)

        await agent.classify(
            subject=None,
            body_snippet="What is the fee for one-day training?",
            from_address="+917700112233",
            campaign_context=None,
            tenant_id=TENANT_ID,
            request_id="req-wa-003",
            prompt_name=_WA_CLASSIFY_PROMPT,
        )

        prompt_inputs = euri.chat.call_args.kwargs["prompt_inputs"]
        assert prompt_inputs["subject"] == ""  # None coerced to "" in classify()


# ── _classify_wa_and_persist helper ──────────────────────────────────────────

class TestClassifyWaAndPersist:
    def _make_service(self):
        svc = MagicMock()
        svc.update_classification = AsyncMock()
        return svc

    def _make_session(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_successful_classification_updates_inbox_message(self):
        svc = self._make_service()
        session = self._make_session()

        # ReplyClassifierAgent and EuriClient are lazy-imported inside
        # _classify_wa_and_persist, so patch at source module, not whatsapp_inbox.*
        with (
            patch("corpmind.agents.reply_classifier.ReplyClassifierAgent") as mock_agent_cls,
            patch("corpmind.ai.euri_client.EuriClient"),
            patch("corpmind.workers.tasks.whatsapp_inbox._run_wa_reply_automation", AsyncMock()),
        ):
            agent_instance = MagicMock()
            agent_instance.classify = AsyncMock(return_value=MagicMock(
                intent="interested",
                confidence=0.88,
                model_name="gpt-4.1-nano",
            ))
            mock_agent_cls.return_value = agent_instance

            await _classify_wa_and_persist(
                service=svc,
                session=session,
                message_id=MESSAGE_ID,
                outbound_message_id=None,
                body_snippet="Yes, let's schedule a call",
                from_address="+919876543210",
                tenant_uuid=TENANT_ID,
                request_id="req-001",
                contact_id_override=uuid.uuid4(),
                workspace_id_override=uuid.uuid4(),
            )

        svc.update_classification.assert_awaited_once_with(
            MESSAGE_ID,
            intent="interested",
            confidence=0.88,
            model_name="gpt-4.1-nano",
        )

    @pytest.mark.asyncio
    async def test_euri_error_swallowed_no_update(self):
        """LLM failure → classification not persisted, no exception raised."""
        svc = self._make_service()
        session = self._make_session()

        with (
            patch("corpmind.agents.reply_classifier.ReplyClassifierAgent") as mock_agent_cls,
            patch("corpmind.ai.euri_client.EuriClient"),
        ):
            agent_instance = MagicMock()
            agent_instance.classify = AsyncMock(side_effect=RuntimeError("LLM down"))
            mock_agent_cls.return_value = agent_instance

            # Must not raise
            await _classify_wa_and_persist(
                service=svc,
                session=session,
                message_id=MESSAGE_ID,
                outbound_message_id=None,
                body_snippet="ok",
                from_address="+919876543210",
                tenant_uuid=TENANT_ID,
                request_id="req-002",
                contact_id_override=None,
                workspace_id_override=None,
            )

        svc.update_classification.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_low_confidence_skips_automation(self):
        """unknown intent + confidence < 0.5 → update_classification called but automation skipped."""
        svc = self._make_service()
        session = self._make_session()

        with (
            patch("corpmind.agents.reply_classifier.ReplyClassifierAgent") as mock_agent_cls,
            patch("corpmind.ai.euri_client.EuriClient"),
            patch("corpmind.workers.tasks.whatsapp_inbox._run_wa_reply_automation", AsyncMock()) as mock_auto,
        ):
            agent_instance = MagicMock()
            agent_instance.classify = AsyncMock(return_value=MagicMock(
                intent="unknown",
                confidence=0.3,
                model_name="gpt-4.1-nano",
            ))
            mock_agent_cls.return_value = agent_instance

            await _classify_wa_and_persist(
                service=svc,
                session=session,
                message_id=MESSAGE_ID,
                outbound_message_id=None,
                body_snippet="???",
                from_address="+919876543210",
                tenant_uuid=TENANT_ID,
                request_id="req-003",
                contact_id_override=None,
                workspace_id_override=None,
            )

        svc.update_classification.assert_awaited_once()
        mock_auto.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unsubscribe_intent_triggers_automation(self):
        """unsubscribe intent with high confidence → automation IS called."""
        svc = self._make_service()
        session = self._make_session()
        contact_id = uuid.uuid4()
        workspace_id = uuid.uuid4()

        with (
            patch("corpmind.agents.reply_classifier.ReplyClassifierAgent") as mock_agent_cls,
            patch("corpmind.ai.euri_client.EuriClient"),
            patch("corpmind.workers.tasks.whatsapp_inbox._run_wa_reply_automation", AsyncMock()) as mock_auto,
        ):
            agent_instance = MagicMock()
            agent_instance.classify = AsyncMock(return_value=MagicMock(
                intent="unsubscribe",
                confidence=0.99,
                model_name="gpt-4.1-nano",
            ))
            mock_agent_cls.return_value = agent_instance

            await _classify_wa_and_persist(
                service=svc,
                session=session,
                message_id=MESSAGE_ID,
                outbound_message_id=None,
                body_snippet="STOP",
                from_address="+919876543210",
                tenant_uuid=TENANT_ID,
                request_id="req-004",
                contact_id_override=contact_id,
                workspace_id_override=workspace_id,
            )

        mock_auto.assert_awaited_once()
        call_kwargs = mock_auto.call_args.kwargs
        assert call_kwargs["intent"] == "unsubscribe"
        assert call_kwargs["contact_id_override"] == contact_id
        assert call_kwargs["workspace_id_override"] == workspace_id
