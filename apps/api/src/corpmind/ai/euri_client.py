"""Euri AI Gateway client — the SOLE LLM egress for CorporateMind AI.

Every LLM call in the system goes through this client. Direct imports of
openai, anthropic, google.generativeai, etc. are mechanically blocked outside
this file and apps/api/src/corpmind/ai/providers/*.

Pipeline (in order):
  1. PromptRegistry          — load versioned prompt + substitute inputs
  2. PromptInjectionFilter   — scrubs user/retrieved content (Phase 2: LLM-Guard)
  3. PIIRedactor             — Presidio + regex (Phase 2: presidio-analyzer)
  4. SemanticCache           — Qdrant cosine ≥ 0.96 (Phase 2: Qdrant)
  5. Budget pre-check        — raises BudgetExceededError if over tenant limit
  6. Routing + fallback      — primary → secondary → tertiary; each model tried
  7. OutputModerator         — schema validation (Phase 2: Llama Guard)
  8. PII restore             — reverse token substitution (Phase 2)
  9. Record usage            — model_runs table + Langfuse span
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from corpmind.core.exceptions import BudgetExceededError, ModelUnavailableError, RateLimitError
from corpmind.ai.models import ModelRun
from corpmind.ai.pricing import estimate_cost_inr
from corpmind.ai.prompt_registry import registry as prompt_registry
from corpmind.ai.providers.euri_http import EuriHTTPProvider, extract_content, extract_usage
from corpmind.ai.routing import get_model_chain
from corpmind.modules.billing.models import Subscription, UsageMeter
from corpmind.modules.billing.repo import UsageMeterRepo

log = structlog.get_logger(__name__)


class EuriClient:
    """Async LLM client with all gateway pipelines applied.

    Args:
        session: Optional AsyncSession for persisting ModelRun records.
                 When None, usage is logged but not written to DB.
                 Callers that have a session (FastAPI deps, Celery tasks) should pass it.
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session
        self._provider = EuriHTTPProvider()

    async def chat(
        self,
        *,
        task: str,
        prompt_name: str,
        prompt_inputs: dict[str, Any],
        tenant_id: uuid.UUID,
        request_id: str,
        agent: str | None = None,
        run_id: str | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Execute a structured LLM call via the Euri gateway.

        Args:
            task: Task class from routing matrix (e.g. "outreach_copy").
            prompt_name: Versioned prompt name (e.g. "outreach.email").
                         Registry resolves to the latest version automatically.
            prompt_inputs: Template substitution values for the prompt.
            tenant_id: Required for budget checking and tracing.
            request_id: Correlation ID from the HTTP request.
            agent: LangGraph agent name (for tracing).
            run_id: Workflow run ID (for tracing).
            stream: Reserved for future streaming support.

        Returns:
            dict with at least {"content": str} from the model.
        """
        if stream:
            raise NotImplementedError("Streaming not yet implemented in EuriClient")

        call_id = str(uuid.uuid4())
        start_ms = int(time.monotonic() * 1000)

        # 1. Load prompt from registry
        prompt_text, prompt_version = prompt_registry.load(prompt_name, prompt_inputs)

        # 2. Prompt injection filter (Phase 2: LLM-Guard)
        prompt_text = self._filter_injection(prompt_text)

        # 3. PII redaction (Phase 2: presidio-analyzer)
        prompt_text, pii_tokens = self._redact_pii(prompt_text)

        # 4. Semantic cache (Phase 2: Qdrant)
        if self._is_cacheable(task):
            cached = await self._check_semantic_cache(prompt_text, tenant_id)
            if cached:
                log.info(
                    "llm.cache_hit",
                    task=task,
                    prompt_name=prompt_name,
                    tenant_id=str(tenant_id),
                    request_id=request_id,
                )
                return cached

        # 5. Budget pre-check (Phase 2: query subscription table)
        await self._check_budget(tenant_id, task)

        # 6. Model routing + fallback chain
        model_chain = get_model_chain(task)
        messages = [{"role": "user", "content": prompt_text}]

        result_text = ""
        model_used = ""
        tokens_in = 0
        tokens_out = 0

        for model in model_chain:
            try:
                response = await self._provider.chat_completion(
                    model=model,
                    messages=messages,
                    call_id=call_id,
                )
                result_text = extract_content(response)
                tokens_in, tokens_out = extract_usage(response)
                model_used = model
                break
            except RateLimitError:
                log.warning("llm.rate_limited", model=model, task=task, call_id=call_id)
                continue
            except Exception as exc:
                log.warning("llm.model_failed", model=model, error=str(exc), call_id=call_id)
                continue

        if not model_used:
            raise ModelUnavailableError("All models in fallback chain exhausted")

        # 7. Output moderation (Phase 2: schema validation + Llama Guard)
        result: dict[str, Any] = {"content": result_text}

        # 8. Reverse PII substitution (Phase 2)
        # pii_tokens is empty until presidio is wired

        # 9. Record cost + update budget
        cost_inr = estimate_cost_inr(model_used, tokens_in, tokens_out)
        latency_ms = int(time.monotonic() * 1000) - start_ms

        await self._record_usage(
            tenant_id=tenant_id,
            task=task,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            model=model_used,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_inr=cost_inr,
            cached=False,
            latency_ms=latency_ms,
            request_id=request_id,
            agent=agent,
            run_id=run_id,
        )

        log.info(
            "llm.call_complete",
            task=task,
            model=model_used,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_inr=round(cost_inr, 4),
            latency_ms=latency_ms,
            request_id=request_id,
        )

        return result

    # ── Pipeline helpers ──────────────────────────────────────────────────────

    def _filter_injection(self, prompt: str) -> str:
        """Phase 2: integrate LLM-Guard prompt injection filter."""
        return prompt

    def _redact_pii(self, prompt: str) -> tuple[str, dict[str, str]]:
        """Phase 2: integrate presidio-analyzer with token substitution."""
        return prompt, {}

    def _is_cacheable(self, task: str) -> bool:
        _non_cacheable = {"outreach_copy", "proposal_generation", "viral_hooks", "social_post"}
        return task not in _non_cacheable

    async def _check_semantic_cache(
        self, _prompt: str, _tenant_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Phase 2: query global Qdrant prompt cache (cosine ≥ 0.96)."""
        return None

    async def _check_budget(self, tenant_id: uuid.UUID, task: str) -> None:
        """Block the call if the tenant has exhausted its AI budget for the period.

        Lookup order:
          1. Active Subscription for tenant_id  → defines ai_budget_inr ceiling.
          2. UsageMeter row(s) for that subscription → ai_spend_inr running total.

        Permissive fall-throughs (logged, not raised):
          - No bound DB session — agent scaffolding paths that aren't yet wired
            into a request scope. Mirrors the policy used by _record_usage().
          - No active subscription — un-billed sandbox/seed tenants. A WARN log
            keeps the gap visible so it can't silently mask a real tenant.

        Strict block:
          - spent >= budget → BudgetExceededError (402, surfaced via the FastAPI
            exception handler installed in main.py).
        """
        if self._session is None:
            log.debug(
                "llm.budget_check_skipped",
                reason="no_session",
                task=task,
                tenant_id=str(tenant_id),
            )
            return

        sub_row = await self._session.execute(
            select(Subscription).where(
                Subscription.tenant_id == tenant_id,
                Subscription.status == "active",
            )
        )
        subscription = sub_row.scalar_one_or_none()
        if subscription is None:
            log.warning(
                "llm.budget_check_skipped",
                reason="no_active_subscription",
                task=task,
                tenant_id=str(tenant_id),
            )
            return

        meter_row = await self._session.execute(
            select(UsageMeter).where(UsageMeter.subscription_id == subscription.id)
        )
        meter = meter_row.scalar_one_or_none()
        spent = meter.ai_spend_inr if meter is not None else 0.0
        budget = subscription.ai_budget_inr

        if spent >= budget:
            log.warning(
                "llm.budget_exceeded",
                task=task,
                tenant_id=str(tenant_id),
                spent_inr=round(spent, 4),
                budget_inr=round(budget, 4),
            )
            raise BudgetExceededError(
                f"AI budget exhausted: ₹{spent:.2f} of ₹{budget:.2f} used this period."
            )

    async def _record_usage(
        self,
        *,
        tenant_id: uuid.UUID,
        task: str,
        prompt_name: str,
        prompt_version: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_inr: float,
        cached: bool,
        latency_ms: int,
        request_id: str,
        agent: str | None,
        run_id: str | None,
    ) -> None:
        if self._session is None:
            return

        run = ModelRun(
            tenant_id=tenant_id,
            task=task,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_inr=cost_inr,
            cached=cached,
            latency_ms=latency_ms,
            request_id=request_id,
            agent=agent,
            run_id=run_id,
        )
        self._session.add(run)

        # Update the running spend meter so _check_budget sees current spend.
        sub_row = await self._session.execute(
            select(Subscription).where(
                Subscription.tenant_id == tenant_id,
                Subscription.status == "active",
            )
        )
        subscription = sub_row.scalar_one_or_none()
        if subscription is not None:
            await UsageMeterRepo(self._session).increment_ai_spend(subscription.id, cost_inr)
