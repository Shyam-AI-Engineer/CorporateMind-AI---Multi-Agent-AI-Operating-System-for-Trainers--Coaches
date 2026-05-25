# Runbook: Euri / LLM Provider Down

## Incident Summary

The Euri AI Gateway or one of its upstream LLM providers (Claude, GPT, Gemini, DeepSeek) is unavailable, causing agent runs to fail or degrade. All LLM-dependent workflows are affected.

## Trigger Conditions

- `EuriClient` returning 5xx errors or connection timeouts for > 2 consecutive minutes.
- Langfuse shows a spike in `status=error` spans for LLM calls.
- Prometheus alert: `llm_provider_error_rate > 10%` for 5 minutes.
- Grafana LLMOps dashboard shows fallback rate > 50%.
- Agent runs failing at a rate > 20% in rolling 5-minute window.

## Severity Level

- **SEV2** if primary provider is down but fallback chain is handling requests.
- **SEV1** if the entire fallback chain (primary → secondary → tertiary → Ollama) is exhausted.

## Immediate Response Steps

1. **Check Euri status page** — confirm whether this is a provider-side outage or a local configuration issue.
2. **Check Grafana LLMOps dashboard** — identify which model tier is failing (primary vs fallback).
3. **Check Ollama local fallback** — confirm that the local Ollama instance is running and responding:
   ```bash
   curl http://ollama-service:11434/api/tags
   ```
4. **If primary provider only is down** — the fallback chain handles it automatically. Monitor the fallback rate; notify the team if it exceeds 80% for > 10 minutes (cost impact).
5. **If entire chain is down (SEV1):**
   - Flip the kill-switch feature flag for all agent-triggered autonomous workflows: `automation.auto_execute.global = false`.
   - Celery queues `agents` and `outreach` will drain; no new LLM calls are initiated.
   - Trainer-facing UI shows a system degradation banner (triggered by kill-switch flag).
6. **Notify the Incident Commander** and open `#incident-<id>` channel.
7. **Draft customer comms** (SEV1 only) — do not send without IC approval.

## Escalation Path

- **L1:** On-call engineer — assess and mitigate within 15 minutes.
- **L2:** Tech Lead — if local Ollama fallback is also failing or cost impact is high.
- **L3:** Euri AI support + LLM provider support escalation (contact details in `ops/secrets.md`).

## Recovery Checklist

- [ ] Confirm primary provider is back up (check Euri status + send a test prompt).
- [ ] Confirm fallback rate returning to baseline (< 5%) in Grafana.
- [ ] Re-enable autonomous workflows: flip `automation.auto_execute.global = true`.
- [ ] Inspect Celery DLQ for agent runs that failed during the outage — replay if appropriate.
- [ ] Update Langfuse with outage window annotation for cost reconciliation.
- [ ] Update status page: incident resolved.

## Follow-up Actions

- [ ] Postmortem if outage exceeded 30 minutes or affected > 10 tenants.
- [ ] Review and strengthen Ollama local fallback capacity if it was the limiting factor.
- [ ] Add the outage window to the billing reconciliation report (tenants should not be charged for AI runs during provider downtime).
