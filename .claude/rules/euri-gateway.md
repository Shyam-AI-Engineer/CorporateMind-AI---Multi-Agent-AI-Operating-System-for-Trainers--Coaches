# Euri AI Gateway Rules (Sole LLM Egress)

The Euri AI Gateway is the **only** path from our code to any LLM provider. This rule is mechanically enforced by `.claude/scripts/block-direct-llm-imports.sh` — direct imports of `openai`, `anthropic`, `google.generativeai`, `cohere`, `mistralai`, `litellm` from business modules will block the edit.

## Why this matters
- Vendor lock-in is the #1 cost trap in agentic startups.
- Per-tenant cost telemetry, fallback chains, semantic caching, and PII redaction all live at the gateway. Bypassing it bypasses all of them.

## How to call an LLM
```python
from corpmind.ai.euri_client import EuriClient

client = EuriClient()
result = await client.chat(
    task="outreach_copy",          # routes to model per routing matrix
    prompt_name="outreach.email.v3",
    prompt_inputs={...},
    tenant_id=ctx.tenant_id,       # required — budget + tracing
    request_id=ctx.request_id,     # required — correlation
)
```

## What the client does (in order)
1. **PromptInjectionFilter** — scrubs retrieved/user content.
2. **PIIRedactor** — Presidio + regex; substitutes tokens; reverses only in tenant-scoped post-processing.
3. **SemanticCache** — Qdrant `prompt_cache_global`, cosine ≥ 0.96. Cache only deterministic-by-input tasks (extraction, classification). **Never** cache personalized outreach.
4. **Routing** — `routing.py` maps `task → (primary, fallback_chain)` per task class, tenant plan, budget remaining, latency target.
5. **Fallback chain** — primary → secondary → tertiary → Ollama local → cached/HITL. Every decrement logged with reason.
6. **OutputModerator** — Llama Guard 3 on customer-facing outputs; schema validation on structured outputs.
7. **Trace** — every call emits a Langfuse span with `tenant_id`, `agent`, `prompt_name`, `prompt_version`, `tokens_in`, `tokens_out`, `cost_inr`, `cached`.

## Model selection policy (default routing)
- **Small/cheap** (DeepSeek, Qwen, Gemini Flash, Haiku, Phi): classification, extraction, ranking, dedupe, intent detection.
- **Premium** (Claude Sonnet/Opus, GPT-4-class): personalized outreach, proposal generation, strategic copy, viral hooks.

## Prompts
- Prompts live in `apps/api/src/corpmind/ai/prompts/<name>/v<N>.md` (see `prompt-engineering.md`).
- Never inline prompt strings in business logic. The gateway resolves prompt by `(name, version, env)`.

## Budget
- Pre-call estimator on every call. If `tenant.spent + estimate > tenant.budget`, raises `BudgetExceededError`.
- Soft thresholds 70/85/95% emit notification events.
- See `ai-cost-governance.md` for tier limits.

## Allowlisted gateway internals
- `apps/api/src/corpmind/ai/euri_client.py` and `apps/api/src/corpmind/ai/providers/*` are the only files allowed to import provider SDKs directly. The PreToolUse guard permits these paths.
