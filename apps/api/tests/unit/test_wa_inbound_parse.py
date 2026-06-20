"""Unit tests for WhatsApp inbound message parsing in WhatsAppCloudAdapter.

Tests handle_webhook() and _parse_inbound_message() for the message_received path.
HMAC verification is bypassed by omitting WHATSAPP_WEBHOOK_SECRET in settings.

Covers:
  handle_webhook — inbound text message
    - text message produces one message_received InboundEvent
    - event fields populated correctly (provider_message_id, from, text_body)
    - context.id present → metadata.context_id populated
    - context absent → metadata.context_id is None
    - contact name extracted from contacts[] array
    - missing contacts[] → contact_name is None

  handle_webhook — non-text message types
    - image skipped (logged, no event returned)
    - video skipped
    - audio skipped
    - sticker skipped
    - document skipped

  handle_webhook — edge cases
    - message with no id field → skipped
    - empty messages[] → no events
    - delivery receipt + text message in same payload → both events returned

  handle_webhook — replay protection
    - duplicate inbound message id → skipped via Redis NX
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from corpmind.channels.whatsapp_cloud import WhatsAppCloudAdapter


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_adapter() -> WhatsAppCloudAdapter:
    return WhatsAppCloudAdapter()


def _make_headers(sig: str = "sha256=abc") -> MagicMock:
    h = MagicMock()
    h.get = lambda key, default="": sig if "signature" in key else default
    return h


def _text_message_payload(
    *,
    msg_id: str = "wamid.inbound.AAA",
    from_phone: str = "+919876543210",
    text: str = "Yes, I'm interested!",
    context_id: str | None = "wamid.outbound.ZZZ",
    contact_name: str | None = "Ravi Kumar",
    msg_type: str = "text",
    phone_number_id: str = "111222333",
) -> bytes:
    message: dict = {
        "from": from_phone,
        "id": msg_id,
        "timestamp": "1750000000",
        "type": msg_type,
    }
    if msg_type == "text":
        message["text"] = {"body": text}
    if context_id:
        message["context"] = {"from": from_phone, "id": context_id}

    contacts = []
    if contact_name:
        contacts.append({"profile": {"name": contact_name}, "wa_id": from_phone})

    body = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_number_id},
                    "contacts": contacts,
                    "messages": [message],
                }
            }]
        }]
    }
    return json.dumps(body).encode()


def _no_duplicate(event_id: str) -> bool:  # noqa: ARG001
    return False  # always first-time


# ── Text message parsing ──────────────────────────────────────────────────────

class TestInboundTextMessageParsing:
    @pytest.mark.asyncio
    async def test_text_message_produces_message_received_event(self):
        adapter = _make_adapter()
        payload = _text_message_payload()
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        assert len(events) == 1
        assert events[0].event_type == "message_received"

    @pytest.mark.asyncio
    async def test_event_has_correct_provider_message_id(self):
        adapter = _make_adapter()
        payload = _text_message_payload(msg_id="wamid.inbound.XYZ")
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        assert events[0].provider_message_id == "wamid.inbound.XYZ"
        assert events[0].provider_event_id == "wamid.inbound.XYZ"

    @pytest.mark.asyncio
    async def test_event_has_sender_phone_number(self):
        adapter = _make_adapter()
        payload = _text_message_payload(from_phone="+917654321098")
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        assert events[0].recipient_address == "+917654321098"

    @pytest.mark.asyncio
    async def test_metadata_text_body_populated(self):
        adapter = _make_adapter()
        payload = _text_message_payload(text="Interested, please share details")
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        assert events[0].metadata["text_body"] == "Interested, please share details"

    @pytest.mark.asyncio
    async def test_context_id_present_in_metadata(self):
        adapter = _make_adapter()
        payload = _text_message_payload(context_id="wamid.outbound.ORIG")
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        assert events[0].metadata["context_id"] == "wamid.outbound.ORIG"

    @pytest.mark.asyncio
    async def test_no_context_id_when_absent(self):
        adapter = _make_adapter()
        payload = _text_message_payload(context_id=None)
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        assert events[0].metadata["context_id"] is None

    @pytest.mark.asyncio
    async def test_contact_name_extracted(self):
        adapter = _make_adapter()
        payload = _text_message_payload(contact_name="Priya Sharma")
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        assert events[0].metadata["contact_name"] == "Priya Sharma"

    @pytest.mark.asyncio
    async def test_contact_name_none_when_contacts_empty(self):
        adapter = _make_adapter()
        payload = _text_message_payload(contact_name=None)
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        assert events[0].metadata["contact_name"] is None

    @pytest.mark.asyncio
    async def test_channel_is_whatsapp(self):
        adapter = _make_adapter()
        payload = _text_message_payload()
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        assert events[0].channel == "whatsapp"


# ── Non-text message types ────────────────────────────────────────────────────

class TestNonTextMessageTypes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("msg_type", ["image", "video", "audio", "sticker", "document"])
    async def test_non_text_type_skipped(self, msg_type: str):
        adapter = _make_adapter()
        payload = _text_message_payload(msg_type=msg_type)
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        # No message_received event emitted for non-text types.
        inbound = [e for e in events if e.event_type == "message_received"]
        assert inbound == [], f"Expected no inbound event for type '{msg_type}'"

    @pytest.mark.asyncio
    async def test_non_text_type_does_not_block_delivery_events(self):
        """A non-text message in the same payload should not suppress delivery receipts."""
        adapter = _make_adapter()
        body = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111"},
                        "contacts": [],
                        "messages": [{"id": "wamid.img", "type": "image", "from": "+91"}],
                        "statuses": [{"id": "wamid.out1", "status": "delivered", "recipient_id": "+91"}],
                    }
                }]
            }]
        }
        payload = json.dumps(body).encode()
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        delivery = [e for e in events if e.event_type == "delivery_report"]
        assert len(delivery) == 1


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_message_with_no_id_is_skipped(self):
        adapter = _make_adapter()
        body = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{"type": "text", "text": {"body": "hi"}, "from": "+91"}]
                        # no "id" field
                    }
                }]
            }]
        }
        payload = json.dumps(body).encode()
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        assert events == []

    @pytest.mark.asyncio
    async def test_empty_messages_array_produces_no_events(self):
        adapter = _make_adapter()
        body = {"entry": [{"changes": [{"value": {"messages": []}}]}]}
        payload = json.dumps(body).encode()
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        assert events == []

    @pytest.mark.asyncio
    async def test_delivery_receipt_and_text_in_same_payload(self):
        adapter = _make_adapter()
        body = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "id": "wamid.in1",
                            "type": "text",
                            "from": "+91",
                            "timestamp": "1234",
                            "text": {"body": "reply"},
                        }],
                        "statuses": [{"id": "wamid.out1", "status": "read", "recipient_id": "+91"}],
                    }
                }]
            }]
        }
        payload = json.dumps(body).encode()
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", side_effect=_no_duplicate),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        types = {e.event_type for e in events}
        assert "message_received" in types
        assert "delivery_report" in types

    @pytest.mark.asyncio
    async def test_duplicate_inbound_message_is_skipped(self):
        adapter = _make_adapter()
        payload = _text_message_payload(msg_id="wamid.dup")
        with (
            patch.object(adapter, "_verify_hmac"),
            patch.object(adapter, "_is_duplicate", return_value=True),
        ):
            events = await adapter.handle_webhook(payload, _make_headers())
        inbound = [e for e in events if e.event_type == "message_received"]
        assert inbound == []

    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty_list(self):
        adapter = _make_adapter()
        with patch.object(adapter, "_verify_hmac"):
            events = await adapter.handle_webhook(b"not json", _make_headers())
        assert events == []
