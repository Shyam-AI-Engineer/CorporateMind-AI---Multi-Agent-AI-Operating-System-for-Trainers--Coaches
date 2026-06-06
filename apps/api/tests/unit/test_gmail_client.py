"""Unit tests for the Gmail API client (gmail_client.py).

Uses respx to intercept httpx calls so no live network requests are made.
Covers: message listing, message detail fetching, error dispatch (401/429/5xx),
date parsing edge cases, and Message-ID extraction.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from corpmind.core.exceptions import ValidationError
from corpmind.modules.inbox.gmail_client import (
    GmailMessage,
    GmailMessageSummary,
    _extract_message_id,
    _parse_date,
    get_message,
    list_inbox_messages,
)

ACCESS_TOKEN = "test-access-token"
AUTH_HEADER = f"Bearer {ACCESS_TOKEN}"

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


# ── list_inbox_messages ────────────────────────────────────────────────────────

class TestListInboxMessages:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_summaries_and_no_next_page_token(self):
        respx.get(f"{_GMAIL_BASE}/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "messages": [
                        {"id": "msg-1", "threadId": "thread-1"},
                        {"id": "msg-2", "threadId": "thread-2"},
                    ]
                },
            )
        )

        summaries, next_token = await list_inbox_messages(ACCESS_TOKEN)

        assert len(summaries) == 2
        assert summaries[0].message_id == "msg-1"
        assert summaries[0].thread_id == "thread-1"
        assert next_token is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_next_page_token_when_present(self):
        respx.get(f"{_GMAIL_BASE}/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "messages": [{"id": "msg-1", "threadId": "t-1"}],
                    "nextPageToken": "tok-abc",
                },
            )
        )

        _, next_token = await list_inbox_messages(ACCESS_TOKEN)

        assert next_token == "tok-abc"

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_inbox_returns_empty_list(self):
        respx.get(f"{_GMAIL_BASE}/messages").mock(
            return_value=httpx.Response(200, json={})
        )

        summaries, next_token = await list_inbox_messages(ACCESS_TOKEN)

        assert summaries == []
        assert next_token is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_401_raises_validation_error_about_token(self):
        respx.get(f"{_GMAIL_BASE}/messages").mock(
            return_value=httpx.Response(401, json={"error": "invalid_token"})
        )

        with pytest.raises(ValidationError, match="expired or revoked"):
            await list_inbox_messages(ACCESS_TOKEN)

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_raises_validation_error_about_rate_limit(self):
        respx.get(f"{_GMAIL_BASE}/messages").mock(
            return_value=httpx.Response(429, json={"error": "rateLimitExceeded"})
        )

        with pytest.raises(ValidationError, match="rate limit"):
            await list_inbox_messages(ACCESS_TOKEN)

    @pytest.mark.asyncio
    @respx.mock
    async def test_500_raises_validation_error_with_http_status(self):
        respx.get(f"{_GMAIL_BASE}/messages").mock(
            return_value=httpx.Response(500, json={"error": "internalError"})
        )

        with pytest.raises(ValidationError, match="HTTP 500"):
            await list_inbox_messages(ACCESS_TOKEN)


# ── get_message ────────────────────────────────────────────────────────────────

class TestGetMessage:
    @pytest.mark.asyncio
    @respx.mock
    async def test_extracts_all_standard_headers(self):
        respx.get(f"{_GMAIL_BASE}/messages/msg-123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "msg-123",
                    "threadId": "thread-42",
                    "snippet": "Hi there, replying to your email",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "hr@company.com"},
                            {"name": "Subject", "value": "Re: Training"},
                            {"name": "Date", "value": "Mon, 02 Jun 2025 10:30:00 +0000"},
                            {"name": "Message-ID", "value": "<inbound-msg@mail.example.com>"},
                            {"name": "In-Reply-To", "value": "<outbound-orig@mail.example.com>"},
                            {"name": "References", "value": "<outbound-orig@mail.example.com>"},
                        ]
                    },
                },
            )
        )

        msg = await get_message(ACCESS_TOKEN, "msg-123")

        assert isinstance(msg, GmailMessage)
        assert msg.message_id == "msg-123"
        assert msg.thread_id == "thread-42"
        assert msg.from_address == "hr@company.com"
        assert msg.subject == "Re: Training"
        assert msg.smtp_message_id == "<inbound-msg@mail.example.com>"
        assert msg.in_reply_to == "<outbound-orig@mail.example.com>"
        assert msg.references_header == "<outbound-orig@mail.example.com>"
        assert msg.snippet == "Hi there, replying to your email"

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_missing_optional_headers(self):
        respx.get(f"{_GMAIL_BASE}/messages/msg-no-headers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "msg-no-headers",
                    "threadId": None,
                    "snippet": None,
                    "payload": {"headers": []},
                },
            )
        )

        msg = await get_message(ACCESS_TOKEN, "msg-no-headers")

        assert msg.from_address == ""
        assert msg.subject is None
        assert msg.smtp_message_id is None
        assert msg.in_reply_to is None
        assert msg.references_header is None
        assert isinstance(msg.received_at, datetime)

    @pytest.mark.asyncio
    @respx.mock
    async def test_401_raises_validation_error(self):
        respx.get(f"{_GMAIL_BASE}/messages/msg-x").mock(
            return_value=httpx.Response(401, json={})
        )

        with pytest.raises(ValidationError, match="expired or revoked"):
            await get_message(ACCESS_TOKEN, "msg-x")

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_raises_validation_error(self):
        respx.get(f"{_GMAIL_BASE}/messages/msg-x").mock(
            return_value=httpx.Response(429, json={})
        )

        with pytest.raises(ValidationError, match="rate limit"):
            await get_message(ACCESS_TOKEN, "msg-x")


# ── _parse_date ────────────────────────────────────────────────────────────────

class TestParseDate:
    def test_parses_valid_rfc2822_date(self):
        result = _parse_date("Mon, 02 Jun 2025 10:30:00 +0000")
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 2
        assert result.tzinfo == UTC

    def test_returns_utc_now_for_empty_string(self):
        before = datetime.now(UTC)
        result = _parse_date("")
        after = datetime.now(UTC)
        assert before <= result <= after
        assert result.tzinfo is not None

    def test_returns_utc_now_for_malformed_date(self):
        before = datetime.now(UTC)
        result = _parse_date("not-a-real-date")
        after = datetime.now(UTC)
        assert before <= result <= after


# ── _extract_message_id ────────────────────────────────────────────────────────

class TestExtractMessageId:
    def test_extracts_angle_bracket_message_id(self):
        result = _extract_message_id("<abc123@mail.example.com>")
        assert result == "<abc123@mail.example.com>"

    def test_extracts_from_surrounding_whitespace(self):
        result = _extract_message_id("  <abc123@mail.example.com>  ")
        assert result == "<abc123@mail.example.com>"

    def test_extracts_first_id_from_multi_id_string(self):
        result = _extract_message_id("<first@a.com> <second@b.com>")
        assert result == "<first@a.com>"

    def test_returns_stripped_value_when_no_angle_brackets(self):
        result = _extract_message_id("plain-id-no-brackets")
        assert result == "plain-id-no-brackets"

    def test_returns_none_for_none_input(self):
        assert _extract_message_id(None) is None

    def test_returns_none_for_empty_string(self):
        assert _extract_message_id("") is None

    def test_returns_none_for_whitespace_only(self):
        assert _extract_message_id("   ") is None
