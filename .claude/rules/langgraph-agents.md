# LangGraph Agent Rules

LangGraph is the only agent runtime. Agents live under `apps/api/src/corpmind/agents/`.

## Single responsibility
- One agent, one job. If you find yourself adding a second concern to an agent, split it.
- The roster (12 agents) is defined in the PRD §9.1; new agents require an ADR.

## Shared state
- `corpmind.agents.state.AgentState` (TypedDict) is the only state passed between nodes. No untyped graph state.
- New fields require: (a) a default value, (b) a state-schema version bump, (c) a migration for checkpoint resumption.

## Planner-Executor split
- **Planner** generates a strict-schema `Plan { steps: List[Step] }` with explicit `tool`, `inputs`, `expected_output_schema`.
- **Executor** is a deterministic dispatcher — it does NOT reason; it executes the plan. This split makes every action auditable and replayable.

## Tools
- Tools registered with explicit schemas + per-tool budgets (`max_calls_per_run`, `max_tokens_per_call`, `timeout_s`).
- Tools marked `read_only` (default), `mutating_low_risk`, or `mutating_high_risk`. High-risk requires HITL or explicit policy approval.
- An agent CANNOT call a tool not in its registered toolset. Attempts are blocked and logged.

## Checkpointing
- Every state transition writes `(workflow_id, node, version, state_blob, ts)` to `workflow_checkpoints`.
- Workflows resumable from any checkpoint in any process.
- Resumption validates `schema_version`; migrations registered per `(from, to)`.

## HITL gates
Interrupt the graph and route to approval queue when:
- Recipient count > 200
- Enterprise-tier outreach
- ComplianceGuardAgent flags content
- Sensitive-content classifier triggers
- First-week-of-tenant mode is active (training wheels)

The graph resumes on approval; rejection emits `campaign.rejected` event.

## Determinism around fragile model behavior
- Wrap LLM outputs in deterministic helpers (parsers, validators).
- Always provide a fallback path for low-confidence outputs.
- Never expose raw model output to end users without post-processing.

## Logging
- Each node emits a Langfuse span: `tenant_id`, `agent`, `node`, `model`, `tokens_in`, `tokens_out`, `latency_ms`, `result_status`, `request_id`.
- Log key decisions (tool calls, branch choices) — not raw payloads.

## Concurrency
- Per-tenant cap on `agents` Celery queue: Starter=2, Growth=8, Enterprise=32.
- Within a workflow, parallel sub-agent calls fan out via `asyncio.gather` with per-call timeouts.

## Sub-agent communication
- Sub-agents communicate ONLY via the shared `AgentState`, never directly. This keeps the topology a tree (debuggable), not a mesh (chaotic).

## Continuous learning
- Outcomes feed Langfuse + `campaign_outcomes_{org}` Qdrant collection.
- Weekly DSPy job proposes prompt candidates; promotion gated by Promptfoo eval suite (see `prompt-engineering.md`).
