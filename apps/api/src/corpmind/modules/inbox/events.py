"""Inbox domain events.

Phase 1 events are defined as immutable dataclasses and emitted via structlog
(no in-process event bus exists yet in CorporateMind — the same convention is
used by every other module's events.py).  Sprint 4C (CRM automation) will
consume reply.classified to drive lead state transitions.

Naming convention mirrors the module/topic.action pattern used elsewhere:
  reply.classified           — a synced inbound was successfully classified
  reply.classification_failed — classification raised or returned unknown
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ReplyClassified:
    """Successful classification of an inbound reply.

    outbound_message_id is None when the inbound could not be matched to an
    outbound (smtp_message_id mismatch or no headers); downstream CRM logic
    must tolerate that case.
    """

    inbox_message_id: uuid.UUID
    tenant_id: uuid.UUID
    intent: str
    confidence: float
    model_name: str
    outbound_message_id: uuid.UUID | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ReplyClassificationFailed:
    """Classification did not produce a usable result.

    Emitted when:
      - EuriClient raised (budget, all models in fallback chain exhausted).
      - LLM returned malformed output that coerced to "unknown" with confidence < 0.5.

    `error` is a short reason string (e.g. "budget_exceeded", "models_unavailable",
    "malformed_output"); it is NEVER a stack trace or PII.
    """

    inbox_message_id: uuid.UUID
    tenant_id: uuid.UUID
    error: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
