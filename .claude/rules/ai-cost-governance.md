# AI Cost Governance

LLM spend is the dominant variable cost of this product. Cost discipline is a feature, not an afterthought.

## What every agent run records
For every LLM call, persist (and mirror to Langfuse):
- `prompt_tokens`, `completion_tokens`, `latency_ms`
- `estimated_cost_inr`
- `model` (the actual model that served the request — primary, fallback, or local)
- `cached: bool`
- `tenant_id`, `agent`, `prompt_name`, `prompt_version`
- `request_id` (correlation)

Stored in `model_runs` table; queryable per tenant per day for billing reconciliation.

## Per-tenant budgets
- Hard ceiling per tenant per billing period encoded in `TenantContext.ai_budget`.
- Pre-call estimator on every LLM call. If `spent + estimate > budget`, raises `BudgetExceededError`.
- **Never silently degrade** — surface a typed error so the caller can show a real banner.

## Soft thresholds
- **70%** — info event + dashboard banner.
- **85%** — warning event + email to OrgAdmin.
- **95%** — critical event + email + dashboard modal.
- **100%** — `BudgetExceededError`; non-critical workflows refuse to start.

## Model selection policy
- **Cheap models** (DeepSeek, Qwen, Gemini Flash, Haiku, Phi-3.5) for:
  - Classification (reply intent, sentiment)
  - Extraction (structured fields from text)
  - Tagging / ranking / dedupe
  - Embedding (bge-small self-hosted)
  - Reranking (bge-reranker-base self-hosted)
- **Premium models** (Claude Sonnet/Opus, GPT-4-class) for:
  - Personalized outreach copy
  - Proposal generation
  - Strategic viral hooks
  - Long-context planning by RootOrchestrator

A new task class added to the routing matrix requires an ADR (see `adr.md`).

## Expensive workflows
Workflows that estimate > a tenant-configured threshold (default ₹50) require explicit user confirmation in the UI before kickoff. Examples:
- Outreach to > 500 recipients
- Full proposal generation
- Bulk profile re-extraction

## Semantic cache hit rate
- Tracked as a SLO; target ≥ 38%.
- Alert if it drops below 30% for > 24h (could indicate a prompt version churn or a bug).
- See `rag-retrieval.md` for cache config.

## Per-tenant cost dashboard
- First-class admin surface. Shows: spend today, projected monthly, top-N expensive agents, cache hit %.
- Tenant can set their own soft thresholds below the org-level hard ceiling.

## Tier limits (default)
| Tier | AI runs/mo | Outreach sends/mo | Token budget hint (₹) |
|---|---|---|---|
| Starter | 1,000 | 500 | 400 |
| Growth | 15,000 | 5,000 | 4,000 |
| Enterprise | Unlimited (fair-use) | Unlimited (fair-use) | Negotiated |

Overage: ₹40 / 1,000 runs, ₹0.40 / outreach send.
