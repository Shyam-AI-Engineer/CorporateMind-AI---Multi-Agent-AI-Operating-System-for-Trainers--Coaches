"""Compliance service — the programmatic gate for all outbound sends.

The actual ComplianceGuardAgent (LangGraph) orchestrates these checks.
This service provides the database-backed checks it calls.

Design notes
────────────
• check_opt_in  — raw SQL on hr_contacts (avoids importing hr_discovery models).
• check_frequency_cap — queries audit_events (this module's own table).
  Every confirmed send writes event_type='message.sent' so the count is
  authoritative without crossing module boundaries.
• check_unsubscribe — UnsubscribeRepo (this module's own table).
• All blocks write an AuditEvent before returning BLOCKED.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac_mod
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import TenantContext, get_tenant_context
from corpmind.modules.compliance.models import AuditEvent
from corpmind.modules.compliance.repo import AuditRepo, UnsubscribeRepo
from corpmind.modules.compliance.schemas import (
    ComplianceCheckRequest,
    ComplianceCheckResult,
    ComplianceOutcome,
)

log = structlog.get_logger(__name__)

_FREQUENCY_CAP = 2       # max marketing sends to one recipient in the rolling window
_FREQUENCY_WINDOW = "7"  # days — kept as a string constant, not user-supplied


def _recipient_hmac(email: str | None, tenant_id: uuid.UUID) -> str | None:
    """HMAC-SHA256(email, tenant_id) — per-tenant PII-safe hash for unsubscribe lookups."""
    if not email:
        return None
    key = str(tenant_id).encode()
    return _hmac_mod.new(key, email.encode(), hashlib.sha256).hexdigest()


class ComplianceService:
    """Database-backed compliance checks called by ComplianceGuardAgent nodes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditRepo(session)
        self._unsub = UnsubscribeRepo(session)

    async def check_opt_in(self, req: ComplianceCheckRequest) -> ComplianceCheckResult:
        """Verify contact exists, is_contactable, and has an opted_in_at timestamp."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            text(
                "SELECT is_contactable, opted_in_at, opt_in_evidence"
                " FROM hr_contacts"
                " WHERE id = :cid AND tenant_id = :tid"
            ),
            {"cid": str(req.contact_id), "tid": str(ctx.org_id)},
        )
        row = result.one_or_none()

        if row is None:
            log.info(
                "compliance.opt_in.failed",
                contact_id=str(req.contact_id),
                reason="contact_not_found",
            )
            event = await self._write_block_audit(req, ctx, "opt_in_contact_not_found")
            return ComplianceCheckResult(
                outcome=ComplianceOutcome.BLOCKED,
                reason="Contact not found for this tenant",
                blocked_by="opt_in",
                audit_event_id=event.id,
            )

        is_contactable, opted_in_at, opt_in_evidence = row[0], row[1], row[2]

        if not is_contactable:
            log.info(
                "compliance.opt_in.failed",
                contact_id=str(req.contact_id),
                reason="not_contactable",
            )
            event = await self._write_block_audit(req, ctx, "opt_in")
            return ComplianceCheckResult(
                outcome=ComplianceOutcome.BLOCKED,
                reason="Contact has no current opt-in for outbound sends",
                blocked_by="opt_in",
                audit_event_id=event.id,
            )

        if opted_in_at is None:
            log.info(
                "compliance.opt_in.failed",
                contact_id=str(req.contact_id),
                reason="missing_opted_in_at",
            )
            event = await self._write_block_audit(req, ctx, "opt_in_missing_timestamp")
            return ComplianceCheckResult(
                outcome=ComplianceOutcome.BLOCKED,
                reason="Contact is missing opt-in timestamp",
                blocked_by="opt_in",
                audit_event_id=event.id,
            )

        log.info(
            "compliance.opt_in.passed",
            contact_id=str(req.contact_id),
            channel=req.channel,
            has_evidence=bool(opt_in_evidence),
        )
        return ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)

    async def check_frequency_cap(self, req: ComplianceCheckRequest) -> ComplianceCheckResult:
        """Verify ≤ 2 marketing messages per 7 rolling days (cross-channel)."""
        if req.recipient_hash is None:
            log.warning("compliance.frequency_cap.no_hash", contact_id=str(req.contact_id))
            return ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)

        ctx = get_tenant_context()
        result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM audit_events"
                " WHERE tenant_id = :tid"
                "   AND recipient_hash = :rhash"
                "   AND event_type = 'message.sent'"
                "   AND occurred_at > NOW() - INTERVAL '7 days'"
            ),
            {"tid": str(ctx.org_id), "rhash": req.recipient_hash},
        )
        recent_count: int = result.scalar_one()
        log.info(
            "compliance.frequency_cap_check",
            contact_id=str(req.contact_id),
            recent_sends=recent_count,
            cap=_FREQUENCY_CAP,
        )
        if recent_count >= _FREQUENCY_CAP:
            event = await self._write_block_audit(req, ctx, "frequency_cap")
            return ComplianceCheckResult(
                outcome=ComplianceOutcome.BLOCKED,
                reason=(
                    f"Frequency cap: {recent_count} sends in last {_FREQUENCY_WINDOW} days"
                    f" (max {_FREQUENCY_CAP})"
                ),
                blocked_by="frequency_cap",
                audit_event_id=event.id,
            )
        return ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)

    async def check_unsubscribe(self, req: ComplianceCheckRequest) -> ComplianceCheckResult:
        """Verify contact is not on the tenant's unsubscribe list."""
        if req.recipient_hash is None:
            log.warning("compliance.unsubscribe.no_hash", contact_id=str(req.contact_id))
            return ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)

        ctx = get_tenant_context()
        is_unsub = await self._unsub.is_unsubscribed(
            ctx.org_id, req.recipient_hash, req.channel
        )
        log.info(
            "compliance.unsubscribe_check",
            contact_id=str(req.contact_id),
            is_unsubscribed=is_unsub,
        )
        if is_unsub:
            event = await self._write_block_audit(req, ctx, "unsubscribe")
            return ComplianceCheckResult(
                outcome=ComplianceOutcome.BLOCKED,
                reason="Contact is on the unsubscribe list",
                blocked_by="unsubscribe",
                audit_event_id=event.id,
            )
        return ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)

    async def check_unsubscribe_by_contact_id(
        self, req: ComplianceCheckRequest
    ) -> ComplianceCheckResult:
        """Resolve contact email → HMAC → delegate to check_unsubscribe.

        Used by ComplianceGuardAgent when the caller has a contact_id but not a
        pre-computed recipient_hash.  Keeps hash computation inside the compliance
        module; the agent never touches raw email data.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            text("SELECT email FROM hr_contacts WHERE id = :cid AND tenant_id = :tid"),
            {"cid": str(req.contact_id), "tid": str(ctx.org_id)},
        )
        row = result.one_or_none()
        if row is None:
            # Contact was already rejected by opt_in check; treat as not unsubscribed.
            log.warning(
                "compliance.unsubscribe.contact_not_found",
                contact_id=str(req.contact_id),
            )
            return ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)

        email = row[0]
        recipient_hash = _recipient_hmac(email, ctx.org_id)
        enriched = req.model_copy(update={"recipient_hash": recipient_hash})
        return await self.check_unsubscribe(enriched)

    async def check_whatsapp_opt_in(self, req: ComplianceCheckRequest) -> ComplianceCheckResult:
        """Verify contact has WhatsApp-specific opt-in (ADR-0010, Sprint 16A).

        Checks hr_contacts.whatsapp_opt_in_at IS NOT NULL — a separate consent
        record from the general is_contactable flag.  Required by Meta policy
        and DPDP for WhatsApp channel sends.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            text(
                "SELECT whatsapp_opt_in_at, phone_deliverable FROM hr_contacts"
                " WHERE id = :cid AND tenant_id = :tid"
            ),
            {"cid": str(req.contact_id), "tid": str(ctx.org_id)},
        )
        row = result.one_or_none()
        has_wa_optin = bool(row and row[0] is not None)
        phone_deliverable = bool(row and row[1]) if row else True
        log.info(
            "compliance.whatsapp_opt_in_check",
            contact_id=str(req.contact_id),
            has_wa_optin=has_wa_optin,
            phone_deliverable=phone_deliverable,
        )
        if not has_wa_optin:
            event = await self._write_block_audit(req, ctx, "whatsapp_opt_in")
            return ComplianceCheckResult(
                outcome=ComplianceOutcome.BLOCKED,
                reason="Contact has no WhatsApp opt-in record",
                blocked_by="whatsapp_opt_in",
                audit_event_id=event.id,
            )
        if not phone_deliverable:
            event = await self._write_block_audit(req, ctx, "phone_not_deliverable")
            return ComplianceCheckResult(
                outcome=ComplianceOutcome.BLOCKED,
                reason="Contact phone is marked non-deliverable",
                blocked_by="phone_not_deliverable",
                audit_event_id=event.id,
            )
        return ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)

    async def record_audit_event(
        self,
        *,
        event_type: str,
        outcome: str,
        reason: str | None = None,
        content_hash: str | None = None,
        event_data: dict | None = None,
    ) -> None:
        """Append an audit_events row for a privileged action.

        The public entry point other modules use to write audit records without
        importing this module's repo/models (cross-module boundary rule).  Used
        by the Sprint 8C follow-up approval flow (followup.approved / .rejected /
        .edited / .blocked_on_approve).  actor is the current user from context.
        """
        ctx = get_tenant_context()
        await self._audit.append(
            AuditEvent(
                tenant_id=ctx.org_id,
                actor_id=ctx.user_id,
                actor_type="user",
                event_type=event_type,
                outcome=outcome,
                reason=reason,
                content_hash=content_hash,
                event_data=event_data or {},
            )
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _write_block_audit(
        self,
        req: ComplianceCheckRequest,
        ctx: TenantContext,
        check_name: str,
    ) -> AuditEvent:
        event = AuditEvent(
            tenant_id=ctx.org_id,
            actor_id=ctx.user_id,
            actor_type="agent",
            event_type="compliance.blocked",
            channel=req.channel,
            recipient_hash=req.recipient_hash,
            content_hash=req.content_hash,
            outcome="blocked",
            reason=check_name,
            event_data={
                "contact_id": str(req.contact_id),
                "campaign_id": str(req.campaign_id) if req.campaign_id else None,
            },
        )
        return await self._audit.append(event)
