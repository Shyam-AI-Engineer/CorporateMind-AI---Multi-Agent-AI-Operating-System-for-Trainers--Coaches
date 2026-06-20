"""WhatsApp Cloud API channel adapter (ADR-0010).

Sends outbound messages via Meta's WhatsApp Business Cloud API and handles
inbound delivery-receipt webhooks.  Template messages are used for cold
outreach (all contacts outside an active 24h session are outside the window,
so only approved templates may be sent).  Free-form messages are permitted
only when WhatsAppService.check_24h_window() confirms an active session.

Retry and circuit-breaker are handled by the Celery send_message task, not
here.  ComplianceGuard runs before send() is called — this adapter trusts
the caller has already passed all compliance gates.

HMAC verification:
  Meta sends X-Hub-Signature-256: sha256=<hex> computed over the raw body
  with WHATSAPP_WEBHOOK_SECRET.  We verify this BEFORE parsing any payload.

Replay protection:
  provider_event_id extracted from each status update is stored in Redis
  with a 24h TTL so duplicate webhook deliveries are dropped silently.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    from starlette.datastructures import Headers

from corpmind.channels.base import (
    DeliveryStatus,
    InboundEvent,
    OutboundMessage,
    SendResult,
)
from corpmind.channels.metrics import channel_send_latency_seconds as _send_latency
from corpmind.channels.metrics import channel_send_total as _send_total
from corpmind.core.config import settings

log = structlog.get_logger(__name__)

# Meta Graph API version — pin explicitly; update on Meta sunset notices.
_API_VERSION = "v20.0"
_GRAPH_BASE = "https://graph.facebook.com"

# Replay-protection TTL for Meta webhook event ids (seconds).
# Meta retries unacknowledged webhooks for up to 24h, so 24h TTL guarantees
# we drop every duplicate within the provider retry window.
_WEBHOOK_EVENT_TTL = 86_400  # 24 hours

# Status values from Meta webhook delivery receipts.
_META_STATUS_MAP: dict[str, DeliveryStatus] = {
    "sent": DeliveryStatus.SENT,
    "delivered": DeliveryStatus.DELIVERED,
    "read": DeliveryStatus.OPENED,
    "failed": DeliveryStatus.FAILED,
}


class WhatsAppCloudAdapter:
    """Meta WhatsApp Business Cloud API channel adapter."""

    name: str = "whatsapp"

    async def send(self, msg: OutboundMessage) -> SendResult:
        """Send a WhatsApp message via Meta Cloud API.

        Uses template-based send when msg.template_id is set (cold outreach).
        Falls back to plain text when template_id is None and an active 24h
        session exists (ComplianceGuard enforces the window check upstream).
        """
        phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        token = settings.WHATSAPP_ACCESS_TOKEN
        url = f"{_GRAPH_BASE}/{_API_VERSION}/{phone_number_id}/messages"

        payload = self._build_payload(msg)

        with _send_latency.labels("whatsapp").time():
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        url,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                    )

                if resp.status_code == 200:
                    data = resp.json()
                    wa_id = (data.get("messages") or [{}])[0].get("id")
                    _send_total.labels("whatsapp", "success").inc()
                    log.info(
                        "whatsapp.sent",
                        message_id=msg.message_id,
                        wa_message_id=wa_id,
                        tenant_id=msg.tenant_id,
                        phone_hash=_short_hash(msg.recipient_address),
                    )
                    return SendResult(success=True, provider_message_id=wa_id)

                error_body = resp.text[:300]
                _send_total.labels("whatsapp", "failed").inc()
                log.error(
                    "whatsapp.send_failed",
                    message_id=msg.message_id,
                    status_code=resp.status_code,
                    error=error_body,
                    tenant_id=msg.tenant_id,
                )
                return SendResult(
                    success=False,
                    error_code=f"http_{resp.status_code}",
                    error_detail=error_body,
                )

            except httpx.TimeoutException as exc:
                _send_total.labels("whatsapp", "timeout").inc()
                log.error(
                    "whatsapp.send_timeout",
                    message_id=msg.message_id,
                    error=str(exc),
                )
                return SendResult(
                    success=False,
                    error_code="timeout",
                    error_detail=str(exc),
                )
            except httpx.RequestError as exc:
                _send_total.labels("whatsapp", "network_error").inc()
                log.error(
                    "whatsapp.send_network_error",
                    message_id=msg.message_id,
                    error=str(exc),
                )
                return SendResult(
                    success=False,
                    error_code="network_error",
                    error_detail=str(exc),
                )

    async def fetch_status(self, message_id: str) -> DeliveryStatus:
        # Delivery status arrives via webhook — Meta has no polling endpoint.
        return DeliveryStatus.SENT

    async def handle_webhook(
        self, payload: bytes, headers: Headers
    ) -> list[InboundEvent]:
        """Parse a Meta webhook for delivery receipt events.

        Verifies X-Hub-Signature-256 BEFORE parsing.  Each status event is
        replay-protected via a Redis NX lock keyed by the Meta event id (24h TTL).
        Inbound messages are intentionally dropped (Sprint 17 scope).
        """
        self._verify_hmac(payload, headers)

        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            log.warning("whatsapp.webhook.invalid_json")
            return []

        events: list[InboundEvent] = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status in value.get("statuses", []):
                    event_id = status.get("id")
                    if event_id and self._is_duplicate(event_id):
                        log.info("whatsapp.webhook.replay_skip", event_id=event_id)
                        continue
                    event = self._parse_status(status, payload)
                    if event:
                        events.append(event)
        return events

    def _is_duplicate(self, event_id: str) -> bool:
        """Return True when this event_id was already processed (replay protection).

        Uses a Redis NX lock with a 24h TTL — mirrors the inbox sync dedup
        pattern.  Returns False when Redis is unavailable (fail-open to avoid
        blocking the entire webhook on a cache outage).
        """
        try:
            import redis as _redis

            r = _redis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                key = f"wa:webhook:event:{event_id}"
                # SET NX: only sets if key does not exist; returns True on set, False on collision.
                was_new = r.set(key, "1", ex=_WEBHOOK_EVENT_TTL, nx=True)
                return not was_new  # duplicate if key already existed (NX returned None/False)
            finally:
                r.close()
        except Exception as exc:
            log.warning("whatsapp.webhook.replay_guard_error", error=str(exc))
            return False  # fail-open

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_payload(self, msg: OutboundMessage) -> dict:
        """Build the Meta API request body.

        Template send: msg.template_id must be set; template variables are
        passed via msg.metadata["template_params"] (list of strings).
        Plain-text send: used when template_id is None (active 24h window).
        """
        recipient = msg.recipient_address  # must be E.164, e.g. +919876543210
        if msg.template_id:
            components: list[dict] = []
            params = msg.metadata.get("template_params", [])
            if params:
                components.append(
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in params],
                    }
                )
            language = msg.metadata.get("template_language", "en")
            return {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "template",
                "template": {
                    "name": msg.template_id,
                    "language": {"code": language},
                    "components": components,
                },
            }
        # Free-form text (inside 24h window only — compliance enforced upstream).
        return {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": msg.body},
        }

    def _parse_status(self, status: dict, raw: bytes) -> InboundEvent | None:
        """Convert a Meta status object to a normalised InboundEvent."""
        event_id = status.get("id") or status.get("message_id")
        if not event_id:
            return None
        meta_status = status.get("status", "")
        delivery_status = _META_STATUS_MAP.get(meta_status, DeliveryStatus.SENT)
        return InboundEvent(
            event_type="delivery_report",
            provider_event_id=event_id,
            provider_message_id=status.get("id"),
            channel="whatsapp",
            recipient_address=status.get("recipient_id"),
            raw_payload=raw,
            metadata={
                "delivery_status": delivery_status.value,
                "timestamp": status.get("timestamp"),
                "errors": status.get("errors", []),
            },
        )

    def _verify_hmac(self, payload: bytes, headers: Headers) -> None:
        """Raise ValueError if the X-Hub-Signature-256 header is invalid."""
        secret = settings.WHATSAPP_WEBHOOK_SECRET
        if not secret:
            # Dev environments may omit the secret; skip verification.
            log.warning("whatsapp.webhook.hmac_secret_not_set")
            return
        header_sig = headers.get("x-hub-signature-256", "")
        if not header_sig.startswith("sha256="):
            raise ValueError("Missing or malformed X-Hub-Signature-256 header")
        expected = "sha256=" + hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, header_sig):
            raise ValueError("X-Hub-Signature-256 mismatch — possible spoofed webhook")


def _short_hash(phone: str) -> str:
    """16-char hex prefix of SHA-256 — safe for logs, not reversible."""
    return hashlib.sha256(phone.encode()).hexdigest()[:16]
