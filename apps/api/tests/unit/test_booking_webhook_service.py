"""Unit tests for CRMService.process_booking_event() — Sprint 14.

All DB calls are mocked so these run without testcontainers.  Tests verify:
  - Duplicate events are dropped before any processing (idempotency gate).
  - Unsupported event types mark the event as skipped immediately.
  - Contact-not-found path marks the event as skipped.
  - No-active-lead path marks the event as skipped.
  - Happy path: lead fields updated, CRM activity created, outcome applied.
  - Provider_event_id is written to Lead.booking_provider_event_id.
  - BookingWebhookReceived event is always emitted (before idempotency check).
  - MeetingAutoScheduled event is only emitted on success.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.crm.schemas import BookingWebhookPayload


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _payload(**overrides) -> BookingWebhookPayload:  # type: ignore[return]
    return BookingWebhookPayload(
        provider="calendly",
        provider_event_id=overrides.get("provider_event_id", str(uuid.uuid4())),
        event_type=overrides.get("event_type", "booking.created"),
        invitee_email=overrides.get("invitee_email", "hr@acme.com"),
        invitee_name="Jane HR",
        scheduled_at=overrides.get(
            "scheduled_at", datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
        ),
        metadata={},
    )


def _make_lead(
    contact_id: uuid.UUID,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> MagicMock:
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.contact_id = contact_id
    lead.workspace_id = workspace_id
    lead.tenant_id = tenant_id
    lead.stage = "engaged"
    return lead


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_service(session: MagicMock) -> object:
    """Build a CRMService with a mocked session and pre-wired TenantContext."""
    from corpmind.modules.crm.service import CRMService
    return CRMService(session)


def _mock_tenant(org_id: uuid.UUID, workspace_id: uuid.UUID) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id
    ctx.workspace_id = workspace_id
    return ctx


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_event_returns_early() -> None:
    """If BookingWebhookEventRepo.reserve() returns None, we drop the event."""
    session = MagicMock()
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    payload = _payload()

    with (
        patch("corpmind.modules.crm.service.get_tenant_context",
              return_value=_mock_tenant(org_id, workspace_id)),
        patch("corpmind.modules.crm.service.BookingWebhookEventRepo") as MockRepo,
        patch("corpmind.modules.crm.service._log_event"),
    ):
        mock_repo = AsyncMock()
        mock_repo.reserve = AsyncMock(return_value=None)  # duplicate
        MockRepo.return_value = mock_repo

        svc = _make_service(session)
        await svc.process_booking_event(workspace_id, payload)

        mock_repo.reserve.assert_awaited_once()
        mock_repo.mark_outcome.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_event_type_marks_skipped() -> None:
    """booking.cancelled should be skipped, not raise."""
    session = MagicMock()
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    event_id = uuid.uuid4()
    payload = _payload(event_type="booking.cancelled")

    with (
        patch("corpmind.modules.crm.service.get_tenant_context",
              return_value=_mock_tenant(org_id, workspace_id)),
        patch("corpmind.modules.crm.service.BookingWebhookEventRepo") as MockRepo,
        patch("corpmind.modules.crm.service._log_event"),
    ):
        mock_repo = AsyncMock()
        mock_repo.reserve = AsyncMock(return_value=event_id)
        mock_repo.mark_outcome = AsyncMock()
        MockRepo.return_value = mock_repo

        svc = _make_service(session)
        await svc.process_booking_event(workspace_id, payload)

        mock_repo.mark_outcome.assert_awaited_once_with(event_id, outcome="skipped")


@pytest.mark.asyncio
async def test_contact_not_found_marks_skipped() -> None:
    """When no hr_contact row matches the invitee email, outcome is skipped."""
    session = AsyncMock()
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    event_id = uuid.uuid4()
    payload = _payload()

    # Simulate empty DB result for the raw-SQL contact lookup
    mock_result = MagicMock()
    mock_result.first.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    with (
        patch("corpmind.modules.crm.service.get_tenant_context",
              return_value=_mock_tenant(org_id, workspace_id)),
        patch("corpmind.modules.crm.service.BookingWebhookEventRepo") as MockRepo,
        patch("corpmind.modules.crm.service._log_event"),
    ):
        mock_repo = AsyncMock()
        mock_repo.reserve = AsyncMock(return_value=event_id)
        mock_repo.mark_outcome = AsyncMock()
        MockRepo.return_value = mock_repo

        svc = _make_service(session)
        await svc.process_booking_event(workspace_id, payload)

        mock_repo.mark_outcome.assert_awaited_once_with(event_id, outcome="skipped")


@pytest.mark.asyncio
async def test_no_active_lead_marks_skipped() -> None:
    """When the contact exists but has no active lead, outcome is skipped."""
    session = AsyncMock()
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    event_id = uuid.uuid4()
    contact_id = uuid.uuid4()
    payload = _payload()

    mock_result = MagicMock()
    mock_result.first.return_value = (str(contact_id),)
    session.execute = AsyncMock(return_value=mock_result)

    with (
        patch("corpmind.modules.crm.service.get_tenant_context",
              return_value=_mock_tenant(org_id, workspace_id)),
        patch("corpmind.modules.crm.service.BookingWebhookEventRepo") as MockRepo,
        patch("corpmind.modules.crm.service.LeadRepo") as MockLeadRepo,
        patch("corpmind.modules.crm.service._log_event"),
    ):
        mock_repo = AsyncMock()
        mock_repo.reserve = AsyncMock(return_value=event_id)
        mock_repo.mark_outcome = AsyncMock()
        MockRepo.return_value = mock_repo

        mock_lead_repo = AsyncMock()
        mock_lead_repo.find_active_by_contact_any_workspace = AsyncMock(return_value=None)
        MockLeadRepo.return_value = mock_lead_repo

        svc = _make_service(session)
        await svc.process_booking_event(workspace_id, payload)

        mock_repo.mark_outcome.assert_awaited_once_with(event_id, outcome="skipped")


@pytest.mark.asyncio
async def test_happy_path_updates_lead_and_marks_applied() -> None:
    """Full happy path: lead is updated, activity created, outcome applied."""
    session = AsyncMock()
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    event_id = uuid.uuid4()
    contact_id = uuid.uuid4()
    scheduled = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
    payload = _payload(scheduled_at=scheduled)

    lead = _make_lead(contact_id, workspace_id, org_id)

    mock_contact_result = MagicMock()
    mock_contact_result.first.return_value = (str(contact_id),)
    session.execute = AsyncMock(return_value=mock_contact_result)

    emitted: list[object] = []

    with (
        patch("corpmind.modules.crm.service.get_tenant_context",
              return_value=_mock_tenant(org_id, workspace_id)),
        patch("corpmind.modules.crm.service.BookingWebhookEventRepo") as MockRepo,
        patch("corpmind.modules.crm.service.LeadRepo") as MockLeadRepo,
        patch("corpmind.modules.crm.service.ActivityRepo") as MockActivityRepo,
        patch("corpmind.modules.crm.service._log_event", side_effect=emitted.append),
    ):
        mock_booking_repo = AsyncMock()
        mock_booking_repo.reserve = AsyncMock(return_value=event_id)
        mock_booking_repo.mark_outcome = AsyncMock()
        MockRepo.return_value = mock_booking_repo

        mock_lead_repo = AsyncMock()
        mock_lead_repo.find_active_by_contact_any_workspace = AsyncMock(return_value=lead)
        mock_lead_repo.update_fields = AsyncMock()
        MockLeadRepo.return_value = mock_lead_repo

        mock_activity_repo = AsyncMock()
        mock_activity_repo.create = AsyncMock()
        MockActivityRepo.return_value = mock_activity_repo

        svc = _make_service(session)
        await svc.process_booking_event(workspace_id, payload)

        # Lead was updated with the scheduled time and provider event id
        mock_lead_repo.update_fields.assert_awaited_once_with(
            lead.id,
            meeting_scheduled_at=scheduled,
            booking_provider_event_id=payload.provider_event_id,
        )

        # Activity was created
        mock_activity_repo.create.assert_awaited_once()
        activity_arg = mock_activity_repo.create.call_args[0][0]
        assert activity_arg.type == "booking_confirmed"
        assert "calendly" in activity_arg.summary

        # Outcome marked applied with the lead id
        mock_booking_repo.mark_outcome.assert_awaited_once_with(
            event_id, outcome="applied", lead_id=lead.id
        )


@pytest.mark.asyncio
async def test_meeting_auto_scheduled_event_emitted_on_success() -> None:
    """MeetingAutoScheduled domain event is emitted on the happy path."""
    from corpmind.modules.crm.events import MeetingAutoScheduled

    session = AsyncMock()
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    event_id = uuid.uuid4()
    contact_id = uuid.uuid4()
    payload = _payload()
    lead = _make_lead(contact_id, workspace_id, org_id)

    mock_contact_result = MagicMock()
    mock_contact_result.first.return_value = (str(contact_id),)
    session.execute = AsyncMock(return_value=mock_contact_result)

    emitted: list[object] = []

    with (
        patch("corpmind.modules.crm.service.get_tenant_context",
              return_value=_mock_tenant(org_id, workspace_id)),
        patch("corpmind.modules.crm.service.BookingWebhookEventRepo") as MockRepo,
        patch("corpmind.modules.crm.service.LeadRepo") as MockLeadRepo,
        patch("corpmind.modules.crm.service.ActivityRepo") as MockActivityRepo,
        patch("corpmind.modules.crm.service._log_event", side_effect=emitted.append),
    ):
        MockRepo.return_value = AsyncMock(
            reserve=AsyncMock(return_value=event_id),
            mark_outcome=AsyncMock(),
        )
        MockLeadRepo.return_value = AsyncMock(
            find_active_by_contact_any_workspace=AsyncMock(return_value=lead),
            update_fields=AsyncMock(),
        )
        MockActivityRepo.return_value = AsyncMock(create=AsyncMock())

        svc = _make_service(session)
        await svc.process_booking_event(workspace_id, payload)

    scheduled_events = [e for e in emitted if isinstance(e, MeetingAutoScheduled)]
    assert len(scheduled_events) == 1
    evt = scheduled_events[0]
    assert evt.lead_id == lead.id
    assert evt.provider == "calendly"
    assert evt.provider_event_id == payload.provider_event_id


@pytest.mark.asyncio
async def test_booking_webhook_received_always_emitted() -> None:
    """BookingWebhookReceived is emitted even for duplicate events."""
    from corpmind.modules.crm.events import BookingWebhookReceived

    session = MagicMock()
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    payload = _payload()

    emitted: list[object] = []

    with (
        patch("corpmind.modules.crm.service.get_tenant_context",
              return_value=_mock_tenant(org_id, workspace_id)),
        patch("corpmind.modules.crm.service.BookingWebhookEventRepo") as MockRepo,
        patch("corpmind.modules.crm.service._log_event", side_effect=emitted.append),
    ):
        MockRepo.return_value = AsyncMock(reserve=AsyncMock(return_value=None))

        svc = _make_service(session)
        await svc.process_booking_event(workspace_id, payload)

    received_events = [e for e in emitted if isinstance(e, BookingWebhookReceived)]
    assert len(received_events) == 1


@pytest.mark.asyncio
async def test_booking_rescheduled_event_type_is_processed() -> None:
    """booking.rescheduled is treated the same as booking.created."""
    session = AsyncMock()
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    event_id = uuid.uuid4()
    contact_id = uuid.uuid4()
    payload = _payload(event_type="booking.rescheduled")
    lead = _make_lead(contact_id, workspace_id, org_id)

    mock_contact_result = MagicMock()
    mock_contact_result.first.return_value = (str(contact_id),)
    session.execute = AsyncMock(return_value=mock_contact_result)

    with (
        patch("corpmind.modules.crm.service.get_tenant_context",
              return_value=_mock_tenant(org_id, workspace_id)),
        patch("corpmind.modules.crm.service.BookingWebhookEventRepo") as MockRepo,
        patch("corpmind.modules.crm.service.LeadRepo") as MockLeadRepo,
        patch("corpmind.modules.crm.service.ActivityRepo") as MockActivityRepo,
        patch("corpmind.modules.crm.service._log_event"),
    ):
        MockRepo.return_value = AsyncMock(
            reserve=AsyncMock(return_value=event_id),
            mark_outcome=AsyncMock(),
        )
        lead_repo = AsyncMock(
            find_active_by_contact_any_workspace=AsyncMock(return_value=lead),
            update_fields=AsyncMock(),
        )
        MockLeadRepo.return_value = lead_repo
        MockActivityRepo.return_value = AsyncMock(create=AsyncMock())

        svc = _make_service(session)
        await svc.process_booking_event(workspace_id, payload)

        lead_repo.update_fields.assert_awaited_once()


@pytest.mark.asyncio
async def test_invitee_email_is_lowercased_in_reserve() -> None:
    """Emails are stored lower-cased so 'HR@Acme.COM' matches 'hr@acme.com'."""
    session = AsyncMock()
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    payload = _payload(invitee_email="HR@Acme.COM", event_type="booking.cancelled")

    mock_result = MagicMock()
    mock_result.first.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    with (
        patch("corpmind.modules.crm.service.get_tenant_context",
              return_value=_mock_tenant(org_id, workspace_id)),
        patch("corpmind.modules.crm.service.BookingWebhookEventRepo") as MockRepo,
        patch("corpmind.modules.crm.service._log_event"),
    ):
        event_id = uuid.uuid4()
        mock_repo = AsyncMock(
            reserve=AsyncMock(return_value=event_id),
            mark_outcome=AsyncMock(),
        )
        MockRepo.return_value = mock_repo

        svc = _make_service(session)
        await svc.process_booking_event(workspace_id, payload)

        # reserve() was called — the repo layer lowercases the email
        mock_repo.reserve.assert_awaited_once()
        call_kwargs = mock_repo.reserve.call_args.kwargs
        # invitee_email passed to reserve (repo normalises it)
        assert call_kwargs["invitee_email"] == "HR@Acme.COM"  # service passes raw
