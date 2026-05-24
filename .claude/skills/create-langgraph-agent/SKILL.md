---
name: create-langgraph-agent
description: Scaffold a new LangGraph agent with single responsibility, explicit toolset, guardrails, planner/executor split, and checkpoint support
---

# Create LangGraph Agent Skill

## Goal
Add a new agent to the multi-agent runtime. Each agent has one job, a minimal toolset, and full Langfuse tracing.

## Pre-flight
- An ADR is REQUIRED for any new agent (agent topology change). See `.claude/rules/adr.md`.
- Confirm with the user that this responsibility doesn't already belong to an existing agent (see PRD §9.1 roster).

## Steps
1. **Ask for:** agent name (PascalCase), one-line responsibility, tool list (minimal), memory class (working / episodic / semantic / procedural), target model tier (small / mid / premium).
2. **Create files:**
   ```
   apps/api/src/corpmind/agents/<snake_name>/
   ├── __init__.py
   ├── agent.py        # node functions + graph compiler
   ├── tools.py        # explicit tool registrations with schemas + budgets
   ├── prompts/        # versioned prompt files (see create-prompt-template)
   ├── guardrails.py   # input/output validators specific to this agent
   ├── schemas.py      # agent-specific input/output Pydantic models
   └── state.py        # AgentState extensions (typed fields, schema version)
   ```
3. **Register** the agent in `apps/api/src/corpmind/agents/runtime.py` (the runtime registry).
4. **Define `AgentState` contribution** — what new fields does this agent read/write? Bump the schema version; add migration if needed.
5. **Wire tools** — each tool registered with `max_calls_per_run`, `max_tokens_per_call`, `timeout_s`, `risk_level` (read_only / mutating_low / mutating_high).
6. **Add HITL gates** — when does this agent require human approval? Encode in `agent.py`.
7. **Add a kill-switch feature flag** — `agent.<name>.enabled` (see `.claude/rules/feature-flags.md`).
8. **Tests:**
   - Replay against fixed `AgentState` fixtures.
   - Assert state transitions (PLAN → EXECUTE → VERIFY) and side effects.
   - Schema validity of all LLM outputs.
   - Guardrail rejection cases.
9. **Promptfoo eval suite** — at least 20 input/output fixtures covering happy path, edge cases, adversarial inputs.
10. **Write the ADR** documenting why this agent exists, its scope, alternatives considered.

## Quality rules
- **Single responsibility** — one agent, one job. Splitting is cheap; merging later is expensive.
- **Minimal toolset** — every tool is an attack surface. Start with the smallest set.
- **Planner-Executor split** — planner generates structured `Plan`; executor is deterministic dispatch. Never let the executor "decide."
- **Checkpoint every node** — resumption must work for any node.
- **No raw model output exposed** — always post-process through schemas + validators.
- **Fallback for low confidence** — define what happens when the model is uncertain.
- **Langfuse span** — every node emits a span with `tenant_id`, `agent`, `node`, `model`, tokens, latency.
- **Euri gateway only** — all LLM calls via `EuriClient` (mechanically enforced).

## References
- `.claude/rules/langgraph-agents.md`
- `.claude/rules/euri-gateway.md`
- `.claude/rules/prompt-engineering.md`
- `.claude/rules/feature-flags.md`
- `.claude/rules/adr.md`
