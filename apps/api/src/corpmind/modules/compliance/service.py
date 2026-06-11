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


class ComplianceService:
    """Database-backed compliance checks called by ComplianceGuardAgent nodes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditRepo(session)
        self._unsub = UnsubscribeRepo(session)

    async def check_opt_in(self, req: ComplianceCheckRequest) -> ComplianceCheckResult:
        """Verify contact has a current opt-in record (hr_contacts.is_contactable = true)."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            text(
                "SELECT is_contactable FROM hr_contacts"
                " WHERE id = :cid AND tenant_id = :tid"
            ),
            {"cid": str(req.contact_id), "tid": str(ctx.org_id)},
        )
        row = result.one_or_none()
        is_contactable = bool(row and row[0])
        log.info(
            "compliance.opt_in_check",
            contact_id=str(req.contact_id),
            channel=req.channel,
            is_contactable=is_contactable,
        )
        if not is_contactable:
            event = await self._write_block_audit(req, ctx, "opt_in")
            return ComplianceCheckResult(
                outcome=ComplianceOutcome.BLOCKED,
                reason="Contact has no current opt-in for outbound sends",
                blocked_by="opt_in",
                audit_event_id=event.id,
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
