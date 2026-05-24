# Prompt Engineering Standards

Prompts are code. They get versioned, tested, gated, and rolled back like any other production change.

## Where prompts live
```
apps/api/src/corpmind/ai/prompts/
└── <task_name>/
    ├── v1.md           # the prompt body (markdown frontmatter for metadata)
    ├── v2.md
    ├── fixtures/       # eval fixtures (input → expected shape)
    └── evals.yaml      # promptfoo config
```

- Never inline a prompt string in a service or agent file. The prompt registry resolves `(name, version, env)` at call time.
- The Euri client receives `prompt_name` and `prompt_inputs`; the registry handles the rest.

## Prompt file structure
Every prompt file declares:
- **Role** — who the model is (e.g., "You are a senior B2B outreach copywriter").
- **Constraints** — length, tone, forbidden words.
- **Input schema** — what the registry will substitute.
- **Output schema** — JSON schema; structured output preferred (function calling / `response_format=json_schema`).
- **Safety rules** — what not to do.
- **Examples** — 2–5 few-shot exemplars when helpful.

## Determinism
- Prefer structured output (JSON mode / function calling) over free-text parsing.
- Avoid hidden chain-of-thought in production prompts (latency + cost + leak risk). If reasoning is needed, use a `<scratchpad>` section parsed and dropped before returning to the caller.

## Versioning
- Semantic version: `vMAJOR.MINOR`. Bump MAJOR on breaking schema change, MINOR on copy/quality change.
- The previous version stays loadable in the registry for rollback.

## Eval suite (per prompt)
- Fixture set with golden inputs + expected output shape.
- Promptfoo configuration runs the suite on every PR touching the prompt or the model routing.
- Merge blocked on regression > 2% across schema validity, format compliance, or task-specific score.

## Promotion flow
A new prompt version follows the feature-flag flow (see `feature-flags.md`):
1. **Shadow** — runs alongside the active version; outputs scored but not returned.
2. **% rollout** — 10% → 25% → 50% → 100% by tenant cohort.
3. **Promote** — the new version becomes `active`; old version remains loadable.

## Metrics tracked per prompt version
- Reply rate / extraction accuracy / classification F1 (task-dependent).
- p50/p95 latency.
- Avg tokens in/out.
- Cost per call.
- Fallback rate.
- HITL override rate (where applicable).

## Rollback
- `prompt_templates.active_in_envs` flag flips back to the previous version. No code change required.
- An ADR is required if a prompt rollback corresponds to a model-routing change.

## Forbidden
- Inlining prompt strings in service code.
- Editing a published prompt version in place — write a new version instead.
- Shipping a new prompt without a fixture set + eval pass.
