"""Domain exceptions for CorporateMind AI.

Raise typed exceptions from services; the FastAPI exception handlers in
main.py translate them into the structured error envelope:
  { "code": str, "message": str, "request_id": str }
"""

from __future__ import annotations


class CorporateMindError(Exception):
    """Base class for all domain exceptions."""

    code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ── Auth / Tenancy ────────────────────────────────────────────────────────────

class AuthenticationError(CorporateMindError):
    code = "unauthenticated"
    http_status = 401


class PermissionDeniedError(CorporateMindError):
    code = "permission_denied"
    http_status = 403


class TenantNotFoundError(CorporateMindError):
    code = "tenant_not_found"
    http_status = 404


# ── Compliance ────────────────────────────────────────────────────────────────

class OptInRequiredError(CorporateMindError):
    """Contact has not opted in for this channel."""
    code = "opt_in_required"
    http_status = 422


class FrequencyCapExceededError(CorporateMindError):
    """Sending frequency cap would be violated."""
    code = "frequency_cap_exceeded"
    http_status = 422


class ComplianceBlockError(CorporateMindError):
    """ComplianceGuardAgent blocked the outbound message."""
    code = "compliance_blocked"
    http_status = 422


class UnsubscribedError(CorporateMindError):
    """Recipient has unsubscribed from this tenant's sends."""
    code = "recipient_unsubscribed"
    http_status = 422


# ── AI / Budget ───────────────────────────────────────────────────────────────

class BudgetExceededError(CorporateMindError):
    """Tenant's AI token budget would be exceeded."""
    code = "budget_exceeded"
    http_status = 402


class ModelUnavailableError(CorporateMindError):
    """Entire fallback chain exhausted; no model could serve the request."""
    code = "model_unavailable"
    http_status = 503


# ── Domain ────────────────────────────────────────────────────────────────────

class NotFoundError(CorporateMindError):
    code = "not_found"
    http_status = 404


class ConflictError(CorporateMindError):
    code = "conflict"
    http_status = 409


class ValidationError(CorporateMindError):
    code = "validation_error"
    http_status = 422


class RateLimitError(CorporateMindError):
    """External provider rate limit hit after retries."""
    code = "rate_limited"
    http_status = 429


class ChannelUnavailableError(CorporateMindError):
    """Channel circuit breaker is open."""
    code = "channel_unavailable"
    http_status = 503


# ── Workflow / Agents ─────────────────────────────────────────────────────────

class WorkflowNotFoundError(CorporateMindError):
    code = "workflow_not_found"
    http_status = 404


class CheckpointCorruptedError(CorporateMindError):
    """Workflow checkpoint exists but cannot be deserialized."""
    code = "checkpoint_corrupted"
    http_status = 500


class HITLRequiredError(CorporateMindError):
    """Action requires human-in-the-loop approval before proceeding."""
    code = "hitl_required"
    http_status = 202
