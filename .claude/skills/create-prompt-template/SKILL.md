---
name: create-prompt-template
description: Create a new versioned prompt template with fixtures, Promptfoo eval suite, and registry entry
---

# Create Prompt Template Skill

## Goal
Add a new prompt to the registry under `apps/api/src/corpmind/ai/prompts/<task_name>/`. Prompts are code: versioned, tested, and gated for rollout.

## Steps
1. **Ask for:**
   - Task name (e.g., `outreach.email`, `proposal.section.solution`, `lead.classify_reply`).
   - Purpose: what the prompt should accomplish.
   - Input schema: what variables get substituted.
   - Output schema: structured JSON shape expected from the model.
   - Constraints: length, tone, language, forbidden words.
2. **Create the prompt file:**
   ```
   apps/api/src/corpmind/ai/prompts/<task>/
   ├── v1.md           # role, constraints, input/output schemas, safety, examples
   ├── fixtures/       # input → expected-shape JSON files
   │   ├── 01_happy_path.json
   │   ├── 02_edge_short_input.json
   │   └── 03_adversarial_injection.json
   └── evals.yaml      # promptfoo configuration
   ```
3. **Author the prompt** (`v1.md`) with these sections:
   - **Role** — single sentence persona.
   - **Constraints** — bulleted hard limits.
   - **Input schema** — JSON-schema shape of substituted variables.
   - **Output schema** — JSON-schema shape the model must produce (used by `response_format=json_schema`).
   - **Safety rules** — what the model must never do.
   - **Examples** — 2–5 input/output pairs (kept short).
4. **Add the registry entry** in `apps/api/src/corpmind/ai/prompts/registry.py`:
   - `(name, version, env)` → file path mapping.
   - Initial promotion state: `shadow` (runs alongside any prior version, output not returned).
5. **Add routing matrix entry** in `apps/api/src/corpmind/ai/routing.py`: which task class → which primary / fallback / local-fallback model.
6. **Build fixtures** — at least 20 covering:
   - Happy path (typical inputs)
   - Edge cases (empty fields, max-length inputs, multilingual)
   - Adversarial (prompt-injection attempts, PII smuggling, jailbreaks)
7. **Configure Promptfoo** (`evals.yaml`) with assertions:
   - `is-json` and JSON-schema validation
   - `not-contains` for denylist (competitor names, profanity, PII patterns)
   - Length bounds
   - Language match (where applicable)
   - Task-specific scorers (LLM judge for tone match, semantic equivalence)
8. **Run the eval suite** locally — must pass before opening the PR.
9. **Document the rollout plan** in the PR description:
   - Shadow duration
   - % rollout cadence
   - Promotion criteria (which metrics must hold)
10. **Tests:**
    - Registry lookup test (correct file resolved per `(name, version, env)`).
    - Eval suite passes in CI (Promptfoo job).

## Quality rules
- Semantic version: `vMAJOR.MINOR`. Bump MAJOR on output-schema break; MINOR on copy/quality change.
- Prefer structured output (JSON mode / function calling) over free-text.
- Avoid hidden chain-of-thought in production. If reasoning is needed, use a `<scratchpad>` parsed and dropped.
- NEVER inline a prompt string in service or agent code.
- Previous version remains loadable for rollback — never delete a published version.
- A new prompt without a fixture set + eval pass is a review blocker.

## References
- `.claude/rules/prompt-engineering.md`
- `.claude/rules/euri-gateway.md`
- `.claude/rules/feature-flags.md` (rollout flow)
