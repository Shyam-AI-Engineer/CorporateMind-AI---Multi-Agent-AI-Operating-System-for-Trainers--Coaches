"""Unit tests for Sprint 17B unsubscribe CRM automation.

Covers:
  ReplyAutomationService._handle_unsubscribe()
    - issues raw SQL UPDATE clearing whatsapp_opt_in_at for the right contact
    - creates an Activity with type 'whatsapp_unsubscribed'
    - emits ContactUnsubscribed event
    - returns AutomationResult(outcome='applied')
    - idempotent: reserve=False → 'already_applied' without executing the update
  ReplyAutomationService.handle_classified() dispatch
    - intent='unsubscribe' routes to _handle_unsubscribe
    - fresh-conversation path (no outbound_message_id, contact_id_override set) works
  ContactUnsubscribed event
    - channel field is 'whatsapp'
    - source_inbox_message_id matches the inbox message
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.crm.automation import (
    ACTIVITY_WHATSAPP_UNSUBSCRIBED,
    AutomationResult,
    ReplyAutomationService,
)
from corpmind.modules.crm.events import ContactUnsubscribed


TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
CONTACT_ID = uuid.uuid4()
LEAD_ID = uuid.uuid4()
OUTBOUND_ID = uuid.uuid4()
INBOX_MSG_ID = uuid.uuid4()


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = TENANT_ID
    ctx.workspace_id = WORKSPACE_ID
    return ctx


def _lead(stage: str = "engaged") -> MagicMock:
    lead = MagicMock()
    lead.id = LEAD_ID
    lead.tenant_id = TENANT_ID
    lead.contact_id = CONTACT_ID
    lead.workspace_id = WORKSPACE_ID
    lead.stage = stage
    return lead


def _make_service(
    *,
    reserve_returns: bool = True,
    outbound_returns: tuple[uuid.UUID, uuid.UUID] | None = (CONTACT_ID, WORKSPACE_ID),
    lead_returns: MagicMock | None = None,
) -> ReplyAutomationService:
    session = MagicMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()

    svc = ReplyAutomationService(session)

    svc._log_repo = MagicMock()
    svc._log_repo.reserve = AsyncMock(return_value=reserve_returns)

    svc._activity_repo = MagicMock()
    svc._activity_repo.create = AsyncMock(side_effect=lambda a: a)

    svc._followup_repo = MagicMock()
    svc._followup_repo.create = AsyncMock(side_effect=lambda t: t)

    svc._lead_repo = MagicMock()
    svc._lead_repo.find_active_by_contact_any_workspace = AsyncMock(return_value=lead_returns)

    svc._resolve_outbound = AsyncMock(return_value=outbound_returns)

    return svc


# ── _handle_unsubscribe unit tests ────────────────────────────────────────────

class TestHandleUnsubscribe:
    @pytest.mark.asyncio
    async def test_clears_whatsapp_opt_in_at_via_sql(self):
        """Must issue raw SQL setting whatsapp_opt_in_at = NULL."""
        svc = _make_service()
        emitted: list = []

        with (
            patch("corpmind.modules.crm.automation.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.crm.automation._emit", side_effect=emitted.append),
        ):
            result = await svc._handle_unsubscribe(
                inbox_message_id=INBOX_MSG_ID,
                contact_id=CONTACT_ID,
                workspace_id=WORKSPACE_ID,
                outbound_message_id=OUTBOUND_ID,
                lead=_lead(),
            )

        # Verify the raw SQL was executed with the right params
        svc._session.execute.assert_awaited_once()
        call_args = svc._session.execute.call_args
        sql_str = str(call_args.args[0])
        assert "whatsapp_opt_in_at" in sql_str
        assert "NULL" in sql_str
        params = call_args.args[1]
        assert str(CONTACT_ID) == params["cid"]
        assert str(TENANT_ID) == params["tid"]

    @pytest.mark.asyncio
    async def test_creates_activity_with_correct_type(self):
        """Activity type must be ACTIVITY_WHATSAPP_UNSUBSCRIBED."""
        svc = _make_service()

        with (
            patch("corpmind.modules.crm.automation.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.crm.automation._emit"),
        ):
            await svc._handle_unsubscribe(
                inbox_message_id=INBOX_MSG_ID,
                contact_id=CONTACT_ID,
                workspace_id=WORKSPACE_ID,
                outbound_message_id=OUTBOUND_ID,
                lead=_lead(),
            )

        svc._activity_repo.create.assert_awaited_once()
        activity = svc._activity_repo.create.call_args.args[0]
        assert activity.type == ACTIVITY_WHATSAPP_UNSUBSCRIBED
        assert activity.contact_id == CONTACT_ID
        assert activity.source_inbox_message_id == INBOX_MSG_ID

    @pytest.mark.asyncio
    async def test_emits_contact_unsubscribed_event(self):
        """Must emit ContactUnsubscribed with channel='whatsapp'."""
        svc = _make_service()
        emitted: list = []

        with (
            patch("corpmind.modules.crm.automation.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.crm.automation._emit", side_effect=emitted.append),
        ):
            await svc._handle_unsubscribe(
                inbox_message_id=INBOX_MSG_ID,
                contact_id=CONTACT_ID,
                workspace_id=WORKSPACE_ID,
                outbound_message_id=OUTBOUND_ID,
                lead=None,  # also works with no lead
            )

        assert len(emitted) == 1
        event = emitted[0]
        assert isinstance(event, ContactUnsubscribed)
        assert event.contact_id == CONTACT_ID
        assert event.tenant_id == TENANT_ID
        assert event.channel == "whatsapp"
        assert event.source_inbox_message_id == INBOX_MSG_ID

    @pytest.mark.asyncio
    async def test_returns_applied_outcome(self):
        svc = _make_service()

        with (
            patch("corpmind.modules.crm.automation.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.crm.automation._emit"),
        ):
            result = await svc._handle_unsubscribe(
                inbox_message_id=INBOX_MSG_ID,
                contact_id=CONTACT_ID,
                workspace_id=WORKSPACE_ID,
                outbound_message_id=None,
                lead=None,
            )

        assert isinstance(result, AutomationResult)
        assert result.outcome == "applied"

    @pytest.mark.asyncio
    async def test_idempotent_already_applied(self):
        """Second call with same inbox_message_id → 'already_applied', no SQL."""
        svc = _make_service(reserve_returns=False)  # reserve returns False → already logged

        with (
            patch("corpmind.modules.crm.automation.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.crm.automation._emit"),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="unsubscribe",
                outbound_message_id=OUTBOUND_ID,
            )

        assert result.outcome == "already_applied"
        svc._session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_lead_no_error(self):
        """Unsubscribe with no associated lead completes without error."""
        svc = _make_service(lead_returns=None)

        with (
            patch("corpmind.modules.crm.automation.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.crm.automation._emit"),
        ):
            result = await svc._handle_unsubscribe(
                inbox_message_id=INBOX_MSG_ID,
                contact_id=CONTACT_ID,
                workspace_id=WORKSPACE_ID,
                outbound_message_id=None,
                lead=None,
            )

        assert result.outcome == "applied"


# ── handle_classified dispatch ────────────────────────────────────────────────

class TestHandleClassifiedUnsubscribeDispatch:
    @pytest.mark.asyncio
    async def test_unsubscribe_intent_routes_to_handler(self):
        """handle_classified with intent='unsubscribe' calls _handle_unsubscribe."""
        svc = _make_service(lead_returns=_lead())

        with (
            patch("corpmind.modules.crm.automation.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.crm.automation._emit"),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="unsubscribe",
                outbound_message_id=OUTBOUND_ID,
            )

        assert result.outcome == "applied"
        # The SQL UPDATE for whatsapp_opt_in_at should have been issued
        svc._session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fresh_conversation_unsubscribe_with_overrides(self):
        """Fresh-conversation path: no outbound_message_id, overrides provided."""
        svc = _make_service(
            outbound_returns=None,  # _resolve_outbound not called for fresh path
            lead_returns=_lead(),
        )

        with (
            patch("corpmind.modules.crm.automation.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.crm.automation._emit"),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="unsubscribe",
                outbound_message_id=None,
                contact_id_override=CONTACT_ID,
                workspace_id_override=WORKSPACE_ID,
            )

        # Should succeed — overrides provide contact + workspace
        assert result.outcome == "applied"
        # _resolve_outbound must NOT have been called (fresh path bypasses it)
        svc._resolve_outbound.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_outbound_no_overrides_fails(self):
        """No outbound_message_id and no overrides → 'no_outbound_match' failure."""
        svc = _make_service()

        with (
            patch("corpmind.modules.crm.automation.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.crm.automation._emit"),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="unsubscribe",
                outbound_message_id=None,
                contact_id_override=None,
                workspace_id_override=None,
            )

        assert result.outcome == "failed"
        assert result.reason == "no_outbound_match"


# ── ContactUnsubscribed event schema ─────────────────────────────────────────

class TestContactUnsubscribedEvent:
    def test_event_fields(self):
        event = ContactUnsubscribed(
            contact_id=CONTACT_ID,
            tenant_id=TENANT_ID,
            channel="whatsapp",
            source_inbox_message_id=INBOX_MSG_ID,
        )
        assert event.contact_id == CONTACT_ID
        assert event.tenant_id == TENANT_ID
        assert event.channel == "whatsapp"
        assert event.source_inbox_message_id == INBOX_MSG_ID

    def test_event_is_frozen(self):
        event = ContactUnsubscribed(
            contact_id=CONTACT_ID,
            tenant_id=TENANT_ID,
            channel="whatsapp",
            source_inbox_message_id=INBOX_MSG_ID,
        )
        with pytest.raises(Exception):
            event.channel = "email"  # type: ignore[misc]

    def test_occurred_at_is_set(self):
        event = ContactUnsubscribed(
            contact_id=CONTACT_ID,
            tenant_id=TENANT_ID,
            channel="whatsapp",
            source_inbox_message_id=INBOX_MSG_ID,
        )
        assert event.occurred_at is not None

    def test_activity_type_constant(self):
        assert ACTIVITY_WHATSAPP_UNSUBSCRIBED == "whatsapp_unsubscribed"
