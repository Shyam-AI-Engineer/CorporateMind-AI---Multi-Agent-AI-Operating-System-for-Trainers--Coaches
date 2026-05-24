# Observability Rules

Three correlated planes: app traces (OTel), LLM traces (Langfuse), metrics (Prometheus/Grafana). All joined by `request_id`.

## Stack
- **Langfuse** — every agent run = one trace; nested spans per node, tool call, model call.
- **OpenTelemetry** — application + workflow spans propagated via `traceparent` header end-to-end (HTTP → Celery → DB query).
- **Prometheus** — scraped from FastAPI `/metrics` and Celery exporter.
- **Grafana** — dashboards (Tenant Health / Agent Runtime / LLMOps / Workflow / Channels / Business).
- **Sentry** — error capture, release tracking, performance for FE + BE.

## Correlation
- Every inbound HTTP request gets a `request_id` (ULID).
- Propagated: HTTP → Celery task headers → LangGraph `RunnableConfig.metadata` → Langfuse trace `metadata.request_id`.
- One ID joins: HTTP logs ↔ DB query logs ↔ Celery logs ↔ LLM trace ↔ Sentry event.

## Structured logging
- JSON only via structlog. Every line includes:
  - `request_id`, `tenant_id`, `workspace_id`, `run_id` (when applicable)
  - `level`, `event`, `module`, timestamps in UTC ISO 8601
- Use `logger.bind(...)` to inherit context within a request scope.
- NO PII in logs. NO tokens. NO credentials. NO full request/response bodies.

## What to log (and what not to)
- Log service-level decisions (route taken, model fell back, compliance blocked).
- Don't log raw payloads. Log shape + size + hash.
- Don't log on the hot path inside a tight loop — emit metrics instead.

## Custom metrics
Every business module exposes Prometheus metrics. Examples:
- `outreach_sent_total{channel,tenant}`
- `compliance_blocks_total{reason,channel}`
- `agent_run_duration_seconds{agent}`
- `llm_tokens_total{model,task,cached}`
- `tenant_budget_remaining_inr{tenant}`

## SLOs
| SLO | Target | Burn alert |
|---|---|---|
| API availability | 99.9% monthly | 2% budget burn in 1h → page |
| Agent run success | 96% rolling 24h | < 94% for 30 min → page |
| Outreach send error rate | < 1% | > 2% for 15 min → page |
| Token cost / tenant / day | < ₹20 avg | > ₹40 for any tenant → notify |
| ComplianceGuard false-positive rate | < 0.5% | > 1% for 1h → notify |
| Semantic cache hit rate | ≥ 38% | < 30% for 24h → notify |

## Workflow replay debugging
Any failed run is fetchable via admin UI with full state diff per node and re-executable against staging with the exact same `WorkflowState` and a sandbox tool registry. Same input → deterministic identical run.

## Dashboards (Grafana)
- **Tenant Health** — per-tenant request rate, p95 latency, error %, token spend, agent success %.
- **Agent Runtime** — run count, success rate, p50/p95/p99, retry rate, HITL rate.
- **LLMOps** — token usage by model, cost projection, fallback rate, cache hit rate, eval trend.
- **Workflow** — DLQ size, replay rate, checkpoint count, longest-paused workflows.
- **Channels** — per-channel send rate, delivery %, reply %, compliance-block rate.
- **Business** — new tenants, MRR, churn, avg reply rate, avg meetings/tenant/month.
