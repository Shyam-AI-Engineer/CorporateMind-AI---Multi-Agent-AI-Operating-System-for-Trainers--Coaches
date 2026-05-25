"""Euri AI Gateway client — the SOLE LLM egress for CorporateMind AI.

Every LLM call in the system goes through this client. Direct imports of
openai, anthropic, google.generativeai, etc. are mechanically blocked outside
this file and apps/api/src/corpmind/ai/providers/*.

Pipeline (in order):
  1. PromptInjectionFilter    — scrubs user/retrieved content
  2. PIIRedactor              — Presidio + regex; substitutes tokens
  3. SemanticCache            — Qdrant cosine ≥ 0.96 (deterministic tasks only)
  4. Routing                  — task → (primary, fallback_chain)
  5. Fallback chain           — primary → secondary → tertiary → local → HITL
  6. OutputModerator          — schema validation + safety filter
  7. Langfuse trace           — per-call observability span
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog

from corpmind.core.config import settings
from corpmind.core.exceptions import BudgetExceededError, ModelUnavailableError
from corpmind.ai.routing import get_model_chain

log = structlog.get_logger(__name__)


class EuriClient:
    """Async LLM client with all gateway pipelines applied."""

    async def chat(
        self,
        *,
        task: str,
        prompt_name: str,
        prompt_inputs: dict[str, Any],
        tenant_id: uuid.UUID,
        request_id: str,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Execute a structured LLM call via the Euri gateway.

        Args:
            task: Task class from routing matrix (e.g. "outreach_copy", "classify_intent").
            prompt_name: Versioned prompt identifier (e.g. "outreach.email.v3").
            prompt_inputs: Template substitution values for the prompt.
            tenant_id: Required for budget checking and tracing.
            request_id: Correlation ID from the HTTP request.
            stream: If True, returns an async generator of chunks (not yet implemented).

        Returns:
            Parsed structured output matching the prompt's output_schema.
        """
        call_id = str(uuid.uuid4())
        start_ms = int(time.monotonic() * 1000)

        # 1. Load prompt from registry
        prompt = await self._load_prompt(prompt_name, prompt_inputs)

        # 2. Prompt injection filter
        prompt = await self._filter_injection(prompt)

        # 3. PII redaction
        prompt, pii_tokens = await self._redact_pii(prompt)

        # 4. Semantic cache check (for deterministic tasks only)
        if self._is_cacheable(task):
            cached = await self._check_semantic_cache(prompt, tenant_id)
            if cached:
                log.info(
                    "llm.cache_hit",
                    task=task,
                    prompt_name=prompt_name,
                    tenant_id=str(tenant_id),
                    request_id=request_id,
                )
                return cached

        # 5. Budget pre-check
        await self._check_budget(tenant_id, task)

        # 6. Model routing + fallback chain
        model_chain = get_model_chain(task)
        result, model_used, tokens_in, tokens_out = await self._call_with_fallback(
            model_chain, prompt, call_id
        )

        # 7. Output moderation
        result = await self._moderate_output(result, task)

        # 8. Reverse PII substitution
        result = await self._restore_pii(result, pii_tokens)

        # 9. Record cost + update budget
        cost_inr = self._estimate_cost_inr(model_used, tokens_in, tokens_out)
        await self._record_usage(
            tenant_id=tenant_id,
            task=task,
            prompt_name=prompt_name,
            model=model_used,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_inr=cost_inr,
            cached=False,
            latency_ms=int(time.monotonic() * 1000) - start_ms,
            request_id=request_id,
        )

        log.info(
            "llm.call_complete",
            task=task,
            model=model_used,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_inr=round(cost_inr, 4),
            request_id=request_id,
        )

        return result

    # ── Private pipeline steps (stubs — implemented in Phase 1) ──────────────

    async def _load_prompt(self, prompt_name: str, inputs: dict[str, Any]) -> str:
        """Load versioned prompt from registry and substitute inputs."""
        # TODO(Phase 1): implement prompt registry lookup
        return str(inputs)

    async def _filter_injection(self, prompt: str) -> str:
        """Apply LLM-Guard prompt injection filter."""
        # TODO(Phase 1): integrate LLM-Guard
        return prompt

    async def _redact_pii(self, prompt: str) -> tuple[str, dict[str, str]]:
        """Presidio PII redaction with token substitution."""
        # TODO(Phase 1): integrate presidio-analyzer
        return prompt, {}

    def _is_cacheable(self, task: str) -> bool:
        """Deterministic-by-input tasks are cacheable; personalized ones are not."""
        _non_cacheable = {"outreach_copy", "proposal_generation", "viral_hooks"}
        return task not in _non_cacheable

    async def _check_semantic_cache(
        self, prompt: str, tenant_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Query global Qdrant prompt cache (cosine ≥ 0.96)."""
        # TODO(Phase 1): integrate Qdrant semantic cache
        return None

    async def _check_budget(self, tenant_id: uuid.UUID, task: str) -> None:
        """Pre-call budget check. Raises BudgetExceededError if over limit."""
        # TODO(Phase 1): query UsageMeter + Subscription
        pass

    async def _call_with_fallback(
        self, model_chain: list[str], prompt: str, call_id: str
    ) -> tuple[dict[str, Any], str, int, int]:
        """Try each model in the fallback chain until one succeeds."""
        for model in model_chain:
            try:
                # TODO(Phase 1): call the Euri HTTP API with the selected model
                return {}, model, 0, 0
            except Exception as exc:
                log.warning("llm.model_failed", model=model, error=str(exc))
                continue

        raise ModelUnavailableError("All models in fallback chain exhausted")

    async def _moderate_output(self, result: dict[str, Any], task: str) -> dict[str, Any]:
        """Apply output schema validation and safety filter."""
        return result

    async def _restore_pii(
        self, result: dict[str, Any], pii_tokens: dict[str, str]
    ) -> dict[str, Any]:
        return result

    def _estimate_cost_inr(self, model: str, tokens_in: int, tokens_out: int) -> float:
        # TODO(Phase 1): implement per-model pricing lookup
        return 0.0

    async def _record_usage(self, **kwargs: Any) -> None:
        """Persist usage to model_runs table and Langfuse."""
        # TODO(Phase 1): write to model_runs + emit Langfuse span
        pass
