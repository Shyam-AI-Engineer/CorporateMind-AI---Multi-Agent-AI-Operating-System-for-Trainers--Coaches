# ADR-0007: Proposal Generation Architecture

- **Status:** Accepted
- **Date:** 2026-06-10
- **Deciders:** Shyam-AI-Engineer (Tech Lead)
- **Supersedes:** —
- **Related ADRs:** ADR-0002 (Euri gateway), ADR-0003 (RLS tenancy), ADR-0004 (LangGraph agents)

---

## Context

CorporateMind AI's core value proposition is helping trainers, coaches, and consultants win corporate engagements faster. A common bottleneck in the sales cycle is the proposal: after a discovery meeting, trainers spend hours writing bespoke documents tailored to each company's context. This is high-effort, error-prone, and inconsistent.

By the time a lead reaches the `meeting_completed` or `booked` CRM stage, the system has already accumulated:
- The lead's score and stage history
- Meeting notes and CRM observations logged by the trainer
- The trainer's specializations and previous campaign context
- The contact's company and seniority information (from HR discovery)

This is sufficient signal for an LLM to produce a structured first-draft proposal, which the trainer reviews and sends — collapsing hours of work into minutes.

### Constraints
- Every LLM call must route through Euri AI Gateway (`ADR-0002`). No direct provider SDK imports.
- Every write table must have `tenant_id` with RLS (`ADR-0003`).
- New agent topology entries require this ADR (`ADR-0004`), even if the implementation predates the formal record.
- Proposals must not auto-send. A human must explicitly mark a proposal as sent.
- This module is a **modular monolith service**, not a standalone agent graph. The name "ProposalAgent" in the Euri call metadata refers to the logical agent label for observability, not a LangGraph agent node.

---

## Decision

Implement proposal generation as a **service-layer LLM call** (not a LangGraph graph node) within the `proposals` module, triggered manually by the trainer via the UI. The service:

1. Validates that the lead is in an eligible CRM stage (`meeting_completed` or `booked`).
2. Calls `EuriClient.chat(task="proposal_generation", ...)` with structured lead context.
3. Persists the AI-generated content as a `Proposal` row with `status="draft"`.
4. Returns the draft to the trainer for review.
5. The trainer reads, edits (out of scope: Phase 2 edit flow), and explicitly clicks **Mark as sent** to transition to `status="sent"`.

The architecture deliberately does not use a LangGraph graph for this workflow. A single-step, single-LLM-call generation with a deterministic fallback does not warrant a graph. LangGraph is reserved for multi-step, multi-agent, resumable workflows (`ADR-0004`).

---

## Existing Proposal Architecture

### Module layout

```
apps/api/src/corpmind/modules/proposals/
├── models.py      — Proposal SQLAlchemy model
├── repo.py        — ProposalRepo (CRUD, tenant-scoped)
├── schemas.py     — GenerateProposalRequest, ProposalOut, ProposalListOut
├── service.py     — ProposalService (generate, list, get, mark_sent)
├── api.py         — 4 REST endpoints
└── events.py      — ProposalGenerated, ProposalSent domain events
```

### Database table

```sql
CREATE TABLE proposals (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL,           -- RLS column
    workspace_id UUID NOT NULL,
    contact_id   UUID NOT NULL,           -- the HR contact being proposed to
    title        VARCHAR(500) NOT NULL,
    status       VARCHAR(30) NOT NULL DEFAULT 'draft',
    content      JSONB NOT NULL DEFAULT '{}',
    cloudinary_url VARCHAR(1000),         -- optional PDF upload (Phase 2)
    sent_at      TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Indexes: `(tenant_id)`, `(workspace_id)`, `(contact_id)`.
RLS policy: `USING (tenant_id = current_setting('app.tenant_id')::uuid)`.

**Known gap:** `lead_id` is not stored on the `Proposal` row. The service receives a `LeadOut` and stores `contact_id`, but the original `lead_id` is not persisted, making `proposal → lead` forward tracing unavailable without a join through `hr_contacts`. A Phase 2 expand migration should add `lead_id UUID NULLABLE` to `proposals`. See §Failure Modes.

### REST API

| Method | Path | Description |
|---|---|---|
| `POST /api/v1/proposals/` | Generate | Create draft for a lead |
| `GET /api/v1/proposals/` | List | Paginated by `workspace_id` |
| `GET /api/v1/proposals/{id}` | Get | Single proposal |
| `POST /api/v1/proposals/{id}/send` | Mark sent | `draft → sent` transition |

Router registered in `corpmind/main.py` at prefix `/api/v1/proposals`.

### Frontend

```
apps/web/src/features/proposals/
├── types.ts                            — Proposal, ProposalListOut, PROPOSAL_STATUS_CONFIG
├── api/use-proposals.ts                — useProposals, useProposal, useGenerateProposal, useMarkProposalSent
└── ui/
    ├── proposal-status-badge.tsx
    ├── proposal-list.tsx               — paginated table, links to detail
    ├── generate-proposal-dialog.tsx    — lead selector, eligible stage guard
    └── proposal-content-view.tsx       — structured JSON renderer (title, body, extras, PDF link)

apps/web/src/app/(dashboard)/proposals/
├── page.tsx                            — list page + generate dialog
└── [id]/page.tsx                       — detail page + mark-sent action
```

Sidebar nav entry: `{ href: "/proposals", label: "Proposals", icon: FileText }`.

---

## Current Proposal Lifecycle

```
[Trainer] clicks "Generate proposal"
    │
    ▼
GenerateProposalDialog (frontend)
    │  selects a lead from eligible stages: meeting_completed | booked
    │
    ▼
POST /api/v1/proposals/
    │
    ▼
CRMService.get_lead(lead_id)           ← stage validation
    │  raises ValidationError if stage ∉ {meeting_completed, booked}
    │
    ▼
ProposalService.generate()
    │
    ▼
EuriClient.chat(task="proposal_generation", prompt_name="proposals.generate")
    │  routes to model per routing matrix (premium tier: outreach-class task)
    │  prompt template: ai/prompts/proposals/generate/v1.md
    │  inputs: contact_id, lead_stage, lead_score, lead_notes, meeting_at
    │
    ▼
_parse_content()                        ← JSON parsing with fallback to title+body stub
    │
    ▼
Proposal(status="draft") persisted      ← tenant_id from TenantContext (never trusted from caller)
    │
    ▼
ProposalGenerated event logged          ← structured log until event bus is wired
    │
    ▼
ProposalOut returned to frontend

[Trainer] reviews draft in /proposals/{id}
    │
    ▼
POST /api/v1/proposals/{id}/send        ← explicit trainer action
    │
    ▼
ProposalService.mark_sent()
    │  raises ConflictError if already sent
    │
    ▼
status="sent", sent_at=now() persisted
    │
    ▼
ProposalSent event logged
```

---

## Trigger Decision

### Why `meeting_completed` and `booked` — not earlier stages

| Stage | Rationale for exclusion |
|---|---|
| `discovered` | No meaningful signal — just a raw HR contact, no conversation |
| `engaged` | Outreach has started but no meeting context exists; a proposal at this stage is premature and damages credibility |
| `meeting_scheduled` | Meeting hasn't happened yet; no notes to draw from |
| `lost` | No commercial path; proposal would be ignored |
| `meeting_completed` | ✅ The trainer has met the HR; notes exist; temperature is highest |
| `booked` | ✅ Training is already confirmed; proposal is now a formal engagement document |

### Why not fully automatic (event-driven)?

The `meeting_completed` CRM stage transition fires a `crm.lead_stage_changed` domain event (emitted by `CRMService`). An automated trigger would listen to this event and call `ProposalService.generate()` without trainer input.

This was rejected because:
- **Trainer-specific context**: The best proposal requires the trainer to have added meeting notes. Firing immediately on stage change often means notes aren't yet in the system.
- **Quality over speed**: A trainer who surprises a contact with an unsolicited AI proposal is damaging their own brand. Human-in-the-loop at the *send* decision, not just the review.
- **Cost governance**: Each generation call costs LLM tokens. Auto-triggering on every stage change could generate proposals for leads that the trainer decides not to pursue.
- **Training-wheels mode**: The first week of any new tenant requires explicit approval for all agent-proposed actions (`automation.md`).

**Conclusion:** Manual trigger is correct for Phase 1. An optional auto-draft (with HITL approval before delivery) is the Phase 2 path, gated by a feature flag.

### Manual trigger — why this is not a limitation

The dialog is one click from the CRM pipeline board. A trainer who just completed a meeting can generate a proposal in under 60 seconds with the correct lead pre-selected.

---

## Inputs Used for Generation

The `proposals.generate` prompt receives these inputs:

| Field | Source | Notes |
|---|---|---|
| `contact_id` | `lead.contact_id` | Opaque reference; not used by the model directly |
| `lead_stage` | `lead.stage` | Grounds the tone (`meeting_completed` = warm, `booked` = formal) |
| `lead_score` | `lead.score` | 0–100; used as engagement signal in the prompt |
| `lead_notes` | `lead.notes` | Free-text CRM notes; the primary qualitative signal |
| `meeting_at` | `lead.meeting_scheduled_at` | ISO timestamp; used to anchor the timeline |

**Phase 2 inputs (not yet wired):**
- Trainer profile (specializations, past wins, pricing tiers) from `trainer_intel` module
- Contact's company profile from `hr_discovery` module
- Past campaign outcomes from `campaign_outcomes_{org}` Qdrant collection

These inputs are excluded from Phase 1 because the retrieval pipeline (`rag-retrieval.md`) adds complexity that is not justified until the basic happy path is validated end-to-end.

---

## Proposal Prompt Strategy

### File

`apps/api/src/corpmind/ai/prompts/proposals/generate/v1.md`

### Model selection

Task `"proposal_generation"` maps to the **premium** model tier in the Euri routing matrix (Claude Sonnet / GPT-4-class). This is correct because:
- Proposals are customer-facing, high-stakes documents.
- Quality directly affects the trainer's win rate and reputation.
- A cheaper model produces noticeably lower-quality structured content for complex multi-section outputs.

### Output format

The prompt requests **pure JSON** output (no markdown fences, no preamble) matching a defined schema:

```json
{
  "title": "...",
  "executive_summary": "...",
  "proposed_training": { "topic", "duration", "format", "participants" },
  "value_proposition": ["outcome 1", "outcome 2", "outcome 3"],
  "proposed_agenda": [{ "session": "...", "focus": "..." }, ...],
  "investment": "...",
  "call_to_action": "..."
}
```

The `_parse_content()` fallback in `service.py` handles malformed model output by wrapping the raw string in a `{"title": ..., "body": ...}` stub, ensuring a `Proposal` row is always created.

### Known gap: no prompt fixtures or evals

`ai/prompts/proposals/generate/` currently contains only `v1.md`. The `fixtures/` directory and `evals.yaml` required by `prompt-engineering.md` do not exist. This means:
- CI cannot run a Promptfoo eval on prompt changes.
- There is no regression baseline for proposal quality.

This is the highest-priority test gap for Sprint 7B.

---

## Human Approval Workflow

This implementation uses **implicit HITL** at the send step rather than an explicit LangGraph interrupt:

```
generate() → status="draft"
    [trainer reads and decides]
mark_sent() → status="sent"
```

The trainer is the approval gate. The draft sits indefinitely until they act. No automatic expiry, no background send.

### Why no LangGraph interrupt queue?

The LangGraph HITL pattern (`langgraph-agents.md`) uses a `workflow_checkpoints` interrupt that parks a running graph and resumes it on approval. This is appropriate for:
- Long-running multi-step workflows that need to be paused mid-flight.
- Workflows with a recipient count > 200 that must be reviewed before fan-out.

A proposal generation has neither property — it is a single synchronous call that completes immediately. The natural HITL gate is the trainer's own review-and-send action, not a workflow checkpoint. Using LangGraph here would be over-engineering.

### Phase 2: Richer HITL

When auto-draft is introduced (event-driven from `meeting_completed`), generated drafts should enter an approval queue (`proposal_approvals` table) before the trainer is notified. That path will use the notification system, not LangGraph, because there is still no long-running workflow to checkpoint.

---

## Sending Workflow

Current implementation: `mark_sent()` sets `status="sent"` and `sent_at=now()`. It does **not** dispatch the proposal through a channel adapter.

This is intentional for Phase 1. The trainer is expected to copy the generated content and send it through their own email client, WhatsApp, or in person. The `status="sent"` flag records their intent for CRM tracking purposes.

**Phase 2 sending path** (not yet implemented):
1. `mark_sent()` triggers `ProposalService.send_via_channel(proposal, channel)`.
2. Channel adapter dispatches through `ChannelAdapter.send()`.
3. `ComplianceGuardAgent.check()` runs before dispatch (required by `compliance-guard.md`).
4. Delivery status tracked via `outbound_messages` or a `proposal_deliveries` join table.
5. CRM lead stage auto-advances to `booked` (if currently `meeting_completed`) on confirmed delivery.

The Phase 2 path requires a compliance integration that is not yet scoped. It must not be added without a dedicated ComplianceGuard integration point.

---

## Compliance Requirements

1. **No send without trainer approval.** Current architecture satisfies this by design — `mark_sent()` is an explicit trainer action.

2. **Phase 2 channel dispatch must pass ComplianceGuard.** When direct channel sending is added, the send call must pass through `ComplianceGuardAgent.check()` before any adapter dispatch. There is no exception path.

3. **`cloudinary_url` PDF upload.** If a trainer uploads a PDF version of the proposal, the file must be signed by the backend before Cloudinary upload — the client must never hold the upload key (`security.md`).

4. **PII in `content` field.** The JSONB `content` column may contain contact names or company details inferred from CRM notes. This field is within the tenant's RLS boundary. It must be included in the DPDP/GDPR data export and erasure flows.

5. **Audit events.** `ProposalGenerated` and `ProposalSent` are currently logged as structured events. When the event bus is wired, both must write to `audit_events` for Enterprise-tier compliance.

---

## Failure Modes

### 1. EuriClient returns malformed JSON

**Mitigation:** `_parse_content()` fallback — wraps raw string in `{"title": raw[:200], "body": raw}`. A proposal record is always created. The `ProposalContentView` frontend component handles arbitrary `content` structure gracefully via the `extras` rendering path.

**Gap:** The fallback produces a low-quality proposal. The trainer sees raw model output, not structured sections. This should be surfaced as a warning badge in Phase 2.

### 2. EuriClient raises `BudgetExceededError`

**Behavior:** Exception propagates to the route handler → 422 response with `{code: "budget_exceeded", message: "..."}`. The frontend `generate-proposal-dialog.tsx` displays the `error.message` via `ApiError`.

### 3. Lead stage not eligible (e.g. `engaged`)

**Behavior:** `ValidationError` → 422 with clear message. Frontend guard in `GenerateProposalDialog` pre-filters leads to eligible stages, so this should only occur via direct API calls.

### 4. Network timeout during EuriClient call

**Behavior:** FastAPI request handler times out. No partial `Proposal` row is created (commit only occurs after `create()` succeeds). Idempotent to retry.

### 5. `lead_id` not stored on Proposal

**Impact:** Cannot directly query "all proposals for lead X" without joining through `contact_id`. Analytics and CRM drill-down are degraded.

**Mitigation plan:** Expand migration — add `lead_id UUID NULLABLE` to `proposals`, backfill from the generation request, set NOT NULL in a subsequent contract migration. This is a Phase 2 schema change requiring a separate ADR update.

### 6. Concurrent duplicate generation for same lead

**Behavior:** Multiple calls to `generate()` for the same `lead_id` each create a new `Proposal` row (no uniqueness constraint on `(contact_id, workspace_id)`). This is by design — re-generation is allowed, creating a history of drafts.

**Risk:** If the UI does not debounce the Generate button, a trainer could create multiple drafts. The `ProposalList` shows all drafts; the trainer must pick one to mark sent.

---

## Cost Controls

1. **Premium model routing.** `proposal_generation` task maps to premium models. Each call is estimated at ~2,000–4,000 tokens (prompt + output). At the Growth tier, this is approximately ₹1–3 per proposal.

2. **Pre-call estimator.** `EuriClient` runs the pre-call budget estimator before every call. If `tenant.spent + estimate > tenant.budget`, raises `BudgetExceededError`.

3. **No caching.** Per `euri-gateway.md`, personalized outreach-class outputs are never cached. Proposal generation is in this class — caching would return a previous tenant's proposal structure.

4. **No auto-trigger.** Manual trigger means the trainer consciously initiates a paid generation. No background job can trigger a generation without explicit user action.

5. **Tier limits.** Proposal generation counts against the tenant's AI run budget. The Starter tier (1,000 runs/month) can generate ~1,000 proposals before hitting the cap.

---

## Event Flow

```
POST /api/v1/proposals/
    │
    ├─► EuriClient.chat()
    │       └─► Langfuse span: {tenant_id, agent="ProposalAgent",
    │                           prompt_name="proposals.generate",
    │                           tokens_in, tokens_out, cost_inr, cached=false}
    │
    ├─► Proposal row inserted
    │
    └─► structlog.info("proposals.domain_event", event_type="ProposalGenerated",
                        proposal_id, tenant_id, contact_id)

POST /api/v1/proposals/{id}/send
    │
    ├─► Proposal row updated: status="sent", sent_at=now()
    │
    └─► structlog.info("proposals.domain_event", event_type="ProposalSent",
                        proposal_id, tenant_id)
```

**Phase 2:** Both events write to `audit_events` (append-only) when the event bus is wired. Enterprise-tier audit retention is 7 years.

---

## Sequence Diagram

```
Trainer          Frontend              API                EuriClient          DB
  │                  │                  │                     │               │
  │ click Generate   │                  │                     │               │
  │─────────────────►│                  │                     │               │
  │                  │ POST /proposals/ │                     │               │
  │                  │─────────────────►│                     │               │
  │                  │                  │ get_lead(lead_id)   │               │
  │                  │                  │────────────────────────────────────►│
  │                  │                  │◄────────────────────────────────────│
  │                  │                  │  stage check        │               │
  │                  │                  │  (ValidationError   │               │
  │                  │                  │   if ineligible)    │               │
  │                  │                  │                     │               │
  │                  │                  │ chat(proposal_gen)  │               │
  │                  │                  │────────────────────►│               │
  │                  │                  │                     │  LLM call     │
  │                  │                  │◄────────────────────│               │
  │                  │                  │ parse_content()     │               │
  │                  │                  │ Proposal(draft)     │               │
  │                  │                  │────────────────────────────────────►│
  │                  │                  │◄────────────────────────────────────│
  │                  │ ProposalOut      │                     │               │
  │                  │◄─────────────────│                     │               │
  │ review draft     │                  │                     │               │
  │◄─────────────────│                  │                     │               │
  │                  │                  │                     │               │
  │ click Mark sent  │                  │                     │               │
  │─────────────────►│                  │                     │               │
  │                  │ POST /{id}/send  │                     │               │
  │                  │─────────────────►│                     │               │
  │                  │                  │ update status=sent  │               │
  │                  │                  │────────────────────────────────────►│
  │                  │ ProposalOut      │                     │               │
  │                  │◄─────────────────│                     │               │
  │◄─────────────────│                  │                     │               │
```

---

## Security Review

| Concern | Status |
|---|---|
| Tenant isolation | ✅ Every query filtered by `TenantContext.org_id`. RLS defense-in-depth. |
| `tenant_id` from caller | ✅ Never trusted from request body — always from `TenantContext` (set by JWT middleware). |
| Prompt injection | ✅ `EuriClient` runs `PromptInjectionFilter` on inputs before reaching the model. `lead_notes` is user-supplied content and is filtered. |
| PII in LLM call | ✅ `PIIRedactor` runs in `EuriClient` before model call. `contact_id` passed as UUID (opaque). |
| PII in logs | ✅ `structlog` structured events contain UUIDs only — no names, emails, or phone numbers. |
| Cross-tenant leak | ✅ `ProposalRepo.find_by_id()` and `list_by_workspace()` both include `tenant_id` filter. A tenant B request for tenant A's proposal ID returns `None` → 404. |
| Over-generation DoS | ⚠️ No rate limit per tenant per hour on generation endpoint. Phase 2: add per-tenant Redis token-bucket rate limit (`security.md`). |
| PDF upload (cloudinary_url) | ⚠️ Phase 2: PDF upload must be signed by backend. Client must never hold upload key. Not implemented yet. |
| Audit logging | ⚠️ Domain events are `structlog`-only currently. Phase 2: write to `audit_events` table for Enterprise compliance. |

---

## Rollback Strategy

### If `ProposalService.generate()` introduces a regression

1. No feature flag is currently set on proposal generation. Phase 2 rollout should add `proposals.generation.v2` flag before routing matrix changes.
2. Rollback is a code revert (`git revert`) + Railway re-deploy. Estimated 5 minutes.
3. Existing `Proposal` rows are unaffected — they persist in the database regardless of service rollback.

### If the prompt `proposals.generate/v1.md` degrades

1. Roll back the prompt file commit.
2. The `EuriClient` prompt registry resolves `(name, version, env)` at call time — no service restart required after a prompt file rollback.
3. No `v2.md` exists yet. Until a second version is published, there is only one version to run.

### If the `proposals` table migration must be rolled back

The `proposals` table is part of the initial schema migration (`092be546f82c`). Rolling back this migration drops all proposal data. This should never happen in production outside a full database restore.

---

## Alternatives Considered

### 1. LangGraph multi-step proposal graph

A graph with nodes: `[fetch_trainer_profile → fetch_contact_context → generate_draft → human_review → send]`.

**Why rejected:** Adds significant operational complexity (graph state, checkpoint table, workflow_checkpoints writes) for a single-step generation. LangGraph graphs shine when there are multiple conditional branches, resumable mid-flight state, or parallel sub-agent fan-out. A single LLM call with a linear approval step has none of these properties. The modular service approach is simpler, more testable, and equally correct. Revisit in Phase 2 when multi-source RAG retrieval is added.

### 2. Auto-generate on `meeting_completed` event

A Celery task subscribed to the `crm.lead_stage_changed` event that fires `ProposalService.generate()` automatically.

**Why rejected:** See §Trigger Decision. The primary objections are: (a) meeting notes are often added minutes or hours after the stage transition, so auto-generation runs on incomplete input; (b) cost governance — automatic generation for every eligible stage change burns budget on leads the trainer decides not to pursue; (c) quality — a proposal the trainer didn't ask for and doesn't expect undermines trust in the platform. Manual trigger is the Phase 1 decision with a clear Phase 2 upgrade path.

### 3. Template-based proposal (no LLM)

A structured form where the trainer fills in fields and the system assembles a proposal from a Word/PDF template.

**Why rejected:** This is what trainers do today. It is exactly the manual work the platform exists to eliminate. An LLM-generated first draft that the trainer refines in 2 minutes is meaningfully better than a blank form.

### 4. Separate `proposals` microservice

Extract the proposals module into an independent service with its own database.

**Why rejected:** Stage 1 is a modular monolith by design (ADR-0001). Microservice extraction is a named scaling trigger in PRD §23, not a default. The `proposals` module currently handles ~1 proposal per meeting per trainer — there is no load justification for extraction.

---

## Consequences

### Positive
- Full proposal lifecycle is production-ready and end-to-end testable.
- Trainer can generate a structured, multi-section proposal in ~10 seconds after a meeting.
- All LLM observability (Langfuse traces, cost tracking) flows through Euri gateway automatically.
- Phase 2 path to auto-draft + channel dispatch is clearly scoped without requiring a schema rewrite.

### Negative
- `lead_id` is not stored on `Proposal` — forward-tracing from lead to proposal requires a join through `contact_id`. A Phase 2 expand migration is needed.
- No prompt fixtures or eval suite exists yet. Prompt regressions are not caught in CI.
- `mark_sent()` does not dispatch through a channel adapter — the trainer must send the proposal manually outside the platform. This is a Phase 1 limitation.

### Neutral
- Re-generation creates a new `Proposal` row rather than updating the existing one. This preserves history but requires the trainer to pick the correct draft in the list.
- The `cloudinary_url` column exists on the model but the upload flow is not implemented. The column is nullable and harmless until Phase 2.

---

## References

- [ADR-0001](0001-modular-monolith.md) — Modular monolith architecture
- [ADR-0002](0002-euri-as-sole-llm-egress.md) — Euri AI Gateway as sole LLM egress
- [ADR-0003](0003-postgres-rls-as-tenant-isolation-default.md) — RLS for tenant isolation
- [ADR-0004](0004-langgraph-for-agent-orchestration.md) — LangGraph agent topology (and when NOT to use it)
- [`apps/api/src/corpmind/modules/proposals/`](../../apps/api/src/corpmind/modules/proposals/) — Implementation
- [`apps/api/src/corpmind/ai/prompts/proposals/generate/v1.md`](../../apps/api/src/corpmind/ai/prompts/proposals/generate/v1.md) — Active prompt
- [`apps/api/tests/unit/test_proposal_service.py`](../../apps/api/tests/unit/test_proposal_service.py) — Unit test coverage
- [PRD §9.1](../../docs/PRD.md) — Agent roster and trigger matrix
- [PRD §23](../../docs/PRD.md) — Scaling triggers for microservice extraction
