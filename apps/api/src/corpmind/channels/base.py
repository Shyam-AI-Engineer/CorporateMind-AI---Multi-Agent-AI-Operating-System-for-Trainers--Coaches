"""ChannelAdapter ABC — the common interface for all 6 outbound channels.

Every channel (Email, WhatsApp, Telegram, Instagram, Facebook, LinkedIn)
implements this protocol. Provider SDKs are isolated here and nowhere else.

ComplianceGuard runs BEFORE send() is called — the adapter trusts that
the caller has already passed the compliance gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from starlette.datastructures import Headers


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    REPLIED = "replied"
    BOUNCED = "bounced"
    FAILED = "failed"


class BounceType(StrEnum):
    HARD = "hard"
    SOFT = "soft"
    SPAM_COMPLAINT = "spam_complaint"


@dataclass(frozen=True)
class OutboundMessage:
    """Normalized outbound message for any channel."""

    message_id: str
    recipient_id: str          # internal contact UUID
    recipient_address: str     # email / phone / channel-specific ID
    channel: str
    subject: str | None        # email only
    body: str
    template_id: str | None    # WhatsApp template
    tenant_id: str
    request_id: str
    metadata: dict             # channel-specific extras


@dataclass(frozen=True)
class SendResult:
    """Result of a send() call."""

    success: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None


@dataclass(frozen=True)
class InboundEvent:
    """Normalized inbound event from a channel webhook."""

    event_type: str            # message_received | delivery_report | bounce | reply
    provider_event_id: str
    provider_message_id: str | None
    channel: str
    recipient_address: str | None
    raw_payload: bytes
    metadata: dict


class ChannelAdapter(Protocol):
    """Protocol (structural subtyping) for channel adapters."""

    name: str

    async def send(self, msg: OutboundMessage) -> SendResult:
        """Send a single message. Retry is handled by the caller (Celery task)."""
        ...

    async def fetch_status(self, message_id: str) -> DeliveryStatus:
        """Poll delivery status for a sent message."""
        ...

    async def handle_webhook(
        self, payload: bytes, headers: Headers
    ) -> list[InboundEvent]:
        """Parse and validate an inbound webhook payload.

        MUST verify HMAC/signature BEFORE parsing. Must be idempotent.
        Returns a list of normalized inbound events.
        """
        ...
