# Runbook: Postgres Connection Exhaustion

## Incident Summary

The Postgres connection pool is exhausted. API requests and Celery tasks are failing to acquire database connections, causing 500 errors and task failures across all tenants.

## Trigger Conditions

- Prometheus alert: `db_pool_available_connections < 5` sustained for > 2 minutes.
- Error log spike: `asyncpg.exceptions.TooManyConnectionsError` or `sqlalchemy.exc.TimeoutError`.
- API health endpoint (`/health`) returning 503.
- Celery tasks failing with `OperationalError: server closed the connection unexpectedly`.
- Grafana Tenant Health dashboard showing p95 latency spike (> 2s) across all tenants.

## Severity Level

- **SEV2** — API is partially degraded; some requests failing.
- **SEV1** — API is down; health endpoint failing; all tenants affected.

## Immediate Response Steps

1. **Check current connection count:**
   ```sql
   SELECT count(*) FROM pg_stat_activity WHERE state != 'idle';
   SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock';
   ```
2. **Identify connection holders:**
   ```sql
   SELECT pid, usename, application_name, state, wait_event, query_start, query
   FROM pg_stat_activity
   ORDER BY query_start ASC
   LIMIT 20;
   ```
3. **Kill long-running idle connections (immediate relief):**
   ```sql
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE state = 'idle'
     AND query_start < NOW() - INTERVAL '5 minutes';
   ```
4. **Kill blocking queries if present:**
   ```sql
   SELECT pg_cancel_backend(pid)
   FROM pg_stat_activity
   WHERE wait_event_type = 'Lock'
     AND query_start < NOW() - INTERVAL '2 minutes';
   ```
5. **Restart Celery workers** — workers that crash without releasing connections can leave stale connections. Railway: restart the worker service.
6. **Reduce API replicas temporarily** — if multiple API pods are open, reducing from N to N/2 reduces the connection demand.
7. **Check for connection leak in recent deploys** — if a code change went out in the last hour, this is the likely root cause. Prepare a rollback.

## Escalation Path

- **L1:** On-call engineer — run diagnostic queries, terminate idle connections.
- **L2:** Tech Lead — if a code change is the cause and rollback is needed.
- **L3:** Railway support — if Postgres itself is restarting or the connection limit needs to be raised at the infrastructure level.

## Recovery Checklist

- [ ] Connection count below 80% of `max_connections` (check `SHOW max_connections;`).
- [ ] API health endpoint returning 200.
- [ ] No error spike in Grafana for > 5 minutes.
- [ ] Root cause identified (leak in code, worker crash, missing pool configuration).
- [ ] If code regression: hotfix deployed (see `emergency-hotfix.md`).
- [ ] Status page updated.

## Follow-up Actions

- [ ] Postmortem if outage exceeded 15 minutes.
- [ ] Add `pool_pre_ping=True` and `pool_recycle=1800` to SQLAlchemy engine config if not already present.
- [ ] Review `pool_size` and `max_overflow` settings — adjust based on observed connection patterns.
- [ ] Add a Prometheus alert for `idle in transaction` connections older than 30 seconds (early warning).
- [ ] Consider PgBouncer for connection pooling at the infrastructure level (Stage 2 enhancement).
