---
name: debug-workflow-replay
description: Replay a failed agent / workflow run from its last checkpoint with a sandbox tool registry — same input, deterministic identical run
---

# Debug Workflow Replay Skill

## Goal
Diagnose a failed agent run by re-executing it deterministically against staging with the exact state it had at failure. This is how we debug agentic failures without poking prod.

## Steps
1. **Ask for:** the `run_id` OR `workflow_id` of the failed run. (Look in `dlq_workflows`, the Langfuse trace, the Sentry event, or the admin UI's failed-runs panel.)
2. **Fetch the run's last checkpoint:**
   - Query `workflow_checkpoints` for `(workflow_id, latest)`.
   - Extract `state_blob` (the `WorkflowState`) and `schema_version`.
3. **Open the Langfuse trace** for the run to see:
   - Which node failed.
   - The model + prompt version that ran.
   - The tool calls and their outputs.
   - The exception (if any).
4. **Migrate state if necessary:** if the current code has a newer schema version, apply the registered migration to the state blob.
5. **Set up the sandbox tool registry** in staging:
   - Replace network-touching tools (channel sends, external HTTP) with recorders that store payloads instead of dispatching.
   - Keep DB tools live (against a staging DB or testcontainers).
6. **Run the replay:**
   ```bash
   python -m corpmind.tools.replay --run-id <id> --env staging --sandbox-tools
   ```
   The replay loads the checkpoint, replays from the failing node, and emits a NEW Langfuse trace tagged `replay:<original_run_id>`.
7. **Compare:**
   - Original trace vs. replay trace — do they diverge? Where?
   - Did the same error reproduce? If yes, you have a deterministic repro.
   - If no, the failure was nondeterministic (likely model variance) — try multiple temperatures / seeds; the fix may need a stricter prompt or a deterministic helper.
8. **Iterate:**
   - Modify the prompt OR the agent code OR the tool OR the state.
   - Re-run from the checkpoint.
   - Confirm the failure no longer reproduces.
9. **Write the regression test:** capture the failing `WorkflowState` + the expected outcome as a permanent fixture (`apps/api/tests/integration/fixtures/<scenario>.json`). Add it to the agent's replay test suite so this scenario can never regress silently.
10. **Postmortem (if SEV2+):** link the replay artifact, the fix PR, and the regression test in the postmortem doc.

## Quality rules
- NEVER replay against production. Always staging or local.
- NEVER replace a non-network tool (e.g., DB writes) with a no-op silently — make the sandboxing explicit so you don't get false-positive "it works now."
- The replay must produce a DIFFERENT Langfuse trace (tagged as replay), not pollute the original.
- A reproducible bug is always preferred over a "couldn't reproduce" close — non-determinism deserves its own fix path (prompt tightening, temperature change, retry policy).

## What you'll need
- Admin role to fetch checkpoints + Langfuse traces.
- Staging DB access.
- Staging Qdrant access (or a snapshot).
- The original prompt version (pulled from the registry).

## References
- `.claude/rules/langgraph-agents.md` (checkpointing, state schema)
- `.claude/rules/observability.md` (correlation IDs, Langfuse)
- `.claude/rules/queue-celery.md` (DLQ)
