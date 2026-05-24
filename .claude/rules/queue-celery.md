# Queue & Worker Safety (Celery)

Celery on Redis is our async execution backbone. Every task must be safe to retry, safe to fan out, and observable.

## Per-task requirements
Every Celery task declares:
- `bind=True` so it has access to `self.request` (retries, id).
- `acks_late=True` — task is only acked after success, so worker crashes safely re-queue.
- `max_retries`, `retry_backoff=True`, `retry_backoff_max`, `retry_jitter=True`.
- `time_limit` (hard) and `soft_time_limit` (raises `SoftTimeLimitExceeded` for cleanup).
- An explicit `task_key` derived from arguments — used as Redis idempotency lock.

## Idempotency
- Every task is idempotent. The `task_key` (e.g. `outreach:{campaign_id}:{recipient_id}`) is used both for dedup and for safe replay.
- Mutating side effects (DB writes, external API calls) check for prior completion via the task_key.

## Queues
Separate queues per concern; workers scale per queue:
- `agents` — LangGraph runs
- `outreach` — message send pipelines
- `social` — IG/FB/TG/LI scheduled posts
- `ingestion` — OCR, transcription, embedding
- `analytics` — daily rollups, optimizer jobs
- `scrape` — low-priority, isolated egress IP

Per-tenant concurrency cap per queue (Starter=2, Growth=8, Enterprise=32) prevents noisy-neighbor.

## Fan-out
- Campaigns chunk recipients (default 100/chunk) and self-throttle to respect channel rate limits.
- Use chord/group for parallel dispatch; never `apply_async` in a tight loop without batching.

## Long-running workflows
- Checkpoint state to Postgres `workflow_checkpoints` so resumption survives worker restart (see `langgraph-agents.md`).
- Soft time limit ≥ 90% of hard; on `SoftTimeLimitExceeded`, persist checkpoint and re-queue.

## Dead-letter queue
- Tasks that exhaust retries land in `dlq.{queue_name}` queue → mirrored to `dlq_workflows` table with error fingerprint.
- Daily reaper groups failures by fingerprint and surfaces top-10 to LLMOpsGuardian.
- Alert on DLQ depth > 50.

## Circuit breaker
- Queue-depth breaker: if a queue's depth exceeds a threshold for > 5 min, NEW campaign launches in that queue are deferred and the tenant is notified.

## Metrics
Every task emits Prometheus:
- `celery_task_duration_seconds{task,queue}` (histogram)
- `celery_task_outcome_total{task,status}` (counter: success/retry/failed)
- `celery_task_retries_total{task}` (counter)
- `celery_queue_depth{queue}` (gauge, scraped from Redis)

## Logging
- Every task logs `task_name`, `task_id`, `task_key`, `tenant_id`, `request_id` (propagated from the HTTP request that enqueued it).

## Forbidden
- Tasks that call other tasks synchronously (`.get()` inside a worker) — deadlock risk.
- Tasks without `acks_late=True`.
- Tasks without an explicit `task_key` if they have side effects.
- Sleeping inside a task to poll — schedule a follow-up task instead.
