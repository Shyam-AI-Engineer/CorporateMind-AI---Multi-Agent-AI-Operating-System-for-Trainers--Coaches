# ADR-0001: Modular Monolith for Stage 1

- **Status:** Accepted
- **Date:** 2026-05-25
- **Deciders:** Shyam (Founder/CTO), AI Architect

## Context

CorporateMind AI is an agentic SaaS product targeting trainers, coaches, consultants, and speakers in the Indian market. The system involves multiple cross-cutting concerns: multi-tenant data isolation, async agent runs, multi-channel outreach pipelines, and compliance enforcement.

We need to choose a deployment topology at project inception. The system must be:
- Deliverable by a small team in Stage 1 (< 6 months to first paying tenants)
- Horizontally scalable in Stage 2 without a full rewrite
- Operationally simple — Railway + Vercel, no Kubernetes expertise required in Stage 1

The risk of starting with microservices is high operational overhead, distributed transaction complexity, and premature abstraction that slows feature delivery before product-market fit.

## Decision

**Deploy as a single FastAPI application (modular monolith) on Railway for Stage 1.**

The monolith is structured with clean module boundaries under `apps/api/src/corpmind/modules/<name>/`, each following the Ports & Adapters pattern (`api.py | service.py | repo.py | models.py | schemas.py | events.py`). Modules never import each other's `repo.py` or `models.py` — inter-module communication is via service interfaces (dependency injection) or an in-process event bus.

This preserves the extraction path to microservices by design: each module is already an independently deployable unit of logic. The Stage 2 migration extracts `social/` and `whatsapp/` as separate services; no cross-module coupling cleanup is required.

**Scaling triggers that mandate moving to Stage 2 (defined explicitly in `docs/architecture.md` §11):**
- API p95 latency > 800ms sustained
- Celery queue depth > 200 sustained
- Database connections approaching pool limit

## Alternatives Considered

**1. Microservices from day 1**
- `+` Full independent scalability per service
- `-` Requires Kubernetes, service mesh, distributed tracing, API versioning between services, distributed transactions — all before product-market fit. Team bandwidth cost: ~3× higher for the same features.

**2. Serverless (Vercel Functions / AWS Lambda)**
- `+` Zero ops, scales to zero
- `-` Cold starts kill agent run latency. LangGraph stateful workflows don't fit the stateless function model. Redis + Celery connections are expensive to re-establish per invocation.

**3. Majestic Monolith (no module boundaries)**
- `+` Fastest to write initially
- `-` Creates a tangled codebase that's impossible to extract later. Tenant isolation bugs become impossible to audit. This approach is explicitly rejected.

## Consequences

**Positive:**
- Developers can build, test, and debug all features in a single `docker compose up` environment.
- No distributed transaction coordination: service calls are in-process function calls.
- Simpler CI/CD pipeline for Stage 1 (single container image).
- Clean migration path to microservices when scaling triggers are hit — modules are already ports-and-adapters.

**Negative:**
- Noisy-neighbor risk for CPU-bound agent runs on shared compute. Mitigated by Celery per-tenant queue caps (Starter=2, Growth=8, Enterprise=32).
- A bug in one module can affect others (process-level failure). Mitigated by robust error handling + circuit breakers + Celery task isolation.

**Neutral:**
- Celery runs as a separate worker process from day 1 — the "monolith" is already two deployable units (API + worker).

## References

- `CLAUDE.md` §Stage Evolution
- `docs/architecture.md` §11 (Stage Evolution triggers)
- `.claude/rules/backend-python.md`
- Supersedes: N/A
- Superseded by: N/A (update this when Stage 2 extraction begins)
