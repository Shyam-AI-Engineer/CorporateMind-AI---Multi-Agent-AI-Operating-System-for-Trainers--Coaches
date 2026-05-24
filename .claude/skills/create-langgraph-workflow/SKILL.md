---
name: create-langgraph-workflow
description: Scaffold a new multi-step LangGraph workflow with typed state, checkpointing, HITL gates, and DLQ wiring
---

# Create LangGraph Workflow Skill

## Goal
Add a new end-to-end workflow that coordinates multiple agents over a shared `AgentState`, with full pause/resume support and observability.

## Steps
1. **Ask for:**
   - Workflow name (snake_case) and one-line purpose (e.g., `campaign_send_pipeline` — "approved campaign → throttled multi-channel send → attribution tracking").
   - Participating agents (e.g., `OutreachAgent`, `ComplianceGuardAgent`, channel agents).
   - Trigger source (event subscription, scheduled, manual).
   - HITL gates and their conditions.
   - Expected duration class (sub-minute, minutes, hours).
2. **Create the workflow definition:**
   ```
   apps/api/src/corpmind/workflows/<name>/
   ├── __init__.py
   ├── graph.py        # nodes, edges, conditional routers
   ├── state.py        # workflow-specific state extensions (typed)
   ├── triggers.py     # event/schedule subscriptions
   └── checkpoints.py  # migration functions per state schema version
   ```
3. **Wire checkpointing** — every node transition writes to `workflow_checkpoints`. Define `schema_version`.
4. **Add HITL nodes** — explicit `await_human_approval()` nodes that interrupt the graph and emit the appropriate `campaign.approval_requested` (or similar) event.
5. **Add DLQ wiring** — failed runs land in `dlq_workflows` with error fingerprint.
6. **Add Celery task entrypoint** in `apps/api/src/corpmind/workers/<queue>_tasks.py` — task is idempotent and resumable (see `.claude/rules/queue-celery.md`).
7. **Tests:**
   - Replay fixture: run the workflow against a frozen tool registry and assert state transitions.
   - Pause/resume: persist a checkpoint mid-run, restart, assert resumption produces identical output.
   - HITL: assert that gate triggers and that approval → resume produces correct continuation.
   - Failure: assert that an unrecoverable failure lands in DLQ with the correct fingerprint.
8. **Add metrics:**
   - `workflow_runs_total{workflow,status}`
   - `workflow_duration_seconds{workflow}`
   - `workflow_checkpoint_count{workflow}`
9. **Document in `docs/workflows/<name>.md`** with a state diagram.

## Quality rules
- Typed `WorkflowState` only — no `dict[str, Any]` between nodes.
- Nodes are pure functions `(state) -> partial_state_update`.
- Edges are conditional functions returning the next node or `END`.
- Schema version bumps require a migration function from previous version.
- Workflows older than 30 days that depend on a removed node go to a quarantine view, not silent loss.
- HITL gates are explicit nodes, not implicit checks scattered through the graph.

## References
- `.claude/rules/langgraph-agents.md`
- `.claude/rules/queue-celery.md`
- `.claude/rules/observability.md`
