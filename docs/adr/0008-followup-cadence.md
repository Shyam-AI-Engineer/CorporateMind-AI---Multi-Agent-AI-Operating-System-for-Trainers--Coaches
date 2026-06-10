# ADR-0008: Follow-Up Cadence Architecture

- **Status:** Accepted
- **Date:** 2026-06-10
- **Deciders:** Shyam-AI-Engineer (Tech Lead)
- **Supersedes:** —
- **Related ADRs:** ADR-0002 (Euri gateway), ADR-0003 (RLS tenancy), ADR-0004 (LangGraph agents), ADR-0005 (Celery), ADR-0006 (expand-then-contract), ADR-0007 (Proposal agent)

---

## Context

The inbound reply loop is complete up to one point and no further. When a contact replies to outreach, the system:

1. Syncs the reply into `inbox_messages` (Sprint 3).
2. Classifies its intent via `ReplyClassifierAgent` (Sprint 4B).
3. Drives CRM updates via `ReplyAutomationService` (Sprint 4C).

For two of the seven reply intents — `question` and `out_of_office` — step 3 produces a `FollowUpTask` row in status `pending`. **Nothing consumes those rows.** The Celery beat task that is meant to act on them, `advance_followup_cadence`, fires every 30 minutes but has a `# TODO` body:

```python
# apps/api/src/corpmind/workers/tasks/outreach.py  (current state)
def advance_followup_cadence(self: Task) -> None:
    log.info("outreach.cadence.start")
    # TODO(Phase 1): query due follow-ups, enqueue send_message for each
```

The result: a trainer sees a follow-up task appear in the CRM UI, but the platform never sends the re-engagement message. This breaks the core value loop the product is built on — *reply → classify → CRM update → follow-up → re-engagement send*. The follow-up tasks accumulate forever in `pending`.

This ADR records the architecture for closing that loop: a context-aware follow-up generation + send cadence, governed by compliance, quiet hours, and a deliberate human-in-the-loop stance for reputation-critical replies.

### Constraints (inherited, non-negotiable)

- Every LLM call routes through the Euri AI Gateway (ADR-0002). No direct provider SDK imports.
- Every write table carries `tenant_id` with RLS (ADR-0003).
- A new task class in the routing matrix requires an ADR (ADR-0002 / `ai-cost-governance.md`) — this document is that record.
- Every outbound message passes through `ComplianceGuard` before dispatch (`compliance-guard.md`). No exception path.
- Cross-module rule (CLAUDE.md): the worker may compose multiple module *services*, but no module imports another module's `repo`/`models`. Cross-module reads use raw `text()` SQL.
- Quiet hours and training-wheels mode apply to all autonomous sends (`automation.md`).

---

## Decision

Implement the follow-up cadence as a **two-tier Celery fan-out** (mirroring the proven `inbox.sync_all_active_connections` pattern) plus a **new follow-up generation surface** in `OutreachService`, backed by **two new versioned prompts** routed to the premium model tier.

The cadence **drafts and routes**; it does not blindly auto-send. Reputation-critical replies (`question`) are drafted and parked for human approval unless the model can answer them safely from trainer-profile facts. Low-touch re-engagement (`out_of_office`) auto-sends once compliance passes and the tenant is past training-wheels mode.

The send half of the existing outreach pipeline (`OutreachService.send_message` → `tasks.outreach.send_message` → `_run_send`) is reused wholesale. The cold-outreach generation half is **not** reused (see §3).

---

## 1. Problem Statement

| Dimension | Statement |
|---|---|
| **What is broken** | `FollowUpTask` rows reach `pending` and are never acted on. The cadence worker is a stub. |
| **Who is affected** | Every tenant whose contacts ask a question or reply with an out-of-office auto-responder. |
| **Business impact** | The reply→re-engagement loop — the highest-leverage moment in the funnel, when a contact has *already engaged* — silently dead-ends. Trainers lose warm leads. |
| **Why now** | All upstream machinery (classification, CRM automation, task creation, compliant send pipeline) is built and tested. The cadence is the single missing link, and it is the highest-ROI increment relative to its size. |
| **Why it is non-trivial** | "Fill in the TODO" undersells it. A correct follow-up must answer the contact's actual question (or decline safely), thread into the original email, respect quiet hours and frequency caps, and avoid double-sends across overlapping beats — none of which the cold-outreach path provides. |

---

## 2. Existing `follow_up_tasks` Lifecycle

### Table (created in `b9c5d3e2f7a4_add_crm_automation_tables`)

```sql
CREATE TABLE follow_up_tasks (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                   UUID NOT NULL,            -- RLS column (TenantBase)
    workspace_id                UUID NOT NULL,
    lead_id                     UUID,                     -- nullable: bounce/no live lead
    contact_id                  UUID NOT NULL,
    type                        VARCHAR(50) NOT NULL,     -- question_followup | out_of_office_followup
    status                      VARCHAR(30) NOT NULL DEFAULT 'pending',  -- pending → done | cancelled
    scheduled_for               TIMESTAMPTZ,              -- NULL = do-asap; future = timed reminder
    source_inbox_message_id     UUID NOT NULL,
    source_outbound_message_id  UUID,                     -- nullable: ad-hoc sends
    notes                       TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_follow_up_tasks_tenant_source
        UNIQUE (tenant_id, source_inbox_message_id)
);
```

Indexes: `(lead_id)`, `(status)`, `(scheduled_for)`. RLS: hardened `NULLIF` predicate (post-`b9f4e7d2a1c8`).

### How rows are created (today)

`ReplyAutomationService` ([crm/automation.py](../../apps/api/src/corpmind/modules/crm/automation.py)) creates exactly two task types:

| Intent | `type` | `scheduled_for` | `notes` |
|---|---|---|---|
| `question` | `question_followup` | `NULL` (do-asap) | "Question from reply — answer requested." |
| `out_of_office` | `out_of_office_followup` | `now() + 72h` (`_OOO_FOLLOWUP_HOURS`) | "Out-of-office reply — follow up after return." |

### Lifecycle today vs. after this ADR

```
TODAY:
  pending ──(nothing consumes)──►  ∞

AFTER THIS ADR:
  pending ──claim──► processing ──┬─ auto-eligible ──► (send_message) ──► done
                                  ├─ needs approval ──► awaiting_approval ──► done | cancelled
                                  └─ blocked/unresolvable ──────────────────► cancelled
```

**Schema impact (expand, additive, reversible — ADR-0006):**
- Extend the `status` vocabulary to include `processing` and `awaiting_approval` (string column; no enum migration).
- Add nullable `result_outbound_message_id UUID` so a completed task links to the message it produced (for the Activity Timeline). Backfilled forward-only; never set NOT NULL in Phase 1.
- Add nullable `attempts INTEGER NOT NULL DEFAULT 0` for retry/visibility accounting.

The `UNIQUE(tenant_id, source_inbox_message_id)` constraint already guarantees one task per reply; this ADR adds *send-time* idempotency on top (§8, §9).

---

## 3. Why `generate_message()` Cannot Be Reused Directly

`OutreachService.generate_message()` ([outreach/service.py:63](../../apps/api/src/corpmind/modules/outreach/service.py#L63)) is structurally incapable of producing a follow-up. Three blockers:

### Blocker 1 — Hardwired cold prompt

The method always calls `prompt_name="outreach.email"`. That prompt's role is literally *"Write a single personalized **cold** outreach email"* with first-introduction few-shots. Feeding a follow-up through it produces a **second cold pitch** to a contact who has already replied.

### Blocker 2 — No context inputs

`_build_prompt_inputs()` ([outreach/service.py:292](../../apps/api/src/corpmind/modules/outreach/service.py#L292)) emits only trainer + contact profile fields. There is no slot for:
- the reply text (`reply_text`)
- the original email (`original_subject`, `original_body`)
- the lead stage (`lead_stage`)
- elapsed time (`days_since`)

### Blocker 3 — Wrong semantics for `question`

A `question_followup` must *answer a question*. A cold-copy generator has neither the question nor any directive to respond to one. Sending cold copy here is both useless to the contact and, under the 2-messages-per-7-days frequency cap, spam-adjacent.

### What IS reused

The *persistence + return tail* of `generate_message` (build `OutboundMessage`, save `draft`, return DTO) is sound and reused. The decision is therefore a **sibling method** — `OutreachService.generate_followup(...)` — that selects a follow-up prompt, builds follow-up inputs, and reuses that tail. The cold path is left byte-for-byte unchanged (Engineering Philosophy: stability over cleverness).

```
generate_message()      → outreach.email            (UNCHANGED — cold first-touch)
generate_followup()     → outreach.followup.question | outreach.followup.nudge   (NEW)
                          ↘ shares: draft persistence, OutboundMessageOut return
send_message()          → REUSED WHOLE (compliance + enqueue + dispatch)
```

---

## 4. Follow-Up Prompt Architecture

Two prompts, not one — because the two task types have different jobs. Both follow `prompt-engineering.md`: versioned `vN.md`, structured-JSON output, fixtures + `evals.yaml`, gated in CI by Promptfoo (≥ 95% pass), routed to the **premium** tier in `ai/routing.py` (a new task class → recorded by this ADR).

```
apps/api/src/corpmind/ai/prompts/outreach/followup/
├── question/
│   ├── v1.md
│   ├── fixtures/
│   │   ├── 01_answerable_scope_question.yaml
│   │   ├── 02_unanswerable_pricing_question.yaml
│   │   ├── 03_logistics_question_meeting_scheduled.yaml
│   │   └── 04_injection_in_reply_text.yaml
│   └── evals.yaml
└── nudge/
    ├── v1.md
    ├── fixtures/
    │   ├── 01_ooo_back_after_break.yaml
    │   ├── 02_sparse_context.yaml
    │   └── 03_hinglish_reengagement.yaml
    └── evals.yaml
```

### `outreach.followup.question/v1.md`

- **Role:** "You are the trainer replying to a question an HR contact asked in response to your outreach. Answer truthfully and concisely using **only** the facts in the trainer profile."
- **Inputs:** `original_subject`, `original_body`, `reply_text`, `lead_stage`, trainer fields, contact fields.
- **Output schema:**
  ```json
  {
    "subject": "string (Re: …, ≤ 80 chars)",
    "body": "string (60–160 words)",
    "answered": true,
    "needs_human_review": false,
    "language_used": "ISO-639-1"
  }
  ```
- **Critical safety rule:** if the question cannot be answered from profile facts (specific pricing, availability, custom scope, contractual terms), set `needs_human_review=true` and draft a deflection ("let me confirm the specifics and revert / quick 15-min call") instead of inventing. This is the *correctness-over-speed* pillar made executable.

### `outreach.followup.nudge/v1.md`

- **Role:** "Write a brief, warm re-engagement that references the earlier email; assume the contact was away and is now back."
- **Inputs:** `original_subject`, `original_body`, `days_since`, `lead_stage`, trainer fields, contact fields.
- **Output schema:** `{ "subject": "Re: …", "body": "…", "language_used": "…" }`.

### Routing

| Task class | Tier | Rationale |
|---|---|---|
| `followup_question` | Premium (Claude Sonnet/Opus class) | Answering wrong damages the trainer's reputation; high stakes. |
| `followup_nudge` | Premium | Re-engagement copy is customer-facing personalized text (never cacheable per `euri-gateway.md`). |

Neither prompt is cacheable (`cacheable: false`) — both are personalized.

---

## 5. HITL Decision Matrix

A follow-up auto-sends **only if every condition holds** (intersection of `automation.md` auto-execute eligibility and reply-specific safety). Otherwise it is drafted and routed to `awaiting_approval`.

| Condition | `question_followup` | `out_of_office_followup` |
|---|---|---|
| Tenant past training-wheels (week 1) | Required | Required |
| Follow-up category in tenant auto-execute allowlist | Required | Required |
| ComplianceGuard pre-pass (opt-in, freq-cap, unsubscribe) | Required | Required |
| Recipient count ≤ 200 (always 1 here) | ✅ trivially | ✅ trivially |
| Estimated cost ≤ tenant auto-approve threshold | Required | Required |
| `needs_human_review == false` (model could answer safely) | **Required** | N/A (no question) |
| **Default route when any fails** | `awaiting_approval` | `awaiting_approval` |

### Resulting policy

```
question_followup:
  model answered safely + all gates pass + past training-wheels
      → AUTO-SEND
  model set needs_human_review=true  OR  training-wheels  OR  gate fail
      → DRAFT → awaiting_approval   (trainer answers/edits/approves in 8C)

out_of_office_followup:
  all gates pass + past training-wheels
      → AUTO-SEND
  training-wheels OR gate fail
      → DRAFT → awaiting_approval
```

**Phase note:** The `awaiting_approval` *queue surface* (endpoint + UI) ships in Sprint 8C. In 8A/8B, `question_followup` drafts are still **created and parked** in `awaiting_approval` — they simply wait for the 8C UI to action them. Nothing reputation-critical auto-sends before the human-review surface exists.

---

## 6. Quiet-Hours Policy

Per `automation.md`: no outbound to a recipient outside their local **08:00–21:00** unless flagged urgent and HITL-approved. This is **not enforced anywhere today** — neither the send pipeline nor the (absent) cadence checks it. A `scheduled_for=NULL` "do-asap" question task could otherwise fire at 03:00 local.

### Decision

The cadence enforces quiet hours at **claim time**, before generation:

1. Resolve the recipient's local timezone. Phase 1 source order: contact's company HQ region → workspace `Org.timezone` → `Asia/Kolkata` default. (Per-contact timezone is a Phase 2 enrichment.)
2. If the current local time is inside 08:00–21:00 → proceed.
3. If outside → **re-stamp** `scheduled_for` to the next local 08:00 and return the task to `pending` (no send, no wasted LLM spend). The next beat picks it up in-window.

This keeps quiet-hours logic in one place (the cadence) and avoids burning premium tokens on a draft that compliance-by-policy would hold. Urgent override is out of scope for Phase 1 (no urgent-flag path exists on follow-up tasks).

```
claim → quiet-hours check ──in-window──► generate → ...
                          └─out-window──► UPDATE scheduled_for = next_local_0800,
                                          status = 'pending'  (deferred, no spend)
```

---

## 7. Email Threading Strategy

A follow-up that does not thread into the original conversation reads as a fresh cold pitch and hurts deliverability. Today, `_run_send` ([outreach.py:154](../../apps/api/src/corpmind/workers/tasks/outreach.py#L154)) mints a **new** `smtp_message_id` per send and sets **no** `In-Reply-To`/`References` headers.

### Decision

Thread follow-ups into the original outbound's RFC-2822 message chain:

1. Resolve the original outbound's `smtp_message_id` via `source_outbound_message_id` (raw SQL on `outbound_messages`, same technique as `_resolve_outbound`).
2. The follow-up draft carries the original's id as its threading anchor.
3. Extend the channel `OutboundMessage` schema and `EmailSMTPAdapter` to set:
   - `In-Reply-To: <original_smtp_message_id>`
   - `References: <original_smtp_message_id>`
   - Subject prefixed `Re: ` (de-duplicated if the original already starts with `Re:`).
4. The follow-up still mints its **own** `smtp_message_id` (write-before-send invariant preserved) so its own replies can be matched by `inbox.match_reply` later.

```
original outbound:  Message-ID: <A@domain>
follow-up send:     Message-ID: <B@domain>
                    In-Reply-To: <A@domain>
                    References:  <A@domain>
                    Subject:     Re: <original subject>
```

This is a backward-compatible adapter enhancement: cold sends (no threading anchor) keep the current behaviour.

---

## 8. Task-Claiming Strategy

The cadence runs cross-tenant on a schedule; overlapping beats and per-tenant fan-out mean the same `pending` row could be picked up twice. Claiming must be atomic.

### Two-tier fan-out (mirrors `inbox.sync_all_active_connections`)

```
advance_followup_cadence            [beat, every 30 min, BYPASSRLS role]
  │  sweep: SELECT DISTINCT tenant_id
  │         FROM follow_up_tasks
  │         WHERE status = 'pending'
  │           AND (scheduled_for IS NULL OR scheduled_for <= now())
  │
  └─► process_tenant_followups.apply_async(tenant_id)   [one subtask per tenant]
        │  set_tenant_context(ctx) + set_rls_tenant(tenant_id)
        │  batch cap: LIMIT 50 per tenant per run  (noisy-neighbour guard)
        │
        └─ for each due task:  ATOMIC CLAIM
```

### Atomic claim (DB-level)

A single guarded UPDATE wins the row; losers see zero rows and skip:

```sql
UPDATE follow_up_tasks
SET    status = 'processing', attempts = attempts + 1, updated_at = now()
WHERE  id = :task_id
  AND  tenant_id = :tenant_id
  AND  status = 'pending'
RETURNING id;
```

- If `RETURNING` yields the row → this worker owns it; proceed.
- If it yields nothing → another worker claimed it; skip silently.

This is the primary concurrency guarantee. RLS + explicit `tenant_id` keep the claim tenant-scoped even under the fan-out subtask.

### Terminal transitions

| Outcome | Status set | Side effect |
|---|---|---|
| Auto-sent | `done` | `result_outbound_message_id` set; `followup_sent` activity written |
| Routed to human | `awaiting_approval` | draft persisted; activity written |
| Compliance block / no contact / unresolvable outbound | `cancelled` | `notes` appended with reason; activity written |
| Quiet-hours deferral | back to `pending` | `scheduled_for` re-stamped; no spend |
| Transient error (LLM/DB) | back to `pending` | `attempts` already incremented; Celery retry / next beat |

---

## 9. Redis Lock Strategy

The DB claim (§8) is authoritative. The Redis lock is **belt-and-suspenders** against double *dispatch* in the window between claim and the `send_message` enqueue (e.g., a worker crash after claim but before commit, then a retry), mirroring the existing `outreach:sent:{message_id}` pattern.

| Key | Purpose | TTL | Set when |
|---|---|---|---|
| `followup:processing:{task_id}` | Dispatch guard | 600s (NX) | Acquired right after the DB claim, before generation |
| `outreach:sent:{message_id}` | Existing send-idempotency (unchanged) | 7 days | After successful `_run_send` |

```
acquire SET followup:processing:{task_id} NX EX 600
   ├─ acquired → generate → (eligibility) → send_message / park → set status
   └─ not acquired → another dispatch in flight → skip (DB claim already prevents dup,
                                                        this prevents the rare race)
```

The follow-up's eventual `send_message` reuses the `outreach:sent:{message_id}` lock for the actual network send, so the existing 7-day dedup covers the dispatch itself. The new `followup:processing` lock only guards the *generate-then-enqueue* span. Lock is best-effort; correctness does not depend on it (the DB claim does).

---

## 10. Compliance Integration

**No new compliance code.** Every follow-up is an outbound message and goes through the existing gate by construction:

```
generate_followup()  → OutboundMessage(status="draft")
        │
        ▼
send_message(draft.id)                 ← OutreachService, REUSED WHOLE
        │  runs in order:
        │    check_opt_in
        │    check_frequency_cap        ← 2 marketing msgs / 7 days / cross-channel
        │    check_unsubscribe
        │  BLOCKED → status="blocked"; cadence sets task → cancelled
        │  PASS    → status="queued"; enqueue tasks.outreach.send_message
        ▼
_run_send                              ← re-runs ALL THREE checks immediately before dispatch
        │  (conditions can change between draft and send)
        │  writes AuditEvent(event_type="message.sent") on success
        ▼
EmailSMTPAdapter.send (threaded — §7)
```

### Frequency-cap interaction (called out explicitly)

The original outreach already counted **1** message in the trailing 7 days. A follow-up within that window counts **2** — still at the cap, so it passes. A *second* follow-up in the same window would be **blocked**, which is the correct, desired behaviour (we do not spam). The cadence does not special-case this; it lets ComplianceGuard decide and marks the task `cancelled` with the block reason on a `BLOCKED` outcome.

### Audit & PII

- Every send writes `AuditEvent(message.sent)` (existing). Every cadence decision also writes a `crm_activities` row (`followup_sent` | `automation_failed`) so the Activity Timeline reflects the action.
- The decrypted reply snippet (§Failure Modes) is passed to the LLM, where `PIIRedactor` + `PromptInjectionFilter` run inside `EuriClient` before the model — the `reply_text` is untrusted counterparty content and is filtered there (`security.md`). It is never logged.

---

## 11. Failure Modes

### 1. Reply body is encrypted and truncated
`inbox_messages.body_snippet_enc` is AES-256-GCM, ~500 chars, `body_truncated=True`. **Mitigation:** decrypt via an `InboxService` accessor (keeps encryption ownership in the inbox module — the worker never touches ciphertext). **Gap:** a long multi-part question may be clipped; the model answers on the snippet. Acceptable for Phase 1; documented. Full-body storage is a Phase 2 inbox enhancement.

### 2. `source_outbound_message_id` is NULL (ad-hoc send)
No original email to thread into or quote. **Mitigation:** fall back to a non-threaded follow-up (no `In-Reply-To`); the nudge/question prompt receives empty `original_*` inputs (the eval fixtures cover sparse context).

### 3. LLM returns malformed JSON
**Mitigation:** the same parse-with-`ValidationError` discipline as `generate_message._parse_copy`. On parse failure the task returns to `pending` (transient) up to `attempts` ceiling, then → `cancelled` with reason. No draft is persisted on parse failure (commit only after a valid draft).

### 4. `needs_human_review=true` but 8C queue not yet shipped
**Behaviour (8A/8B):** draft persisted, task → `awaiting_approval`, visible via the existing follow-up list (status filter). It simply waits. No auto-send. This is safe by design.

### 5. Contact opted out / over frequency cap between task creation and send
**Behaviour:** `send_message` (or the worker's `_run_send` re-check) returns `BLOCKED`; cadence sets task → `cancelled` with the block reason; `automation_failed` activity written. No send. Correct.

### 6. Double dispatch across overlapping beats
**Mitigation:** atomic DB claim (§8) is authoritative; `followup:processing` Redis NX lock (§9) covers the generate→enqueue race; `outreach:sent` lock covers the network send. Three layers.

### 7. Quiet-hours timezone unknown
**Mitigation:** fallback chain HQ region → `Org.timezone` → `Asia/Kolkata`. Worst case a send lands in IST business hours, which is the dominant tenant base.

### 8. Tenant exceeds AI budget mid-cadence
**Behaviour:** `EuriClient` raises `BudgetExceededError` during `generate_followup`; the task returns to `pending` (not cancelled — budget resets next period). Surfaced via the existing budget banner. Non-critical workflows refuse to start at 100% per `ai-cost-governance.md`.

### 9. Worker crash mid-task
**Behaviour:** `acks_late=True` re-queues; `attempts` was already incremented at claim; the row is in `processing`. **Gap:** a row stuck in `processing` after a hard crash needs a reaper. **Mitigation:** a sweep that resets `processing` rows older than the `time_limit` back to `pending` (folded into the beat sweep, or the existing DLQ reaper).

---

## 12. Rollback Strategy

Every increment ships behind a kill-switch flag and is reversible without data loss.

### Feature flags

| Flag | Default | Controls |
|---|---|---|
| `outreach.followup.generation` | off | `generate_followup` availability (8A) |
| `outreach.followup.cadence` | off | the beat worker actually sending (8B) — **kill switch** |
| `outreach.followup.auto_send` | off | auto-send vs. always-park (8B/8C) |
| `ui.followup.approval_queue` | off | 8C approval surface |

`outreach.followup.cadence` is a `kill_switch: true` flag: flipping it off pauses all autonomous follow-up sends at the next beat. Tasks remain in `pending`/`processing` and resume safely when re-enabled (claim is idempotent).

### Rollback by layer

1. **Cadence misbehaves (mass-send risk):** flip `outreach.followup.cadence` off → beat becomes a no-op within ≤ 30 min (next beat) or instantly if the running beat is also gated. Pause the `outreach` Celery queue for immediate stop (`incident-response.md`).
2. **Prompt degrades:** roll back `outreach.followup.{question,nudge}/vN.md`; the Euri registry resolves `(name, version, env)` at call time — no redeploy. If a routing-matrix entry changes, this ADR is updated (routing change ⇒ ADR per `prompt-engineering.md`).
3. **Code regression:** `git revert` + Railway redeploy (~5 min). `follow_up_tasks` rows are unaffected.
4. **Schema rollback:** the 8B expand migration (status values, `result_outbound_message_id`, `attempts`) is additive and nullable — the down-migration drops the added columns; pre-existing rows and the `pending → done|cancelled` core lifecycle are untouched (ADR-0006 expand-then-contract; no contract step in the same release).
5. **Channel threading regression:** the `In-Reply-To` enhancement is additive on the adapter; reverting it falls back to non-threaded sends — follow-ups still deliver, just not threaded.

---

## 13. Sequence Diagrams

### 13.1 Happy path — out-of-office nudge, auto-sent

```
Beat            CadenceSweep        TenantSubtask      OutreachSvc     Compliance    SMTP      DB
 │ every 30m       │                    │                 │              │           │        │
 │────────────────►│ SELECT DISTINCT    │                 │              │           │        │
 │                 │ tenant_id (due)    │                 │              │           │        │
 │                 │───────────────────────────────────────────────────────────────────────►│
 │                 │◄───────────────────────────────────────────────────────────────────────│
 │                 │ fan-out per tenant │                 │              │           │        │
 │                 │───────────────────►│ set RLS + ctx   │              │           │        │
 │                 │                    │ claim (UPDATE…RETURNING)        │           │        │
 │                 │                    │───────────────────────────────────────────────────►│
 │                 │                    │◄──────────────────────────────────────────── row ───│
 │                 │                    │ quiet-hours OK  │              │           │        │
 │                 │                    │ acquire redis NX│              │           │        │
 │                 │                    │ hydrate ctx (reply snippet, original, lead, trainer)│
 │                 │                    │───────────────────────────────────────────────────►│
 │                 │                    │◄───────────────────────────────────────────────────│
 │                 │                    │ generate_followup(nudge)        │           │        │
 │                 │                    │────────────────►│ Euri chat     │           │        │
 │                 │                    │                 │ (premium)     │           │        │
 │                 │                    │◄────────────────│ draft         │           │        │
 │                 │                    │ eligibility: PASS (past TW, allowlist, cost OK)      │
 │                 │                    │ send_message(draft.id)          │           │        │
 │                 │                    │────────────────►│ opt-in/freq/unsub          │        │
 │                 │                    │                 │─────────────►│ PASS       │        │
 │                 │                    │                 │ status=queued; enqueue send_message │
 │                 │                    │                 │ ───────────────────────────────►(Celery)
 │                 │                    │ task → done; result_outbound_message_id; activity    │
 │                 │                    │───────────────────────────────────────────────────►│
 │                 │                    │                 │              │           │        │
 (async)           │                    │   _run_send: re-check compliance → threaded send     │
 │                 │                    │                 │─────────────►│──────────►│ Re:… │
 │                 │                    │                 │ AuditEvent(message.sent)            │
```

### 13.2 Question reply — model defers to human

```
TenantSubtask      OutreachSvc      Euri           DB
 │ claim OK            │              │             │
 │ generate_followup(question)        │             │
 │───────────────────►│ chat(premium) │             │
 │                    │──────────────►│             │
 │                    │◄──────────────│ {answered:false, needs_human_review:true, body:deflection}
 │ eligibility: needs_human_review=true → DO NOT auto-send                  │
 │ persist draft; task → awaiting_approval; activity "followup_drafted"     │
 │────────────────────────────────────────────────────────────────────────►│
 │                    │              │             │
 (8C) Trainer opens approval queue → edits/answers → approve → send_message(draft.id)
```

### 13.3 Compliance block — task cancelled

```
TenantSubtask      OutreachSvc      Compliance      DB
 │ claim OK            │               │            │
 │ generate_followup → draft           │            │
 │ send_message(draft.id)              │            │
 │───────────────────►│ check_opt_in   │            │
 │                    │──────────────►│ (or freq-cap / unsubscribe)
 │                    │◄──────────────│ BLOCKED      │
 │                    │ status=blocked │            │
 │◄───────────────────│ SendMessageResponse(blocked)│
 │ task → cancelled (notes += reason); activity "automation_failed"         │
 │─────────────────────────────────────────────────────────────────────────►│
```

### 13.4 Quiet-hours deferral — no spend

```
TenantSubtask                         DB
 │ claim OK (status=processing)         │
 │ resolve tz → local 03:14 (outside 08:00–21:00)
 │ UPDATE scheduled_for = next_local_0800, status = 'pending'
 │─────────────────────────────────────►│
 │ release redis lock; no LLM call, no send
 │ (next in-window beat re-claims)
```

---

## Phased Rollout Plan

Each phase is independently shippable, flag-gated, and leaves the system in a correct state. No phase auto-sends anything reputation-critical before 8C exists.

### Sprint 8A — Generation only

**Goal:** prove context-aware follow-up *drafting* end-to-end, with zero autonomous sending.

- New prompts `outreach.followup.question/v1.md` + `outreach.followup.nudge/v1.md` with fixtures + `evals.yaml`; wired into the Promptfoo CI gate.
- New routing-matrix task classes `followup_question`, `followup_nudge` (premium tier) — covered by this ADR.
- `InboxService.get_decrypted_snippet(inbox_message_id)` accessor (encryption stays in the inbox module).
- `OutreachService.generate_followup(...)` — selects prompt by task type, builds follow-up inputs, reuses the draft-persist tail. Cold path untouched.
- Flag: `outreach.followup.generation` (default off).
- **No worker, no sending.** Drafts can be produced via service/test invocation and inspected.
- Tests: unit (input building, prompt selection, parse + safety-flag handling), prompt evals green.
- **Exit criteria:** a follow-up draft can be generated from a real `FollowUpTask` + hydrated context and is schema-valid; `needs_human_review` is honoured in the returned DTO.

### Sprint 8B — Worker automation

**Goal:** close the loop for the safe, low-touch path; park the rest.

- Expand migration: `status` vocabulary (`processing`, `awaiting_approval`), `result_outbound_message_id`, `attempts` (additive, reversible — ADR-0006).
- `FollowUpTaskRepo.list_due(limit)` (RLS-scoped) + BYPASSRLS distinct-tenant sweep helper.
- Implement `advance_followup_cadence` (sweep + fan-out) and `process_tenant_followups(tenant_id)` (claim → quiet-hours → hydrate → generate → eligibility → send/park → transition).
- Atomic DB claim (§8) + `followup:processing` Redis NX lock (§9).
- Quiet-hours enforcement (§6) with the timezone fallback chain.
- Email threading (§7): extend channel `OutboundMessage` + `EmailSMTPAdapter` with `In-Reply-To`/`References`/`Re:`.
- Stuck-`processing` reaper folded into the sweep.
- Flags: `outreach.followup.cadence` (kill switch), `outreach.followup.auto_send`.
- **Policy:** `out_of_office_followup` auto-sends when eligible; `question_followup` is **always parked** in `awaiting_approval` (8C surface not yet built).
- Rollout cadence (`feature-flags.md`): shadow → 5% → 25% → 50% → 100% by tenant cohort, green dashboards at each step.
- Tests: unit (due-windows, eligibility matrix, quiet-hours re-stamp, claim race), integration (testcontainers: seed task+contact+lead+original outbound → run subtask → assert draft, compliance ran, status transition, activity, threading headers), compliance regression (non-opted-in / over-cap → cancelled), tenant-isolation regression (tenant B's tasks not processed under tenant A).
- **Exit criteria:** OoO follow-ups send end-to-end through ComplianceGuard, threaded, within quiet hours, idempotently; question follow-ups land in `awaiting_approval`; kill switch verified.

### Sprint 8C — HITL approval

**Goal:** give the human the surface to action parked `question_followup` drafts, then allow safe auto-send of model-answered questions.

- Approval queue surface: either extend the campaign approval pattern or a dedicated `GET /api/v1/followups/approvals` + `POST /{id}/approve` | `/{id}/reject` (audited; `tenant_id` from context).
- Frontend: a Follow-Ups → "Needs review" tab; trainer reads the reply + draft, edits the answer, approves (→ `send_message`) or rejects (→ `cancelled`).
- Enable `question_followup` auto-send **only** when `needs_human_review=false` AND past training-wheels AND allowlisted (the matrix in §5 fully activates).
- Training-wheels integration: week-1 tenants route *all* follow-ups to approval regardless of intent.
- Flag: `ui.followup.approval_queue`.
- Tests: API (approve/reject transitions, audit rows, tenant isolation), frontend (Vitest component + Playwright journey: parked draft → edit → approve → sent).
- **Exit criteria:** a parked question draft can be reviewed, edited, and approved into a compliant threaded send; rejection cancels cleanly; week-1 tenants see everything gated.

---

## Alternatives Considered

### 1. Reuse `generate_message()` with a flag
Add a `is_followup` boolean and branch inside the cold-outreach method. **Rejected:** pollutes the stable first-touch path with follow-up concerns, and still leaves the prompt/inputs problem (§3) unsolved. A sibling method keeps both paths simple and independently testable (simplicity-over-abstraction).

### 2. Single unified follow-up prompt
One prompt handling both question and nudge via a `mode` input. **Rejected:** the jobs differ fundamentally (answer-a-question with truthfulness gating vs. warm re-engagement). A single prompt would dilute both and complicate the eval suite. Two focused prompts score and regress independently.

### 3. LangGraph workflow for the cadence
Model the cadence as a checkpointed graph (`hydrate → generate → comply → send`). **Rejected (per ADR-0004 / ADR-0007 reasoning):** this is a short, linear, non-resumable sequence per task. A Celery fan-out with an atomic DB claim is simpler, observable, and matches the existing `inbox.sync_all_active_connections` pattern. Revisit only if multi-step branching (e.g., multi-touch sequences) is added.

### 4. Auto-send question follow-ups from day one
Let the model answer and send without a human gate. **Rejected:** answering an HR contact's question incorrectly directly damages the trainer's reputation — the exact failure the *correctness-over-speed* and *governance-over-chaos* pillars exist to prevent. The `needs_human_review` gate + 8C queue is the safe path; auto-send is enabled only for model-confident answers after the human surface exists.

### 5. Enforce quiet hours in the send pipeline instead of the cadence
Put the 08:00–21:00 check inside `_run_send`. **Rejected for Phase 1:** the cadence is the only autonomous, scheduled sender; enforcing at claim time avoids burning premium LLM tokens on a draft that policy would hold. (A pipeline-level check is a reasonable Phase 2 defense-in-depth addition for *all* sends, not just follow-ups.)

---

## Consequences

### Positive
- Closes the core reply→re-engagement loop — the highest-leverage funnel moment.
- Zero new compliance code: follow-ups inherit the full gate by reusing `send_message`.
- Two-tier fan-out reuses a proven, tested pattern; atomic claim makes double-send structurally impossible.
- Quiet-hours enforcement lands centrally (a pre-existing platform gap), benefiting the whole product's trust posture.
- Reputation-critical replies are human-gated by default; nothing risky ships before the review surface.

### Negative
- New premium-tier LLM spend per follow-up (cost-governed; budget-gated; non-cacheable). Tracked per tenant.
- Reply snippet is truncated to ~500 chars — long questions may be partially answered until Phase 2 full-body storage.
- Email threading requires an adapter change touching the send path (mitigated by additive, backward-compatible headers).
- Three-phase rollout means OoO and question paths go live at different times; documented and flag-gated.

### Neutral
- `follow_up_tasks` gains `processing`/`awaiting_approval` states and two nullable columns — additive, reversible.
- Per-contact timezone is approximated (HQ/org/IST fallback) until a Phase 2 enrichment.
- The `awaiting_approval` state exists from 8B but is only actionable from 8C; parked drafts simply wait.

---

## References

- [ADR-0002](0002-euri-as-sole-llm-egress.md) — Euri AI Gateway as sole LLM egress
- [ADR-0003](0003-postgres-rls-as-tenant-isolation-default.md) — RLS for tenant isolation
- [ADR-0004](0004-langgraph-for-agent-orchestration.md) — LangGraph topology (and when NOT to use it)
- [ADR-0005](0005-celery-for-async-task-distribution.md) — Celery for async task distribution
- [ADR-0006](0006-expand-then-contract-migrations.md) — Expand-then-contract migrations
- [ADR-0007](0007-proposal-agent.md) — Proposal generation architecture (HITL-at-send precedent)
- [`apps/api/src/corpmind/modules/crm/automation.py`](../../apps/api/src/corpmind/modules/crm/automation.py) — FollowUpTask creation
- [`apps/api/src/corpmind/modules/crm/models.py`](../../apps/api/src/corpmind/modules/crm/models.py) — `FollowUpTask` schema
- [`apps/api/src/corpmind/modules/outreach/service.py`](../../apps/api/src/corpmind/modules/outreach/service.py) — `generate_message` (cold path) + `send_message` (reused)
- [`apps/api/src/corpmind/workers/tasks/outreach.py`](../../apps/api/src/corpmind/workers/tasks/outreach.py) — `advance_followup_cadence` stub + `_run_send`
- [`apps/api/src/corpmind/workers/tasks/inbox.py`](../../apps/api/src/corpmind/workers/tasks/inbox.py) — `sync_all_active_connections` fan-out pattern
- `.claude/rules/automation.md` — quiet hours, training-wheels, auto-execute eligibility
- `.claude/rules/compliance-guard.md` — frequency cap, opt-in, unsubscribe
- `.claude/rules/feature-flags.md` — rollout cadence
- [PRD §9.1](../../docs/PRD.md) — Agent roster and trigger matrix
