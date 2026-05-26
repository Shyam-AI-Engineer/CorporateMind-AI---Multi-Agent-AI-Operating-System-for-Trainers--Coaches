"""Email SMTP channel adapter.

Uses aiosmtplib for async SMTP delivery.  Config is driven by pydantic-settings.
ComplianceGuard runs BEFORE send() — this adapter trusts the caller has already
passed the compliance gate.

Retry (exponential backoff) and circuit-breaker are handled by the Celery task
that calls this adapter, not by the adapter itself.
"""

from __future__ import annotations

import email.utils
import hashlib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import structlog
from prometheus_client import Counter, Histogram
from starlette.datastructures import Headers

from corpmind.channels.base import (
    DeliveryStatus,
    InboundEvent,
    OutboundMessage,
    SendResult,
)
from corpmind.core.config import settings

log = structlog.get_logger(__name__)

_send_total = Counter(
    "channel_send_total",
    "Total send attempts per channel",
    ["channel", "status"],
)
_send_latency = Histogram(
    "channel_send_latency_seconds",
    "Outbound send latency per channel",
    ["channel"],
)


class EmailSMTPAdapter:
    """Async SMTP adapter for transactional and outreach emails."""

    name: str = "email"

    async def send(self, msg: OutboundMessage) -> SendResult:
        mime = self._build_mime(msg)
        with _send_latency.labels("email").time():
            try:
                await aiosmtplib.send(
                    mime,
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    username=settings.SMTP_USERNAME,
                    password=settings.SMTP_PASSWORD,
                    use_tls=settings.SMTP_USE_TLS,
                    start_tls=False,
                )
                provider_id = mime.get("Message-ID", "")
                _send_total.labels("email", "success").inc()
                log.info(
                    "email.sent",
                    message_id=msg.message_id,
                    recipient_hash=_short_hash(msg.recipient_address),
                    tenant_id=msg.tenant_id,
                )
                return SendResult(success=True, provider_message_id=provider_id)

            except (aiosmtplib.SMTPException, OSError) as exc:
                _send_total.labels("email", "failed").inc()
                log.error(
                    "email.send_failed",
                    message_id=msg.message_id,
                    error=str(exc),
                    tenant_id=msg.tenant_id,
                )
                return SendResult(
                    success=False,
                    error_code="smtp_error",
                    error_detail=str(exc),
                )

    async def fetch_status(self, message_id: str) -> DeliveryStatus:  # noqa: ARG002
        # SMTP has no polling API; delivery confirmation arrives via bounce-back
        # parsing (MX listener — Phase 2).  Safe default is SENT.
        return DeliveryStatus.SENT

    async def handle_webhook(
        self, payload: bytes, headers: Headers  # noqa: ARG002
    ) -> list[InboundEvent]:
        # SMTP bounce/complaint callbacks are handled by a dedicated MX parser
        # (Phase 2).  Return empty list so existing callers don't break.
        return []

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_mime(self, msg: OutboundMessage) -> MIMEMultipart:
        mime = MIMEMultipart("alternative")
        mime["Subject"] = msg.subject or "(no subject)"
        from_addr = settings.SMTP_FROM_ADDRESS
        mime["From"] = email.utils.formataddr(("CorporateMind AI", from_addr))
        mime["To"] = msg.recipient_address
        # Deterministic Message-ID so duplicate sends produce the same ID (idempotent).
        domain = from_addr.split("@")[-1]
        mime["Message-ID"] = f"<{msg.message_id}@{domain}>"
        mime.attach(MIMEText(msg.body, "plain", "utf-8"))
        return mime


def _short_hash(address: str) -> str:
    """16-char hex prefix of SHA-256 — safe for logs, not reversible."""
    return hashlib.sha256(address.encode()).hexdigest()[:16]
