# ADR-0002: Euri as Sole LLM Egress

- **Status:** Accepted
- **Date:** 2026-05-25
- **Deciders:** Shyam (Founder/CTO), AI Architect

## Context

CorporateMind AI makes LLM calls from 14 specialized agents across multiple task classes (extraction, classification, personalized copy, proposal generation). Without a centralized gateway, each agent or service would import provider SDKs directly, leading to:

- **No per-tenant cost telemetry** — impossible to bill per tenant or enforce budgets.
- **Vendor lock-in** — switching providers requires touching every LLM call site.
- **No fallback chains** — if OpenAI is down, the entire system degrades with no recovery path.
- **No PII redaction** — sensitive contact data may reach the model's API in plaintext.
- **No semantic caching** — identical calls re-billed instead of served from Qdrant cache.
- **No centralized output moderation** — Llama Guard 3 bypass per-agent instead of enforced uniformly.

The Euri AI Gateway is a purpose-built AI gateway from Euri.ai that provides these capabilities.

## Decision

**All LLM calls route through `corpmind.ai.euri_client.EuriClient`. Direct imports of `openai`, `anthropic`, `google.generativeai`, `cohere`, `mistralai`, and `litellm` are forbidden in business modules and mechanically enforced by `.claude/scripts/block-direct-llm-imports.sh` (PreToolUse hook).**

The EuriClient pipeline (in order):
1. PromptInjectionFilter — scrubs user/retrieved content.
2. PIIRedactor — Presidio + regex; tokens reversed in tenant-scoped post-processing only.
3. SemanticCache — Qdrant `prompt_cache_global`, cosine ≥ 0.96. Never caches personalized outreach.
4. Routing matrix — `task → (primary, fallback_chain)` based on tenant plan, budget, latency target.
5. Fallback chain — primary → secondary → tertiary → Ollama local → cached/HITL.
6. OutputModerator — Llama Guard 3 on customer-facing outputs; schema validation on structured outputs.
7. Langfuse span — tenant, agent, prompt_name, tokens, cost_inr, cached.

**Allowlisted paths** (exempt from the import block):
- `apps/api/src/corpmind/ai/euri_client.py`
- `apps/api/src/corpmind/ai/providers/*`

## Alternatives Considered

**1. Direct provider SDKs per agent**
- `+` No abstraction overhead; simplest to start.
- `-` Each provider switch touches every LLM call site. No central telemetry. No fallback. No per-tenant budget enforcement. Rejected: creates exactly the lock-in and cost opacity we cannot afford.

**2. LiteLLM as the router (self-managed)**
- `+` Open-source, provider-agnostic, handles many providers.
- `-` Self-hosting LiteLLM adds infra overhead. No native per-tenant telemetry. No semantic caching. Would require significant custom middleware to match Euri's feature set. Euri provides this out of the box with less operational burden.

**3. Direct Euri API calls without the EuriClient wrapper**
- `+` Slightly fewer abstraction layers.
- `-` Every call site must manage PIIRedactor, SemanticCache, and Langfuse span manually — duplication and inconsistency risk.

## Consequences

**Positive:**
- Every LLM call gets: cost telemetry, PII redaction, semantic cache, fallback chain, output moderation, Langfuse tracing — automatically.
- Provider migrations are a routing matrix config change, not a code change.
- Per-tenant budget enforcement is structurally guaranteed.
- Mechanical import guard prevents accidental bypass.

**Negative:**
- All LLM calls now have a dependency on the EuriClient singleton; local development requires the client to be mockable/stubable.
- The allowlist in `block-direct-llm-imports.sh` must be manually maintained if new gateway files are added.
- Euri AI Gateway availability becomes a dependency — circuit breaker + local Ollama fallback mitigates this.

**Neutral:**
- `routing.py` (the task→model routing matrix) lives in `apps/api/src/corpmind/ai/` and is version-controlled. Adding a new task class to the routing matrix requires an ADR.

## References

- `.claude/rules/euri-gateway.md` — full usage rules
- `.claude/rules/ai-cost-governance.md` — per-tenant budget enforcement
- `.claude/scripts/block-direct-llm-imports.sh` — mechanical enforcement
- Supersedes: N/A
- Superseded by: N/A
