# ADR-0011: Analytics Narrative Uses Cheap Summarisation Model

- **Status:** Accepted
- **Date:** 2026-06-23
- **Deciders:** Engineering (Sprint 20B)

## Context

Sprint 20B adds a narrative AI layer on top of the deterministic Sprint 20A
recommendations. The task is to explain, summarise, and prioritise existing
recommendations — not to reason, plan, or generate creative copy.

The routing matrix (see ADR-0002) requires an ADR for every new task class added.
`analytics_narrative` is the new task class for this endpoint.

## Decision

Route `analytics_narrative` to cheap summarisation models:
primary `claude-haiku-4-5`, fallback chain `gpt-4.1-nano → gemini-2.5-flash`.

The AI receives a serialised `RecommendationsOut` JSON blob only. It may not access
DB data, alter confidence scores, or invent recommendations — enforced by the
`AnalyticsInsightService._build_context()` boundary.

## Alternatives considered

1. **Claude Sonnet (premium)** — better narrative quality but 8–12× more expensive
   per call. The input is already structured JSON so Sonnet's reasoning advantage is
   minimal for a summarisation task. Rejected on cost grounds.

2. **No AI / pure deterministic summary** — considered as the cheapest option.
   Deferred: the audit trail and suppressed_count UX is already handled by Sprint 20A;
   the AI layer adds genuine value in plain-language prioritisation for trainers who
   don't interpret raw win-rate numbers.

## Consequences

- **Positive:** < ₹0.05 per insights call at Haiku pricing; negligible token cost.
- **Positive:** Full fallback chain — if Haiku fails, two cheap providers remain.
- **Negative:** Haiku occasionally produces less polished prose than Sonnet.
  Mitigated by structured JSON output schema and the deterministic fallback that
  fires on any parse error.
- **Neutral:** Adds `analytics_narrative` to the routing matrix; any future
  quality upgrade is a routing-only change, no service code change needed.

## References

- ADR-0002: Euri as sole LLM egress
- Sprint 20A: deterministic recommendations (foundation this layer builds on)
- `apps/api/src/corpmind/ai/routing.py`
- `apps/api/src/corpmind/modules/analytics/service.py` — `AnalyticsInsightService`
