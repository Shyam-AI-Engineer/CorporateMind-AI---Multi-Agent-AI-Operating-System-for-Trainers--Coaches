"""Compliance schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ComplianceOutcome(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    HITL_REQUIRED = "hitl_required"


class ComplianceCheckRequest(BaseModel):
    contact_id: uuid.UUID
    channel: str
    content_hash: str
    recipient_count: int = 1
    campaign_id: uuid.UUID | None = None
    # HMAC(email, org_id) — used for frequency-cap and unsubscribe lookups without storing raw PII
    recipient_hash: str | None = None


class ComplianceCheckResult(BaseModel):
    outcome: ComplianceOutcome
    reason: str | None = None
    blocked_by: str | None = None  # which check failed
    audit_event_id: uuid.UUID | None = None
