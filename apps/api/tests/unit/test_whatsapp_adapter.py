"""Unit tests for WhatsAppCloudAdapter."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import Headers

from corpmind.channels.whatsapp_cloud import WhatsAppCloudAdapter
from corpmind.channels.base import DeliveryStatus, OutboundMessage


def _make_msg(template_id: str | None = "outreach_intro_v1") -> OutboundMessage:
    return OutboundMessage(
        message_id="msg-001",
        recipient_id="contact-uuid",
        recipient_address="+919876543210",
        channel="whatsapp",
        subject=None,
        body="Hi Priya, open to a chat?",
        template_id=template_id,
        tenant_id="tenant-uuid",
        request_id="req-001",
        metadata={"template_language": "en", "template_params": []},
    )


class TestWhatsAppCloudAdapterSend:
    def test_name_is_whatsapp(self):
        assert WhatsAppCloudAdapter.name == "whatsapp"

    @pytest.mark.asyncio
    async def test_send_template_success(self):
        adapter = WhatsAppCloudAdapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"messages": [{"id": "wamid.abc123"}]}

        with patch("corpmind.channels.whatsapp_cloud.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await adapter.send(_make_msg())

        assert result.success is True
        assert result.provider_message_id == "wamid.abc123"

    @pytest.mark.asyncio
    async def test_send_template_payload_shape(self):
        """Template send must include messaging_product and template block."""
        adapter = WhatsAppCloudAdapter()
        captured: list[dict] = []

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"messages": [{"id": "wamid.x"}]}

        async def capture_post(url, *, json, headers):  # noqa: ARG001
            captured.append(json)
            return mock_resp

        with patch("corpmind.channels.whatsapp_cloud.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = capture_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            await adapter.send(_make_msg(template_id="outreach_intro_v1"))

        payload = captured[0]
        assert payload["messaging_product"] == "whatsapp"
        assert payload["type"] == "template"
        assert payload["template"]["name"] == "outreach_intro_v1"

    @pytest.mark.asyncio
    async def test_send_freeform_payload_when_no_template(self):
        adapter = WhatsAppCloudAdapter()
        captured: list[dict] = []

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"messages": [{"id": "wamid.y"}]}

        async def capture_post(url, *, json, headers):  # noqa: ARG001
            captured.append(json)
            return mock_resp

        with patch("corpmind.channels.whatsapp_cloud.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = capture_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            await adapter.send(_make_msg(template_id=None))

        payload = captured[0]
        assert payload["type"] == "text"
        assert "body" in payload["text"]

    @pytest.mark.asyncio
    async def test_send_returns_failure_on_non_200(self):
        adapter = WhatsAppCloudAdapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"

        with patch("corpmind.channels.whatsapp_cloud.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await adapter.send(_make_msg())

        assert result.success is False
        assert result.error_code == "http_400"

    @pytest.mark.asyncio
    async def test_fetch_status_returns_sent(self):
        adapter = WhatsAppCloudAdapter()
        status = await adapter.fetch_status("wamid.abc")
        assert status == DeliveryStatus.SENT


class TestWhatsAppWebhookHMAC:
    def _sign(self, payload: bytes, secret: str) -> str:
        return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    @pytest.mark.asyncio
    async def test_valid_signature_passes(self):
        adapter = WhatsAppCloudAdapter()
        payload = b'{"object":"whatsapp_business_account","entry":[]}'
        secret = "test-secret"
        sig = self._sign(payload, secret)

        with patch("corpmind.channels.whatsapp_cloud.settings") as mock_settings:
            mock_settings.WHATSAPP_WEBHOOK_SECRET = secret
            events = await adapter.handle_webhook(payload, Headers({"x-hub-signature-256": sig}))

        assert events == []

    @pytest.mark.asyncio
    async def test_invalid_signature_raises(self):
        adapter = WhatsAppCloudAdapter()
        payload = b'{"object":"whatsapp_business_account","entry":[]}'

        with patch("corpmind.channels.whatsapp_cloud.settings") as mock_settings:
            mock_settings.WHATSAPP_WEBHOOK_SECRET = "correct-secret"
            with pytest.raises(ValueError, match="mismatch"):
                await adapter.handle_webhook(
                    payload,
                    Headers({"x-hub-signature-256": "sha256=wronghash"}),
                )

    @pytest.mark.asyncio
    async def test_missing_signature_header_raises(self):
        adapter = WhatsAppCloudAdapter()
        payload = b'{"object":"test","entry":[]}'

        with patch("corpmind.channels.whatsapp_cloud.settings") as mock_settings:
            mock_settings.WHATSAPP_WEBHOOK_SECRET = "secret"
            with pytest.raises(ValueError, match="Missing or malformed"):
                await adapter.handle_webhook(payload, Headers({}))

    @pytest.mark.asyncio
    async def test_delivery_receipt_parsed(self):
        adapter = WhatsAppCloudAdapter()
        secret = "s3cr3t"
        body = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA-ID",
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "wamid.123",
                                        "status": "delivered",
                                        "timestamp": "1700000000",
                                        "recipient_id": "+919876543210",
                                    }
                                ]
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        payload = json.dumps(body).encode()
        sig = self._sign(payload, secret)

        with patch("corpmind.channels.whatsapp_cloud.settings") as mock_settings:
            mock_settings.WHATSAPP_WEBHOOK_SECRET = secret
            events = await adapter.handle_webhook(payload, Headers({"x-hub-signature-256": sig}))

        assert len(events) == 1
        assert events[0].event_type == "delivery_report"
        assert events[0].metadata["delivery_status"] == "delivered"
