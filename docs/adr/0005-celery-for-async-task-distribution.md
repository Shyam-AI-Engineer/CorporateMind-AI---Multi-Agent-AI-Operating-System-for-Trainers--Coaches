# ADR-0005: Celery for Async Task Distribution

- **Status:** Accepted
- **Date:** 2026-05-25
- **Deciders:** Shyam (Founder/CTO), AI Architect

## Context

CorporateMind AI has heavy async workloads that cannot run in the synchronous FastAPI request/response cycle:
- Agent runs (LangGraph graphs, potentially minutes-long)
- Campaign send pipelines (chunked, rate-limited, multi-channel)
- OCR, transcription, and embedding ingestion
- Daily analytics rollups and optimizer jobs
- Social media scheduled posts

Requirements:
1. **Per-tenant concurrency caps** — one tenant's heavy campaign cannot starve another tenant's agent run.
2. **Retry with backoff** — transient provider failures should not cascade to permanent failures.
3. **Idempotency** — re-running a task after a worker crash must produce the same outcome (no duplicate sends).
4. **Dead-letter queue** — exhausted retries must be observable and replayable.
5. **Separate queues per concern** — ingestion workloads should not block outreach workloads.
6. **Celery Beat** — per-tenant timezone-aware cron scheduling for daily automation.

## Decision

**Celery on Redis broker is the async task distribution system. Workers are deployed as a separate Railway service from the FastAPI API container.**

Queue topology (separate queues, separate worker pools):
- `agents` — LangGraph graph runs
- `outreach` — message send pipelines
- `social` — IG/FB/TG/LI scheduled posts
- `ingestion` — OCR, transcription, embedding
- `analytics` — daily rollups, optimizer jobs
- `scrape` — low-priority, isolated egress IP

Per-tenant concurrency: Starter=2, Growth=8, Enterprise=32 (per queue).

Every task must declare: `bind=True`, `acks_late=True`, `max_retries`, `retry_backoff=True`, `retry_jitter=True`, `time_limit` (hard), `soft_time_limit`, and an explicit `task_key` for idempotency.

Celery Beat schedule is version-controlled in `apps/api/src/corpmind/workers/celery_beat_schedule.py`.

## Alternatives Considered

**1. RQ (Redis Queue)**
- `+` Simpler API; less configuration.
- `-` No native per-worker concurrency caps per priority. No built-in retry with jitter. Celery's ecosystem (Flower monitoring, Beat scheduler, canvas primitives) is significantly richer. RQ is appropriate for simpler use cases.

**2. Dramatiq**
- `+` Simpler, more Pythonic API than Celery. Middleware-based architecture.
- `-` Smaller ecosystem; less production-proven at the scale of multi-tenant, multi-queue systems. Celery has 15+ years of production validation.

**3. FastAPI `BackgroundTasks`**
- `+` Zero infrastructure — tasks run in the API process.
- `-` Tasks are lost on API pod restart. No retry logic. No queue depth visibility. No per-tenant concurrency control. Unacceptable for production outreach pipelines.

**4. Temporal**
- `+` Durable execution, native retry semantics, excellent observability.
- `-` Requires a separate Temporal cluster (infrastructure cost + operational complexity). Python SDK is less mature than Go/Java SDKs. Overkill for Stage 1. Reconsidered at Stage 3 if Celery's model limits us.

## Consequences

**Positive:**
- `acks_late=True` means tasks re-queue on worker crash — no lost work.
- Per-tenant concurrency caps prevent noisy-neighbor via per-queue prefetch limits in the worker config.
- Celery Beat provides a version-controlled cron scheduler (no external cron dependencies).
- Dead-letter queue pattern (DLQ) with daily reaper surfaces operational failures proactively.
- Canvas primitives (chord, group) enable efficient fan-out for bulk campaign sends.

**Negative:**
- Celery has known issues with async (asyncio) integration — we use `gevent` or `eventlet` for I/O-bound workers, `prefork` for CPU-bound (ingestion, OCR). This requires worker pool configuration per queue.
- Redis as broker is a single point of failure for all queues. Mitigated by Railway Redis with persistence.
- Celery task serialization is JSON — all task arguments must be JSON-serializable. No SQLAlchemy models in task parameters.

**Neutral:**
- The API container and the Celery worker container share the same codebase — they are built from the same Docker image, started with different entrypoints (`uvicorn` vs `celery -A`).

## References

- `.claude/rules/queue-celery.md` — full task safety rules
- `docs/architecture.md` §9 (CI/CD + Environments)
- `apps/api/src/corpmind/workers/celery_beat_schedule.py` — beat schedule
- Supersedes: N/A
- Superseded by: N/A
