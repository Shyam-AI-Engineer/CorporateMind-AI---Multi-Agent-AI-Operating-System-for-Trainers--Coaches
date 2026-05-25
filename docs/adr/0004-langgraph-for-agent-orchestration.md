# ADR-0004: LangGraph for Agent Orchestration

- **Status:** Accepted
- **Date:** 2026-05-25
- **Deciders:** Shyam (Founder/CTO), AI Architect

## Context

CorporateMind AI requires a multi-agent runtime that coordinates 14 specialized agents (RootOrchestrator + 13 specialists) to perform complex, multi-step tasks: profile extraction, HR discovery, personalized outreach generation, compliance checking, and proposal drafting.

Requirements for the runtime:
1. **Checkpointing** — agent runs can take minutes; worker restarts must not lose progress.
2. **HITL (Human-in-the-Loop) gates** — certain actions must pause for trainer approval before proceeding.
3. **Typed, auditable state** — every state transition must be inspectable and replayable for debugging.
4. **Planner-Executor split** — the reasoning step (plan generation) must be separable from the execution step (deterministic dispatch) to make actions auditable.
5. **Deterministic replay** — a failed run must be re-executable against staging with the same inputs.
6. **Per-tenant concurrency caps** — agents running for one tenant cannot starve another.

## Decision

**LangGraph is the sole agent orchestration runtime. All agents live under `apps/api/src/corpmind/agents/` and share a single typed state: `corpmind.agents.state.AgentState` (TypedDict).**

Key design decisions within LangGraph:
- **Planner-Executor split:** Planner generates `Plan { steps: List[Step] }` (explicit tool, inputs, expected output schema). Executor is a deterministic dispatcher — it does not reason; it executes. Makes every action auditable.
- **Checkpoints:** Every state transition writes `(workflow_id, node, version, state_blob, ts)` to `workflow_checkpoints` table. Resumption validates `schema_version`; migrations registered per `(from, to)`.
- **HITL:** LangGraph `interrupt()` pauses the graph; state is checkpointed; on approval, `resume_workflow` task loads checkpoint and continues.
- **Sub-agent communication:** Only via `AgentState` — never direct agent-to-agent calls. Keeps topology a tree (debuggable) not a mesh (chaotic).
- **Tool registry:** Tools have explicit schemas + per-tool budgets (`max_calls_per_run`, `max_tokens_per_call`, `timeout_s`). An agent cannot call a tool outside its registered toolset.

New agents require an ADR (roster is fixed at 14; additions are architectural decisions).

## Alternatives Considered

**1. LangChain vanilla (without LangGraph)**
- `+` Simpler for single-chain use cases; large ecosystem.
- `-` No native checkpointing. No native HITL. State management is ad hoc. Replay requires custom implementation. Rejected: we need checkpointing and HITL as first-class features, not bolt-ons.

**2. CrewAI**
- `+` Higher-level abstraction; agent role definitions are human-readable.
- `-` Role-based agent framing doesn't map cleanly to our planner-executor split. Less control over state serialization format (needed for typed checkpoint migrations). Smaller ecosystem than LangGraph for production observability.

**3. Custom state machine (asyncio + Postgres)**
- `+` Full control; no framework dependency.
- `-` Building reliable checkpointing, HITL, deterministic replay, and tool registry from scratch is a multi-month engineering investment. LangGraph provides all of this. Building it ourselves is premature at Stage 1.

**4. Temporal (workflow engine)**
- `+` Battle-tested durable execution; excellent for long-running workflows.
- `-` Requires a separate Temporal cluster. Python SDK is mature but the tooling ecosystem for LLM-native workflows (Langfuse integration, prompt tracing) is weaker than LangGraph. Stage 3 option if workflow complexity grows beyond LangGraph's model.

## Consequences

**Positive:**
- Native checkpointing means worker crashes are non-destructive — runs resume from the last node.
- HITL is a first-class primitive — no custom plumbing needed.
- Planner-Executor split makes every action inspectable in the admin workflow inspector.
- Deterministic replay enables the `debug-workflow-replay` skill.
- Langfuse tracing integrates natively.

**Negative:**
- `AgentState` TypedDict is a shared contract — adding fields requires a schema_version bump and a migration registration. This adds overhead for simple state changes.
- LangGraph's async model requires careful error handling at every node to avoid graph deadlocks.
- The planner's structured output (strict JSON schema for `Plan`) must be validated robustly; LLM non-compliance must be caught and re-prompted (max 2 retries).

**Neutral:**
- LangGraph runs within the Celery `agents` queue — it's not an additional service. Workers process one graph per task.

## References

- `.claude/rules/langgraph-agents.md` — full agent rules
- `docs/architecture.md` §5 (Agent Topology)
- `docs/architecture.md` §7b (Agent Run Lifecycle)
- Supersedes: N/A
- Superseded by: N/A (write a new ADR if Temporal migration is triggered at Stage 3)
