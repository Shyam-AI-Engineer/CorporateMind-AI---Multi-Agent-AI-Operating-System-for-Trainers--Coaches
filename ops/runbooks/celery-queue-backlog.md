# Runbook: Celery Queue Backlog

## Incident Summary

One or more Celery queues are accumulating tasks faster than workers can process them, causing delays in campaign sends, agent runs, or analytics jobs. The backlog may grow unboundedly if not addressed.

## Trigger Conditions

- Prometheus alert: `celery_queue_depth{queue="*"} > 200` sustained for > 5 minutes.
- Grafana Workflow dashboard shows increasing DLQ depth.
- Tenants reporting delayed campaign sends or agent runs timing out.
- `celery_task_outcome_total{status="retry"}` spike in Grafana.
- Queue circuit breaker opens: new campaign launches deferred, tenants notified.

## Severity Level

- **SEV3** — one secondary queue (e.g., `analytics`) is backed up; core outreach unaffected.
- **SEV2** — `outreach` or `agents` queue is backed up; campaign sends delayed > 30 minutes.
- **SEV1** — all queues are backed up; multiple tenants reporting send failures.

## Immediate Response Steps

1. **Identify which queue is backed up:**
   ```bash
   # Check queue depths via Redis
   redis-cli -u $REDIS_URL LLEN celery
   redis-cli -u $REDIS_URL LLEN outreach
   redis-cli -u $REDIS_URL LLEN agents
   redis-cli -u $REDIS_URL LLEN ingestion
   redis-cli -u $REDIS_URL LLEN analytics
   ```
2. **Identify root cause:**
   - **Worker crash / not running:** Check Railway worker service health.
   - **Slow external provider:** WhatsApp API or email provider latency spiking.
   - **Infinite retry loop:** A task failing repeatedly and re-queuing. Check DLQ depth.
   - **Resource exhaustion:** Workers hitting memory or CPU limits.
3. **For worker crash:** Restart the Celery worker service on Railway.
4. **For infinite retry loop:**
   - Identify the task fingerprint via the DLQ: `celery inspect query <task_name>`.
   - Revoke the stuck tasks: `celery -A corpmind.workers.celery_app control revoke <task_id> --terminate`.
   - Fix the root cause before re-enabling.
5. **Scale up workers (temporary):** Railway allows increasing worker replicas — scale from N to 2N for the affected queue.
6. **If queue circuit breaker is open:** New campaign launches are already deferred. Focus on draining the existing backlog before re-opening.

## Escalation Path

- **L1:** On-call engineer — identify queue and root cause.
- **L2:** Tech Lead — if scaling workers or revoking tasks in bulk.
- **L3:** Railway support if the issue is infrastructure-level (node exhaustion, network partition).

## Recovery Checklist

- [ ] Root cause identified and fixed.
- [ ] Queue depth returning to baseline (< 50) in Grafana.
- [ ] DLQ inspected — replay failed tasks if appropriate.
- [ ] Worker count returned to baseline if scaled up.
- [ ] Affected tenants notified of the delay.
- [ ] Circuit breaker re-opened if it was manually closed.
- [ ] Status page updated.

## Follow-up Actions

- [ ] Add the root cause to the DLQ fingerprint registry so the reaper can detect it proactively.
- [ ] Review per-tenant concurrency caps — if one tenant's bulk campaign caused the backlog, tighten their cap.
- [ ] If the backlog was caused by a slow external provider, add/tune the circuit breaker for that provider.
- [ ] Consider adding auto-scaling worker replicas based on queue depth (Stage 2 enhancement).
