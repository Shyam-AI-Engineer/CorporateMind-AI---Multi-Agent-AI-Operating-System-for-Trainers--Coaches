"""Euri AI Gateway HTTP adapter.

The ONLY file in the system that makes HTTP calls to LLM providers.
Uses the OpenAI-compatible Chat Completions interface exposed by the Euri gateway.
Retry with exponential backoff lives here so EuriClient stays clean.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from corpmind.core.config import settings
from corpmind.core.exceptions import ModelUnavailableError, RateLimitError

log = structlog.get_logger(__name__)

_RETRY_DELAYS = [1.0, 3.0, 9.0]  # seconds; max 3 retries


class EuriHTTPProvider:
    """Thin async HTTP client for the Euri Chat Completions endpoint."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.EURI_API_BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.EURI_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=settings.EURI_TIMEOUT_SECONDS,
        )

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        call_id: str = "",
    ) -> dict[str, Any]:
        """Call the Euri Chat Completions endpoint with retry.

        Returns the raw response dict on success.
        Raises ModelUnavailableError after exhausting retries.
        Raises RateLimitError on 429 so EuriClient can advance the fallback chain.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        for attempt, delay in enumerate([0.0] + _RETRY_DELAYS):
            if delay:
                await asyncio.sleep(delay)
            try:
                resp = await self._client.post("chat/completions", json=payload)

                if resp.status_code == 429:
                    log.warning(
                        "euri.rate_limited",
                        model=model,
                        attempt=attempt,
                        call_id=call_id,
                    )
                    raise RateLimitError(f"Rate limited by Euri gateway on model {model}")

                if resp.status_code >= 500:
                    log.warning(
                        "euri.server_error",
                        model=model,
                        status=resp.status_code,
                        attempt=attempt,
                        call_id=call_id,
                    )
                    continue  # retry on 5xx

                resp.raise_for_status()
                return resp.json()

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                log.warning(
                    "euri.network_error",
                    model=model,
                    attempt=attempt,
                    error=str(exc),
                    call_id=call_id,
                )
                if attempt == len(_RETRY_DELAYS):
                    raise ModelUnavailableError(f"Network error after retries: {exc}") from exc

        raise ModelUnavailableError(f"Model {model} unavailable after {len(_RETRY_DELAYS)} retries")

    async def vision_describe(
        self,
        image_url: str,
        *,
        instruction: str = "Extract all text and describe what you see in this image.",
        call_id: str = "",
    ) -> str:
        """Call Euri with a vision (image_url) message and return the text response.

        Uses GPT-4o — the only model in our Euri account confirmed to support vision.
        Bypass the EuriClient pipeline (no prompt registry, no PII redaction) because:
          - The image URL is already a signed Cloudinary URL, not user-typed text
          - The response is raw OCR/description, not outbound copy
        Phase 2: wire PII redaction over the description before returning.
        """
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
                ],
            }
        ]
        response = await self.chat_completion(
            model="openai/gpt-4o",
            messages=messages,
            temperature=0.0,
            max_tokens=2048,
            call_id=call_id,
        )
        return extract_content(response)

    async def aclose(self) -> None:
        await self._client.aclose()


def extract_content(response: dict[str, Any]) -> str:
    """Extract the assistant message text from an OpenAI-compatible response."""
    choices = response.get("choices", [])
    if not choices:
        raise ModelUnavailableError("Empty choices in Euri response")
    content = choices[0]["message"]["content"]
    if content is None:
        raise ModelUnavailableError("Model returned null content (possible content-filter block)")
    return content


def extract_usage(response: dict[str, Any]) -> tuple[int, int]:
    """Return (prompt_tokens, completion_tokens) from the usage block."""
    usage = response.get("usage", {})
    return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
