"""Unit tests for Sprint 18A proposal revenue workflow.

Covers:
  ProposalService.record_acceptance()
    - happy path: sets client_status, client_accepted_at, actual_value_inr
    - also updates expected_value_inr when provided
    - advances lead to 'booked' via raw SQL when lead_id is set
    - skips lead advance when lead_id is None
    - guard: status must be 'sent'
    - guard: client_status must be None (no prior response)
    - guard: actual_value_inr must be positive (schema-level)
    - writes CRM activity with ₹ value in summary
    - writes audit event proposal.accepted
    - emits ProposalAccepted domain event

  ProposalService.record_declination()
    - happy path: sets client_status='declined', client_declined_at
    - guard: status must be 'sent'
    - guard: client_status must be None
    - writes CRM activity with optional reason
    - writes audit event proposal.declined
    - emits ProposalDeclined domain event
    - does NOT touch lead stage

  ProposalService.generate()
    - persists lead_id on the Proposal (Sprint 18A attribution fix)
    - persists expected_value_inr when provided

  AcceptProposalRequest schema
    - rejects actual_value_inr <= 0
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import ConflictError, NotFoundError
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.proposals.events import ProposalAccepted, ProposalDeclined
from corpmind.modules.proposals.models import Proposal
from corpmind.modules.proposals.schemas import AcceptProposalRequest, DeclineProposalRequest
from corpmind.modules.proposals.service import ProposalService

# ── Shared fixtures ────────────────────────────────────────────────────────────

_ORG_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PROPOSAL_ID = uuid.uuid4()
_CONTACT_ID = uuid.uuid4()
_LEAD_ID = uuid.uuid4()
_OUTBOUND_ID = uuid.uuid4()

_ADMIN_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="OrgAdmin",
    request_id="req-revenue-test-001",
)


def _make_sent_proposal(
    *,
    lead_id: uuid.UUID | None = _LEAD_ID,
    client_status: str | None = None,
    expected_value_inr: Decimal | None = None,
) -> Proposal:
    p = Proposal(
        tenant_id=_ORG_ID,
        workspace_id=_WS_ID,
        contact_id=_CONTACT_ID,
        title="Test Proposal",
        status="sent",
        content={"title": "Test", "body": "Content"},
        approval_status="approved",
    )
    p.id = _PROPOSAL_ID
    p.cloudinary_url = None
    p.sent_at = datetime.now(UTC)
    p.created_at = datetime.now(UTC)
    p.approved_by = _USER_ID
    p.approved_at = datetime.now(UTC)
    p.rejected_reason = None
    p.outbound_message_id = _OUTBOUND_ID
    p.lead_id = lead_id
    p.expected_value_inr = expected_value_inr
    p.actual_value_inr = None
    p.client_status = client_status
    p.client_accepted_at = None
    p.client_declined_at = None
    return p


def _make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_svc(session: MagicMock) -> ProposalService:
    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock()
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()
    return svc


# ── record_acceptance ──────────────────────────────────────────────────────────

class TestRecordAcceptance:
    @pytest.mark.asyncio
    async def test_happy_path_sets_client_status(self):
        """Acceptance sets client_status='accepted' and actual_value_inr."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_sent_proposal())

        result = await svc.record_acceptance(
            _PROPOSAL_ID, AcceptProposalRequest(actual_value_inr=Decimal("150000"))
        )

        clear_tenant_context(token)
        assert result.client_status == "accepted"
        assert result.actual_value_inr == Decimal("150000")
        assert result.client_accepted_at is not None

    @pytest.mark.asyncio
    async def test_updates_expected_value_when_provided(self):
        """expected_value_inr is updated when passed in the request."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_sent_proposal())

        await svc.record_acceptance(
            _PROPOSAL_ID,
            AcceptProposalRequest(
                actual_value_inr=Decimal("150000"),
                expected_value_inr=Decimal("200000"),
            ),
        )

        clear_tenant_context(token)
        update_kwargs = svc._repo.update_fields.call_args[1]
        assert update_kwargs["expected_value_inr"] == Decimal("200000")

    @pytest.mark.asyncio
    async def test_skips_expected_value_when_not_provided(self):
        """expected_value_inr is NOT written when omitted from request."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_sent_proposal())

        await svc.record_acceptance(
            _PROPOSAL_ID, AcceptProposalRequest(actual_value_inr=Decimal("150000"))
        )

        clear_tenant_context(token)
        update_kwargs = svc._repo.update_fields.call_args[1]
        assert "expected_value_inr" not in update_kwargs

    @pytest.mark.asyncio
    async def test_advances_lead_to_booked_via_sql(self):
        """When lead_id is set, issues raw SQL to advance lead to 'booked'."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(
            return_value=_make_sent_proposal(lead_id=_LEAD_ID)
        )

        await svc.record_acceptance(
            _PROPOSAL_ID, AcceptProposalRequest(actual_value_inr=Decimal("150000"))
        )

        clear_tenant_context(token)
        # session.execute is called twice: lead advance + CRM activity insert
        assert session.execute.await_count == 2
        lead_sql = str(session.execute.call_args_list[0].args[0])
        assert "stage = 'booked'" in lead_sql
        assert "NOT IN ('booked', 'lost')" in lead_sql

    @pytest.mark.asyncio
    async def test_skips_lead_advance_when_no_lead_id(self):
        """When lead_id is None, no lead UPDATE is issued."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(
            return_value=_make_sent_proposal(lead_id=None)
        )

        await svc.record_acceptance(
            _PROPOSAL_ID, AcceptProposalRequest(actual_value_inr=Decimal("150000"))
        )

        clear_tenant_context(token)
        # Only the CRM activity INSERT; no lead UPDATE
        assert session.execute.await_count == 1
        sql = str(session.execute.call_args_list[0].args[0])
        assert "crm_activities" in sql

    @pytest.mark.asyncio
    async def test_guard_status_not_sent_raises(self):
        """ConflictError when proposal.status is not 'sent'."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        draft = _make_sent_proposal()
        draft.status = "draft"
        svc._repo.find_by_id_for_update = AsyncMock(return_value=draft)

        with pytest.raises(ConflictError, match="status must be 'sent'"):
            await svc.record_acceptance(
                _PROPOSAL_ID, AcceptProposalRequest(actual_value_inr=Decimal("100000"))
            )

        clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_guard_already_responded_raises(self):
        """ConflictError when client_status is already set."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(
            return_value=_make_sent_proposal(client_status="accepted")
        )

        with pytest.raises(ConflictError, match="already has a client response"):
            await svc.record_acceptance(
                _PROPOSAL_ID, AcceptProposalRequest(actual_value_inr=Decimal("100000"))
            )

        clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        """NotFoundError when the proposal doesn't exist."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.record_acceptance(
                _PROPOSAL_ID, AcceptProposalRequest(actual_value_inr=Decimal("100000"))
            )

        clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_writes_crm_activity(self):
        """Acceptance writes a 'proposal_accepted' CRM activity with ₹ value."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_sent_proposal())

        await svc.record_acceptance(
            _PROPOSAL_ID, AcceptProposalRequest(actual_value_inr=Decimal("150000"))
        )

        clear_tenant_context(token)
        # Last execute call is the CRM activity insert ('type' is hardcoded in SQL)
        last_call = session.execute.call_args_list[-1]
        last_sql = str(last_call.args[0])
        assert "crm_activities" in last_sql
        assert "proposal_accepted" in last_sql
        last_params = last_call.args[1]
        assert "150,000" in last_params["summary"]

    @pytest.mark.asyncio
    async def test_writes_audit_event(self):
        """Acceptance writes a proposal.accepted audit event."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_sent_proposal())

        await svc.record_acceptance(
            _PROPOSAL_ID, AcceptProposalRequest(actual_value_inr=Decimal("150000"))
        )

        clear_tenant_context(token)
        svc._compliance.record_audit_event.assert_awaited_once()
        audit_kwargs = svc._compliance.record_audit_event.call_args[1]
        assert audit_kwargs["event_type"] == "proposal.accepted"
        assert audit_kwargs["outcome"] == "allowed"

    @pytest.mark.asyncio
    async def test_emits_proposal_accepted_event(self):
        """ProposalAccepted domain event is emitted with correct fields."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_sent_proposal())
        emitted: list = []

        with patch(
            "corpmind.modules.proposals.service._log_event",
            side_effect=emitted.append,
        ):
            await svc.record_acceptance(
                _PROPOSAL_ID, AcceptProposalRequest(actual_value_inr=Decimal("150000"))
            )

        clear_tenant_context(token)
        assert len(emitted) == 1
        event = emitted[0]
        assert isinstance(event, ProposalAccepted)
        assert event.proposal_id == _PROPOSAL_ID
        assert event.tenant_id == _ORG_ID
        assert event.contact_id == _CONTACT_ID
        assert event.actual_value_inr == Decimal("150000")


# ── record_declination ─────────────────────────────────────────────────────────

class TestRecordDeclination:
    @pytest.mark.asyncio
    async def test_happy_path_sets_client_status(self):
        """Declination sets client_status='declined' and client_declined_at."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_sent_proposal())

        result = await svc.record_declination(
            _PROPOSAL_ID, DeclineProposalRequest(reason="Budget not approved")
        )

        clear_tenant_context(token)
        assert result.client_status == "declined"
        assert result.client_declined_at is not None
        assert result.actual_value_inr is None  # unchanged

    @pytest.mark.asyncio
    async def test_guard_status_not_sent_raises(self):
        """ConflictError when proposal.status is not 'sent'."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        draft = _make_sent_proposal()
        draft.status = "draft"
        svc._repo.find_by_id_for_update = AsyncMock(return_value=draft)

        with pytest.raises(ConflictError, match="status must be 'sent'"):
            await svc.record_declination(
                _PROPOSAL_ID, DeclineProposalRequest()
            )

        clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_guard_already_responded_raises(self):
        """ConflictError when client_status is already set."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(
            return_value=_make_sent_proposal(client_status="declined")
        )

        with pytest.raises(ConflictError, match="already has a client response"):
            await svc.record_declination(
                _PROPOSAL_ID, DeclineProposalRequest()
            )

        clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        """NotFoundError when the proposal doesn't exist."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.record_declination(_PROPOSAL_ID, DeclineProposalRequest())

        clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_writes_crm_activity_with_reason(self):
        """CRM activity summary includes the declination reason when provided."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_sent_proposal())

        await svc.record_declination(
            _PROPOSAL_ID, DeclineProposalRequest(reason="No budget this quarter")
        )

        clear_tenant_context(token)
        last_call = session.execute.call_args_list[-1]
        assert "proposal_declined" in str(last_call.args[0])
        assert "No budget this quarter" in last_call.args[1]["summary"]

    @pytest.mark.asyncio
    async def test_writes_crm_activity_without_reason(self):
        """CRM activity still created when no reason is provided."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_sent_proposal())

        await svc.record_declination(_PROPOSAL_ID, DeclineProposalRequest())

        clear_tenant_context(token)
        last_call = session.execute.call_args_list[-1]
        assert "proposal_declined" in str(last_call.args[0])
        assert "crm_activities" in str(last_call.args[0])

    @pytest.mark.asyncio
    async def test_writes_audit_event(self):
        """Declination writes a proposal.declined audit event."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_sent_proposal())

        await svc.record_declination(
            _PROPOSAL_ID, DeclineProposalRequest(reason="timing")
        )

        clear_tenant_context(token)
        audit_kwargs = svc._compliance.record_audit_event.call_args[1]
        assert audit_kwargs["event_type"] == "proposal.declined"
        assert audit_kwargs["outcome"] == "allowed"

    @pytest.mark.asyncio
    async def test_emits_proposal_declined_event(self):
        """ProposalDeclined domain event is emitted with correct fields."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_sent_proposal())
        emitted: list = []

        with patch(
            "corpmind.modules.proposals.service._log_event",
            side_effect=emitted.append,
        ):
            await svc.record_declination(
                _PROPOSAL_ID, DeclineProposalRequest(reason="budget")
            )

        clear_tenant_context(token)
        assert len(emitted) == 1
        event = emitted[0]
        assert isinstance(event, ProposalDeclined)
        assert event.proposal_id == _PROPOSAL_ID
        assert event.tenant_id == _ORG_ID
        assert event.reason == "budget"

    @pytest.mark.asyncio
    async def test_does_not_touch_lead_stage(self):
        """Declination never issues a lead UPDATE — lead stage is preserved."""
        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = _make_svc(session)
        svc._repo.find_by_id_for_update = AsyncMock(
            return_value=_make_sent_proposal(lead_id=_LEAD_ID)
        )

        await svc.record_declination(_PROPOSAL_ID, DeclineProposalRequest())

        clear_tenant_context(token)
        # Only one execute call (the CRM activity INSERT); no lead UPDATE
        assert session.execute.await_count == 1
        sql = str(session.execute.call_args_list[0].args[0])
        assert "leads" not in sql


# ── generate() lead_id attribution ────────────────────────────────────────────

class TestGenerateLeadIdAttribution:
    @pytest.mark.asyncio
    async def test_generate_persists_lead_id(self):
        """generate() stores lead_id on the Proposal (Sprint 18A attribution fix)."""
        from corpmind.modules.crm.schemas import LeadOut
        from corpmind.modules.proposals.schemas import GenerateProposalRequest

        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = ProposalService(session)
        svc._repo.create = AsyncMock(side_effect=lambda p: p)
        svc._compliance.record_audit_event = AsyncMock()

        lead = LeadOut(
            id=_LEAD_ID,
            workspace_id=_WS_ID,
            contact_id=_CONTACT_ID,
            stage="meeting_completed",
            score=75,
            notes=None,
            extra={},
            meeting_scheduled_at=None,
            booked_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        created_proposals: list[Proposal] = []

        def capture_create(p: Proposal) -> Proposal:
            created_proposals.append(p)
            p.id = uuid.uuid4()
            p.created_at = datetime.now(UTC)
            return p

        svc._repo.create = AsyncMock(side_effect=capture_create)

        with patch.object(
            svc,
            "_fetch_delivery_status",
            new_callable=lambda: lambda *a, **kw: None,
        ):
            with patch("corpmind.modules.proposals.service.EuriClient") as mock_euri_cls:
                mock_euri = MagicMock()
                mock_euri.chat = AsyncMock(return_value={
                    "content": '{"title": "Test", "body": "Body text"}'
                })
                mock_euri_cls.return_value = mock_euri

                await svc.generate(
                    GenerateProposalRequest(
                        lead_id=_LEAD_ID,
                        workspace_id=_WS_ID,
                    ),
                    lead,
                )

        clear_tenant_context(token)
        assert len(created_proposals) == 1
        assert created_proposals[0].lead_id == _LEAD_ID

    @pytest.mark.asyncio
    async def test_generate_persists_expected_value_inr(self):
        """generate() stores expected_value_inr when provided in the request."""
        from corpmind.modules.crm.schemas import LeadOut
        from corpmind.modules.proposals.schemas import GenerateProposalRequest

        token = set_tenant_context(_ADMIN_CTX)
        session = _make_session()
        svc = ProposalService(session)
        svc._compliance.record_audit_event = AsyncMock()

        lead = LeadOut(
            id=_LEAD_ID,
            workspace_id=_WS_ID,
            contact_id=_CONTACT_ID,
            stage="booked",
            score=90,
            notes=None,
            extra={},
            meeting_scheduled_at=None,
            booked_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        created_proposals: list[Proposal] = []

        def capture_create(p: Proposal) -> Proposal:
            created_proposals.append(p)
            p.id = uuid.uuid4()
            p.created_at = datetime.now(UTC)
            return p

        svc._repo.create = AsyncMock(side_effect=capture_create)

        with patch("corpmind.modules.proposals.service.EuriClient") as mock_euri_cls:
            mock_euri = MagicMock()
            mock_euri.chat = AsyncMock(return_value={
                "content": '{"title": "Leadership Workshop", "body": "Details"}'
            })
            mock_euri_cls.return_value = mock_euri

            await svc.generate(
                GenerateProposalRequest(
                    lead_id=_LEAD_ID,
                    workspace_id=_WS_ID,
                    expected_value_inr=Decimal("250000"),
                ),
                lead,
            )

        clear_tenant_context(token)
        assert created_proposals[0].expected_value_inr == Decimal("250000")


# ── AcceptProposalRequest schema validation ────────────────────────────────────

class TestAcceptProposalRequestSchema:
    def test_zero_value_rejected(self):
        import pytest as _pytest
        from pydantic import ValidationError
        with _pytest.raises(ValidationError, match="positive"):
            AcceptProposalRequest(actual_value_inr=Decimal("0"))

    def test_negative_value_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="positive"):
            AcceptProposalRequest(actual_value_inr=Decimal("-500"))

    def test_positive_value_accepted(self):
        req = AcceptProposalRequest(actual_value_inr=Decimal("100000"))
        assert req.actual_value_inr == Decimal("100000")
        assert req.expected_value_inr is None
