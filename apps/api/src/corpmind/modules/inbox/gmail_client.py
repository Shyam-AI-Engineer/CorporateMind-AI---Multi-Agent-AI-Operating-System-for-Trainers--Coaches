"""Gmail API client — message listing and header extraction for inbox sync.

Requires: gmail.readonly scope on the supplied access token.

All public functions raise ValidationError on:
  - HTTP 401  — token expired or revoked; caller should refresh/revoke.
  - HTTP 429  — rate limited; Celery task should retry with backoff.
  - Other non-200 — transient provider error; retryable.

This module does NOT manage OAuth state.  Callers are expected to hold a
fresh access token before invoking any function here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
import structlog

from corpmind.core.exceptions import ValidationError

log = structlog.get_logger(__name__)

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
_DEFAULT_TIMEOUT = 30.0

# Only these headers are fetched per message (format=metadata).
# Avoids downloading the full body, saving bandwidth and quota units.
_METADATA_HEADERS = ["From", "Subject", "Date", "Message-ID", "In-Reply-To", "References"]


# ── Data types ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GmailMessageSummary:
    """Minimal data returned by messages.list — no headers yet."""

    message_id: str
    thread_id: str | None
    snippet: str | None  # Gmail's own short preview (~100 chars plain text)


@dataclass(frozen=True)
class GmailMessage:
    """Full message data with extracted headers — returned by messages.get."""

    message_id: str
    thread_id: str | None
    snippet: str | None
    from_address: str
    subject: str | None
    received_at: datetime
    # Message-ID header of this inbound message (its own identity).
    smtp_message_id: str | None
    # In-Reply-To header — the Message-ID of the email this is a reply to.
    # When non-null, this typically matches an outbound_messages.smtp_message_id.
    in_reply_to: str | None
    # Raw References header (space-separated chain of ancestor Message-IDs).
    references_header: str | None


# ── API calls ──────────────────────────────────────────────────────────────────

async def list_inbox_messages(
    access_token: str,
    *,
    max_results: int = 100,
    page_token: str | None = None,
    newer_than_days: int = 7,
) -> tuple[list[GmailMessageSummary], str | None]:
    """List recent INBOX messages.

    Returns (summaries, next_page_token).  next_page_token is None when
    there are no further pages.  Summaries include message_id, thread_id,
    and the Gmail-provided snippet (~100 char plain-text preview).

    Raises:
        ValidationError: On 401 (expired/revoked token), 429 (rate limited),
                         or any other non-200 response.
    """
    params: dict[str, object] = {
        "maxResults": max_results,
        "labelIds": "INBOX",
        "q": f"newer_than:{newer_than_days}d",
    }
    if page_token:
        params["pageToken"] = page_token

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            f"{_GMAIL_BASE}/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )

    _raise_for_gmail_error(resp, "messages.list")

    data = resp.json()
    summaries = [
        GmailMessageSummary(
            message_id=m["id"],
            thread_id=m.get("threadId"),
            snippet=m.get("snippet"),
        )
        for m in data.get("messages", [])
    ]
    return summaries, data.get("nextPageToken")


async def get_message(access_token: str, message_id: str) -> GmailMessage:
    """Fetch a single message with extracted metadata headers.

    Uses format=metadata so only the headers in _METADATA_HEADERS are
    returned — no body download, no base64 decoding.

    Raises:
        ValidationError: On 401, 429, or other non-200 response.
    """
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            f"{_GMAIL_BASE}/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "format": "metadata",
                "metadataHeaders": _METADATA_HEADERS,
            },
        )

    _raise_for_gmail_error(resp, "messages.get")

    data = resp.json()
    headers = {
        h["name"]: h["value"]
        for h in data.get("payload", {}).get("headers", [])
    }

    return GmailMessage(
        message_id=message_id,
        thread_id=data.get("threadId"),
        snippet=data.get("snippet") or None,
        from_address=headers.get("From", ""),
        subject=headers.get("Subject") or None,
        received_at=_parse_date(headers.get("Date", "")),
        smtp_message_id=_extract_message_id(headers.get("Message-ID")),
        in_reply_to=_extract_message_id(headers.get("In-Reply-To")),
        references_header=headers.get("References") or None,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _raise_for_gmail_error(resp: httpx.Response, operation: str) -> None:
    if resp.status_code == 200:
        return
    log.warning(
        "gmail_client.api_error",
        operation=operation,
        http_status=resp.status_code,
    )
    if resp.status_code == 401:
        raise ValidationError("Gmail access token expired or revoked")
    if resp.status_code == 429:
        raise ValidationError("Gmail API rate limit exceeded — retry after backoff")
    raise ValidationError(f"Gmail API error on {operation}: HTTP {resp.status_code}")


def _parse_date(raw: str) -> datetime:
    """Parse an RFC 2822 Date header value to a UTC-aware datetime.

    Falls back to the current UTC time on any parse failure so a malformed
    Date header never prevents a message from being persisted.
    """
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(UTC).replace(tzinfo=UTC)
        except Exception:
            pass
    return datetime.now(UTC)


def _extract_message_id(value: str | None) -> str | None:
    """Extract the first angle-bracket-delimited Message-ID from a header value.

    Returns the raw stripped value when no angle-bracket pair is found
    (non-compliant headers), or None when the value is absent or blank.
    """
    if not value:
        return None
    match = re.search(r"<[^>]+>", value)
    if match:
        return match.group(0)
    stripped = value.strip()
    return stripped if stripped else None
