"""Compliance service — the programmatic gate for all outbound sends.

The actual ComplianceGuardAgent (LangGraph) orchestrates these checks.
This service provides the synchronous database-backed checks it calls.
Every send AND every block is written to audit_events.
"""

from __future__ import annotations

import structlog

from corpmind.modules.compliance.schemas import (
    ComplianceCheckRequest,
    ComplianceCheckResult,
    ComplianceOutcome,
)

log = structlog.get_logger(__name__)


class ComplianceService:
    """Lightweight compliance checks called by ComplianceGuardAgent nodes."""

    async def check_opt_in(self, req: ComplianceCheckRequest) -> ComplianceCheckResult:
        """Verify contact has a current opt-in record for this channel."""
        # TODO(Phase 1): query hr_contacts opt_in fields
        log.info("compliance.opt_in_check", contact_id=str(req.contact_id), channel=req.channel)
        return ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)

    async def check_frequency_cap(self, req: ComplianceCheckRequest) -> ComplianceCheckResult:
        """Verify ≤ 2 marketing messages per 7 days cross-channel."""
        # TODO(Phase 1): query recent audit_events for this contact
        log.info("compliance.frequency_cap_check", contact_id=str(req.contact_id))
        return ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)

    async def check_unsubscribe(self, req: ComplianceCheckRequest) -> ComplianceCheckResult:
        """Verify contact is not on unsubscribe list."""
        # TODO(Phase 1): query UnsubscribeRepo
        log.info("compliance.unsubscribe_check", contact_id=str(req.contact_id))
        return ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)
