"""Unit tests for WhatsApp module API routes.

Uses httpx AsyncClient + FastAPI ASGITransport against a minimal test app —
no real DB, Redis, or Meta API. All side-effecting code is patched.

Covers:
  GET /templates
    - empty list → {items: [], total: 0}
    - two templates → total == 2, items match schema shape
    - items have expected fields

  GET /webhook (Meta challenge verification)
    - correct verify_token → 200, body == int(hub.challenge)
    - wrong verify_token → 403
    - missing hub.verify_token → 403

  POST /webhook
    - handle_webhook raises ValueError (invalid HMAC) → 401
    - adapter returns empty event list → {status: ok, processed: 0}
    - adapter returns one delivery_report event → {status: ok, processed: 1}
    - event with no provider_message_id → not processed (processed == 0)
    - event.event_type != 'delivery_report' → skipped (processed == 0)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from corpmind.modules.whatsapp.api import router
from corpmind.modules.whatsapp.schemas import WhatsAppTemplateListOut, WhatsAppTemplateOut


# ── Test app factory ───────────────────────────────────────────────────────────

def _make_app(get_session_override=None) -> FastAPI:
    from corpmind.core.database import get_session

    app = FastAPI()
    app.include_router(router)
    if get_session_override is not None:
        app.dependency_overrides[get_session] = get_session_override
    return app


def _mock_session() -> MagicMock:
    s = MagicMock()
    s.commit = AsyncMock()
    return s


def _make_template_out(name: str = "hello", language: str = "en") -> WhatsAppTemplateOut:
    return WhatsAppTemplateOut(
        id=uuid.uuid4(),
        name=name,
        language=language,
        category="MARKETING",
        body="Hello {{1}}",
        approval_status="approved",
        meta_template_id="12345",
        created_at=datetime.now(UTC),
    )


# ── GET /templates ─────────────────────────────────────────────────────────────

class TestListTemplates:
    @pytest.mark.asyncio
    async def test_empty_list_returns_zero_total(self):
        session = _mock_session()
        app = _make_app(lambda: session)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch(
                "corpmind.modules.whatsapp.service.WhatsAppService.list_approved_templates",
                AsyncMock(return_value=[]),
            ):
                resp = await client.get("/templates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_two_templates_returns_total_two(self):
        templates = [_make_template_out("t1"), _make_template_out("t2")]
        session = _mock_session()
        app = _make_app(lambda: session)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch(
                "corpmind.modules.whatsapp.service.WhatsAppService.list_approved_templates",
                AsyncMock(return_value=templates),
            ):
                resp = await client.get("/templates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    @pytest.mark.asyncio
    async def test_items_have_expected_fields(self):
        t = _make_template_out("welcome", "hi")
        session = _mock_session()
        app = _make_app(lambda: session)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch(
                "corpmind.modules.whatsapp.service.WhatsAppService.list_approved_templates",
                AsyncMock(return_value=[t]),
            ):
                resp = await client.get("/templates")
        item = resp.json()["items"][0]
        assert item["name"] == "welcome"
        assert item["language"] == "hi"
        assert item["approval_status"] == "approved"
        assert "id" in item
        assert "created_at" in item


# ── GET /webhook (Meta challenge) ─────────────────────────────────────────────

class TestWebhookChallenge:
    @pytest.mark.asyncio
    async def test_correct_verify_token_returns_challenge_as_int(self):
        app = _make_app()
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("corpmind.core.config.settings") as mock_settings:
                mock_settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN = "secret123"
                resp = await client.get(
                    "/webhook",
                    params={
                        "hub.verify_token": "secret123",
                        "hub.challenge": "98765",
                        "hub.mode": "subscribe",
                    },
                )
        assert resp.status_code == 200
        assert resp.json() == 98765

    @pytest.mark.asyncio
    async def test_wrong_verify_token_returns_403(self):
        app = _make_app()
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("corpmind.core.config.settings") as mock_settings:
                mock_settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN = "secret123"
                resp = await client.get(
                    "/webhook",
                    params={
                        "hub.verify_token": "wrong_token",
                        "hub.challenge": "12345",
                    },
                )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_verify_token_returns_403(self):
        app = _make_app()
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("corpmind.core.config.settings") as mock_settings:
                mock_settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN = "secret123"
                resp = await client.get(
                    "/webhook",
                    params={"hub.challenge": "12345"},
                )
        assert resp.status_code == 403


# ── POST /webhook ─────────────────────────────────────────────────────────────

def _make_inbound_event(
    *,
    event_type: str = "delivery_report",
    provider_message_id: str | None = "wamid.abc",
    delivery_status: str = "delivered",
) -> MagicMock:
    from corpmind.channels.base import InboundEvent
    event = MagicMock(spec=InboundEvent)
    event.event_type = event_type
    event.provider_message_id = provider_message_id
    event.provider_event_id = "evt-001"
    event.metadata = {"delivery_status": delivery_status}
    return event


async def _async_session_gen():
    """Async generator that yields a mock session — replaces get_public_session."""
    session = MagicMock()
    session.commit = AsyncMock()
    yield session


class TestPostWebhook:
    @pytest.mark.asyncio
    async def test_invalid_hmac_returns_401(self):
        mock_adapter = MagicMock()
        mock_adapter.handle_webhook = AsyncMock(side_effect=ValueError("HMAC mismatch"))
        app = _make_app()
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("corpmind.channels.registry.get", return_value=mock_adapter):
                resp = await client.post("/webhook", content=b"{}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_no_events_returns_processed_zero(self):
        mock_adapter = MagicMock()
        mock_adapter.handle_webhook = AsyncMock(return_value=[])
        app = _make_app()
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("corpmind.channels.registry.get", return_value=mock_adapter):
                resp = await client.post("/webhook", content=b"{}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["processed"] == 0

    @pytest.mark.asyncio
    async def test_one_delivery_event_processed(self):
        event = _make_inbound_event(provider_message_id="wamid.xyz", delivery_status="delivered")

        mock_adapter = MagicMock()
        mock_adapter.handle_webhook = AsyncMock(return_value=[event])

        mock_repo_instance = MagicMock()
        mock_repo_instance.update_status_by_provider_id = AsyncMock()

        app = _make_app()
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with (
                patch("corpmind.channels.registry.get", return_value=mock_adapter),
                patch("corpmind.modules.whatsapp.api.get_public_session", _async_session_gen),
                patch(
                    "corpmind.modules.outreach.repo.OutboundMessageRepo",
                    return_value=mock_repo_instance,
                ),
            ):
                resp = await client.post("/webhook", content=b'{"object":"whatsapp_business_account"}')

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["processed"] == 1
        mock_repo_instance.update_status_by_provider_id.assert_awaited_once_with(
            "wamid.xyz", "delivered"
        )

    @pytest.mark.asyncio
    async def test_event_with_no_provider_message_id_is_skipped(self):
        event = _make_inbound_event(provider_message_id=None)

        mock_adapter = MagicMock()
        mock_adapter.handle_webhook = AsyncMock(return_value=[event])

        mock_repo_instance = MagicMock()
        mock_repo_instance.update_status_by_provider_id = AsyncMock()

        app = _make_app()
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with (
                patch("corpmind.channels.registry.get", return_value=mock_adapter),
                patch("corpmind.modules.whatsapp.api.get_public_session", _async_session_gen),
                patch(
                    "corpmind.modules.outreach.repo.OutboundMessageRepo",
                    return_value=mock_repo_instance,
                ),
            ):
                resp = await client.post("/webhook", content=b"{}")

        assert resp.status_code == 200
        assert resp.json()["processed"] == 0
        mock_repo_instance.update_status_by_provider_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_delivery_report_event_is_skipped(self):
        """event_type other than 'delivery_report' must not be written to DB."""
        event = _make_inbound_event(event_type="inbound_message", provider_message_id="wamid.abc")

        mock_adapter = MagicMock()
        mock_adapter.handle_webhook = AsyncMock(return_value=[event])

        mock_repo_instance = MagicMock()
        mock_repo_instance.update_status_by_provider_id = AsyncMock()

        app = _make_app()
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with (
                patch("corpmind.channels.registry.get", return_value=mock_adapter),
                patch("corpmind.modules.whatsapp.api.get_public_session", _async_session_gen),
                patch(
                    "corpmind.modules.outreach.repo.OutboundMessageRepo",
                    return_value=mock_repo_instance,
                ),
            ):
                resp = await client.post("/webhook", content=b"{}")

        assert resp.status_code == 200
        assert resp.json()["processed"] == 0
        mock_repo_instance.update_status_by_provider_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_read_status_event_processed_correctly(self):
        event = _make_inbound_event(
            provider_message_id="wamid.read",
            delivery_status="opened",
        )
        mock_adapter = MagicMock()
        mock_adapter.handle_webhook = AsyncMock(return_value=[event])

        mock_repo_instance = MagicMock()
        mock_repo_instance.update_status_by_provider_id = AsyncMock()

        app = _make_app()
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with (
                patch("corpmind.channels.registry.get", return_value=mock_adapter),
                patch("corpmind.modules.whatsapp.api.get_public_session", _async_session_gen),
                patch(
                    "corpmind.modules.outreach.repo.OutboundMessageRepo",
                    return_value=mock_repo_instance,
                ),
            ):
                resp = await client.post("/webhook", content=b"{}")

        assert resp.json()["processed"] == 1
        mock_repo_instance.update_status_by_provider_id.assert_awaited_once_with(
            "wamid.read", "opened"
        )
