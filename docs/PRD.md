# CorporateMind AI

**Autonomous AI Corporate Outreach & Multi-Channel Growth OS**
**Multi-Agent AI Operating System for Trainers, Coaches, Consultants, Speakers & Workshop Providers**

PRODUCT REQUIREMENTS DOCUMENT — Version **3.0** | 2026
Status: Draft for Build
Prepared By: Shyam Sundar G — AI Generalist & Automation Engineer
*Confidential | CorporateMind AI | Internal Architecture & Product Specification*

---

## Table of Contents

1. Executive Summary
2. Problem Analysis
3. Market Opportunity
4. User Personas
5. Product Vision
6. Business Goals & KPIs
7. Scope Definition
8. Enterprise System Architecture
9. Agentic AI Architecture
10. Autonomous Workflow Design
11. Feature Breakdown (Functional Requirements)
12. User Journey Flows
13. API Specifications & Governance
14. Database Design
15. Vector Database Strategy
16. Infrastructure Architecture
17. Deployment Strategy
18. LLMOps Architecture
19. Monitoring & Observability
20. Security Architecture
21. AI Safety & Governance
22. Cost Estimation & Token Economics
23. Scaling Strategy & Infrastructure Evolution
24. Business Model
25. ROI Analysis
26. Competitive Differentiation
27. Pillar-Based Platform Architecture (7 Pillars)
28. Self-Healing Workflow Systems
29. Continuous Learning Pipelines
30. Future Roadmap
31. Risks & Assumptions
32. Open Questions
33. Enterprise Expansion Strategy
34. Final Strategic Positioning

**Appendix A** — AI Memory Architecture (Deep Spec)
**Appendix B** — AI Agent Runtime System (Deep Spec)
**Appendix C** — Event Catalog & Contracts
**Appendix D** — Multi-Tenancy Reference Model
**Appendix E** — Proposed `CLAUDE.MD` (engineering operating manual)
**Appendix F** — Step-by-Step Implementation Roadmap

---

## 1. Executive Summary

- **Product Name:** CorporateMind AI
- **One-Line Vision:** An autonomous multi-agent AI platform that converts an independent trainer, coach, consultant, or speaker — from a solo practitioner to a 50-person training agency — into a self-operating B2B growth machine that discovers HR buyers, generates personalized outreach, runs omnichannel campaigns, follows up, books meetings, drafts proposals, and grows communities with minimal human overhead.
- **Target Users:** NLP coaches, corporate trainers, leadership speakers, wellness coaches, HR trainers, business consultants, workshop providers, motivational speakers; agencies serving these professionals; and white-label resellers (LMS/coaching platforms).
- **High-Level Solution:** A cloud-native, multi-tenant SaaS leveraging a LangGraph multi-agent orchestrator routed through the **Euri AI Gateway** (Claude / GPT / Gemini / DeepSeek / Qwen / Llama / Mistral) on a **free-OSS-first runtime** (FastAPI, PostgreSQL, Redis, Qdrant, optional Ollama) deployable on Vercel + Railway. The platform unifies trainer-profile intelligence, HR discovery, outreach generation, omnichannel campaign distribution, proposal automation, CRM intelligence, and continuous campaign optimization under a single event-driven workflow plane.

### Expected Business Impact

| Outcome | Baseline (Today) | With CorporateMind AI | Delta |
|---|---|---|---|
| Time to find 100 matching HR contacts | 12–20 hours | < 30 minutes | −97% |
| Cold-outreach reply rate | 1.5–3% | 12–18% | +500% |
| Time from poster upload → live campaign | 5–7 days | < 60 minutes | −99% |
| Follow-up cadence completion rate | 22% (manual) | 96% (automated) | +336% |
| Corporate meetings booked / trainer / month | 1–3 | 8–14 | +400% |
| Trainer admin hours / week | 22 | 5 | −77% |
| Cost per qualified corporate lead | ₹420 | ₹95 | −77% |

**Revenue Target:** ₹2 Cr ARR within 18 months on a 3-tier subscription + usage-metered AI/credits model.

### 1.1 Product Vision

CorporateMind AI is **not** a CRM, **not** an email tool, **not** a social scheduler. It is the **autonomous AI Business Growth Operating System** that sits underneath all three, replacing the fragmented stack (Apollo + Lemlist + Buffer + Calendly + Notion + a VA + spreadsheets) with a single agentic substrate that observes signals (trainer expertise, HR seniority, campaign performance, channel responses, calendar gaps) and acts on them (segment refinement, outreach drafting, follow-up sequencing, meeting booking, proposal generation) without the trainer prompting it. The trainer stops being the SDR + marketer + ops lead; the system becomes the operator, and the trainer becomes the **approver and the deliverer**.

### 1.2 Product Name Rationale

**CorporateMind** fuses the two atomic units of B2B training economics — the **corporate** (the buyer) and the **mind** (the trainer's intellectual asset). The name signals that every trainer's mind is a revenue asset under continuous AI optimization, not a passive document. **AI** as suffix asserts the autonomous, multi-agent posture from first impression.

### 1.3 Key Differentiators

- **Multi-Agent Orchestrator vs. Single-Model Chatbots:** Specialized agents (RootOrchestrator, TrainerProfile, HRDiscovery, Outreach, Proposal, channel agents for WA/TG/IG/FB/LI/Email, CampaignOptimizer, Analytics, ComplianceGuard, LLMOpsGuardian) coordinate over a shared LangGraph state plane — competitors expose a chat box wrapped around GPT.
- **Content-In, Pipeline-Out:** Trainers upload posters / videos / PDFs / voice intros — AI extracts expertise, niche, tone, pricing, and corporate fit. No 30-field onboarding form.
- **Free-OSS-First Runtime:** Entire MVP runs on free tiers (Vercel + Railway + Qdrant Cloud free + Cloudinary + optional Ollama fallback). Gross margin positive from tenant #1.
- **Provider-Abstracted Inference via Euri Gateway:** Zero vendor lock-in; routing matrix selects the cheapest capable model per task with circuit-breaker fallbacks.
- **Compliance-Native:** Every outbound message passes through ComplianceGuardAgent (opt-in, rate limit, WhatsApp 24h window, dedup, frequency cap, LinkedIn ToS guard) **before** dispatch. No competitor ships this gate as a first-class agent.
- **Tenant-Isolated AI Budgets:** Hard token ceilings, per-feature rate limits, and per-tenant cost telemetry — a control plane competitors lack.
- **HITL by Design:** Sends > 200 recipients, enterprise outreach, and first-week-of-tenant actions are gated. Trainers stay in control without staying in the loop.

---

## 2. Problem Analysis

### 2.1 The Trainer Revenue Leakage Anatomy

Coaches and corporate trainers are skilled at delivery and weak at distribution. ~70% of independent trainers earn under ₹15L/year despite content quality that justifies 3–5×. Revenue is lost at the seam between five disconnected workflows:

| Workflow | Today's State | Revenue Leak |
|---|---|---|
| HR Discovery | LinkedIn manual scrolling, scraped CSVs | 12–20 hrs/week wasted; stale data |
| Outreach Writing | Templated copy-paste | < 3% reply rate; treated as spam |
| Follow-up | Manual reminders, forgotten | 78% of leads never get touch #2 |
| Channel Mix | Email only; or random IG posts | No omnichannel; weak brand |
| Proposal Generation | Manual PPT, takes 3–5 hours | Slow turnaround = lost deals |

The trainer is the **only integration layer** between these. When the trainer is delivering a workshop, the funnel is paused. CorporateMind AI is the software replacement for the trainer-as-glue.

### 2.2 Why Current Systems Fail

- **Apollo / Lemlist:** Strong outreach + database but no domain awareness of "training services"; treats every contact as a generic prospect; no follow-up intelligence beyond cadence.
- **HubSpot:** A CRM, not an SDR. Requires a human to drive every action.
- **Zoho/Bigin:** Indian-priced but feature-poor; no AI personalization.
- **Buffer / Hootsuite:** Generic schedulers; no awareness of trainer's expertise or workshop calendar.
- **Generic ChatGPT use:** Stateless, no memory of prior conversations with the same HR, no tool access, no compliance gate.
- **Indian-market trainer tools (Tagmango, Exly):** Built for D2C course selling, not B2B corporate acquisition.

### 2.3 Why Now

1. **High-reasoning frontier LLMs** (Claude Sonnet 4.6, GPT-5.x, Gemini 3.x) make personalized outreach economically viable at ~₹2–₹8 per fully-customized HR message.
2. **Open-source agentic frameworks** (LangGraph, DSPy) collapse the engineering cost of a 12-agent orchestrator from a 10-engineer year to a 1-engineer quarter.
3. **Post-pandemic L&D budget reset** has created a generation of HR/L&D heads actively shopping for niche specialist trainers — but they do not know who to call.
4. **WhatsApp Business Cloud API maturity** in India unlocks compliant, scalable B2B messaging that did not exist 18 months ago.

---

## 3. Market Opportunity

### 3.1 TAM / SAM / SOM

| Layer | Definition | 2026 Value | 2030 Projection | CAGR |
|---|---|---|---|---|
| TAM | Global B2B sales-engagement + creator-monetization SaaS | $48 B | $112 B | 23.6% |
| SAM | English/Hindi/regional-Asia outreach + creator SaaS for solo experts / agencies | $7.1 B | $19 B | 27.9% |
| SOM (5-yr) | India + SEA independent trainers/coaches/consultants and 2–50-person training agencies | $520 M | $1.9 B | 29.7% |

India alone has an estimated **~3.2 lakh active trainers, coaches, and corporate consultants** with monthly software budgets > ₹2,000 — a **₹760 Cr** addressable monthly opportunity at the entry tier.

### 3.2 Segment Growth Drivers

| Segment | 2026 Value | 2030 Projection | CAGR |
|---|---|---|---|
| AI Sales Development (AI SDR) | $2.4 B | $11.2 B | 47% |
| Outbound Email Automation | $2.1 B | $5.8 B | 28% |
| WhatsApp Business Automation | $0.9 B | $5.2 B | 55% |
| Creator/Coach SaaS | $1.6 B | $6.4 B | 41% |
| AI Proposal Generation | $0.3 B | $2.1 B | 62% |

The **convergence layer** — a single platform that does all five for the trainer/coach segment — has **no category leader**. CorporateMind AI is positioned to define it.

---

## 4. User Personas

### 4.1 Primary Personas

**1. Priya (Solo NLP Coach, Bengaluru, 6 yrs experience)**
- **Pain:** "I have 14 years of NLP content and I'm still cold-DMing HRs on LinkedIn. I do not know who to email or what to say."
- **Goal:** 2 corporate workshops per month, ₹2L revenue/month, without becoming her own SDR.
- **Channel:** Mobile-first; will not read docs; expects WhatsApp-style UX.

**2. Rajiv (Corporate Trainer, Mumbai, 12 yrs, leadership niche)**
- **Pain:** Spends Saturdays writing proposals from scratch in PPT. Loses 40% of leads to slow turnaround.
- **Goal:** Same-day proposals; pipeline of 30+ active HR conversations; predictable monthly revenue.
- **Channel:** Desktop + email power user; values customization.

**3. Aanya (Founder, 8-trainer agency, Delhi)**
- **Pain:** Each trainer markets themselves differently; no central CRM; agency identity is diluted.
- **Goal:** White-label workspace per trainer with shared HR database, central campaigns, brand guardrails.
- **Channel:** Desktop dashboard daily; needs export + admin views.

**4. Karthik (Leadership Speaker + Author, multi-city)**
- **Pain:** Speaking bookings come through agents who take 30%. Wants direct corporate channel.
- **Goal:** Replace agent dependency; book 4–6 paid speaking gigs/month directly.
- **Channel:** Power user, LinkedIn-heavy; expects polished outputs.

### 4.2 Secondary Personas

- **The HR Buyer (Meera):** Receives outreach; expects relevance; rebooks if remembered next quarter.
- **The Agency Operator (Vikram):** Manages multiple trainer accounts; needs RBAC + reporting.
- **The White-Label Reseller (Edutech SaaS):** Bundles CorporateMind into their LMS for partner trainers.

---

## 5. Product Vision

CorporateMind AI executes a three-horizon vision:

- **Horizon 1 (0–12 months) — The Autonomous Outreach Cockpit.** Replace the trainer's manual SDR + marketer + ops workload. Every HR discovery, message, follow-up, proposal, and campaign is generated, scheduled, executed, and measured by agents. Human role: **approve, edit, deliver**.
- **Horizon 2 (12–30 months) — The Trainer Intelligence Network.** Cross-tenant anonymized signal sharing (which HR titles respond to which message tones; which industries are hiring trainers this quarter) becomes a proprietary data moat. Each trainer benefits from every other trainer on the network.
- **Horizon 3 (30+ months) — The Expert-Services Platform OS.** Open the agent runtime to third-party developers (event organizers, training marketplaces, executive search firms) via a plugin and tool-registration SDK. CorporateMind becomes the agentic substrate that other coaching/training SaaS builds on top of.

---

## 6. Business Goals & KPIs

### 6.1 Business Goals

- **2,000** paying tenants by Month 18.
- 30% MoM growth Months 3–9; 16% MoM Months 10–18.
- **₹2 Cr ARR** by Month 18; **70%** gross margin at scale.
- Net Dollar Retention ≥ **115%**.

### 6.2 Product KPIs

| KPI | Target | Why It Matters |
|---|---|---|
| Time to first value (TTFV) | < 60 min | Upload → first campaign draft same session |
| Workflow success rate | ≥ 96% | Failed agent run = churn risk |
| Activation rate | ≥ 60% | % of signups that approve their first campaign |
| 90-day retention | ≥ 82% | Indian SaaS benchmark is 65–70% |
| Reply rate on outreach | ≥ 12% | 4× the industry baseline (~3%) |
| NPS | ≥ 55 | Trainers rarely give > 50 unless genuinely impressed |

### 6.3 AI-Specific Metrics

| Metric | Target |
|---|---|
| End-to-end agent run p95 latency | < 15 s (text), < 4 s for inline assistants |
| Hallucination rate (validated against tools/DB) | < 1.5% |
| Structured-output schema-validity rate | ≥ 99.4% |
| Self-heal success rate on first retry | ≥ 88% |
| Token COGS per active tenant per month | < ₹180 |
| Semantic cache hit rate | ≥ 38% |
| Drift-detection MTTD | < 24h after model update |
| HITL override rate | < 8% of agent-proposed actions |
| ComplianceGuard block rate (false positives) | < 0.5% |

---

## 7. Scope Definition

### 7.1 In Scope (Phase 1, Months 0–9)

- **12 specialized agents** (full roster in §9)
- **Multi-tenancy:** org → workspace → trainer hierarchy
- **Modules:** trainer intelligence, HR discovery, outreach AI, social automation, WhatsApp engine, proposals, CRM, campaigns, analytics, billing, compliance
- **Channel integrations:** Email (Resend/Postmark/SES), WhatsApp Business Cloud API, Telegram Bot, Instagram Graph (publish + insights), Facebook Graph, LinkedIn (public company data + post publishing only — **no personal DM automation**)
- **Ingestion adapters:** Cloudinary upload + OCR (poster/PDF), audio/video transcription (Whisper self-host or Deepgram free)
- **Self-serve onboarding**, Stripe + Razorpay billing
- **Trainer/Owner dashboard, Agency admin dashboard, Campaign builder, Proposal studio**
- **LLMOps stack:** Langfuse, Promptfoo, DSPy optimization loop

### 7.2 Out of Scope (Phase 1)

- Inbound voice IVR / outbound voice calls (Phase 2 — reuses pattern from sister product RevenueTable AI)
- Personal LinkedIn DM automation (ToS-risk; permanently out)
- Cold-call dialers
- Course/LMS hosting (we integrate with Tagmango/Exly read-only)
- Payment-collection for trainers (we integrate; we don't disburse)
- Native mobile apps (PWA only)
- On-prem deployment (Enterprise tier only, Phase 3+)

---

## 8. Enterprise System Architecture

### 8.1 High-Level Architecture Plane View

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       PRESENTATION PLANE                                │
│  Next.js 14 PWA  │  Trainer Mobile View  │  Agency Admin  │  Reviewer  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ (HTTPS + WSS + SSE)
┌──────────────────────────────▼──────────────────────────────────────────┐
│                       EDGE / API GATEWAY                                │
│  FastAPI (async)  │  AuthN/Z  │  Rate Limit  │  TenantContext  │  OpenAPI │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
   ┌──────────────────────────┼──────────────────────────┐
   │                          │                          │
┌──▼────────────┐    ┌────────▼──────────┐    ┌──────────▼─────────┐
│ SERVICE PLANE │    │  AGENT RUNTIME    │    │   EVENT BUS        │
│ trainer_intel │    │  LangGraph        │    │   Redis Streams    │
│ hr_discovery  │    │  Orchestrator     │    │   Pub/Sub          │
│ outreach      │    │  + 12 Agents      │    │   DLQ              │
│ social        │    │  + Tool Registry  │    │   Replay Log       │
│ whatsapp      │    │  + Memory Manager │    │                    │
│ proposals     │    │  + Guardrails     │    │                    │
│ crm           │    │  + ComplianceGate │    │                    │
│ analytics     │    └────────┬──────────┘    └──────────┬─────────┘
│ compliance    │             │                          │
└──┬────────────┘             │                          │
   │                          │                          │
┌──▼──────────────────────────▼──────────────────────────▼───────────────┐
│                           DATA PLANE                                   │
│  PostgreSQL (RLS + schema-per-org tier) │ Redis │ Qdrant │ Meilisearch │
│  Cloudinary / S3 (objects)              │  Event Store (Postgres)     │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│             INFERENCE PLANE (via Euri AI Gateway + LiteLLM)             │
│  Claude │ GPT │ Gemini │ DeepSeek │ Qwen │ Mistral │ Llama │ Ollama     │
│  Whisper (self-host) │ bge-small embeddings │ bge-reranker              │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                      OBSERVABILITY PLANE                                │
│  Langfuse (LLM traces) │ OpenTelemetry │ Prometheus │ Grafana │ Sentry │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Multi-Tenancy Model

**Hierarchy:** `Organization (Agency or Solo) → Workspace (brand/trainer) → User (trainer/admin/reviewer)`.

| Layer | Isolation Strategy | Rationale |
|---|---|---|
| Database | Postgres RLS on every base table by `tenant_id` (default); schema-per-org for tenants > 250 trainers (Enterprise) | Balances cost (RLS cheap) with strong isolation for premium tier |
| Cache | Redis key prefix `t:{org_id}:{workspace_id}:...` with per-tenant memory budget | Prevents noisy-neighbor cache eviction |
| Vector | Qdrant collection per org for HR contacts + trainer profiles; shared global collection for prompt cache (PII-stripped) | Tenant data never co-mingled in vector space |
| Object | Cloudinary path `tenants/{org_id}/workspaces/{ws_id}/...` with per-tenant signed URLs | Per-tenant lifecycle + retention |
| Workflow | Celery task routing via `tenant_id` header; per-tenant queue concurrency cap | One tenant's runaway loop cannot drown shared workers |
| Inference | LiteLLM virtual key per tenant; per-tenant monthly token ceiling; per-feature rate limit | Hard cost containment; abuse isolation |
| Observability | Langfuse projects scoped by org; Grafana dashboards filtered by `tenant_label` | Tenant-specific debuggability without leakage |

**Entitlements & Feature Flags** are resolved at the API gateway via a `TenantContext` middleware. Every downstream service receives a frozen `TenantContext(org_id, workspace_id, plan, ai_budget_remaining, feature_flags, rate_limits)` injected into the request scope. No service queries entitlement state independently — single source of truth at the edge.

### 8.3 RBAC Inheritance Model

Permissions cascade `Org > Workspace > User` with explicit *deny-overrides-grant* semantics. Built-in roles: `OrgAdmin`, `AgencyManager`, `Trainer`, `Reviewer`, `Analyst (read-only)`. Custom roles supported on Enterprise tier via JSON policy documents (Casbin-style).

---

## 9. Agentic AI Architecture

### 9.1 Agent Roster

| Agent | Primary Role | Tools | Memory Class | Model Tier |
|---|---|---|---|---|
| **RootOrchestrator** | Decomposes intent, manages global state, HITL escalator | All downstream agents | Working + Episodic | Mid (Claude Sonnet / GPT-4.1) |
| **TrainerProfileAgent** | Extracts niche, topics, tone, pricing, corporate fit from uploads | OCR, Whisper, Vision, Qdrant write | Long-term Semantic | Mid + Vision |
| **HRDiscoveryAgent** | Finds matching companies + HR contacts from opt-in sources | Web search, Tavily, public registries, Qdrant | Long-term Semantic | Mid (Claude/GPT for reasoning) + Small (extraction) |
| **OutreachAgent** | Drafts per-recipient messages with A/B variants | Trainer profile, HR record, Qdrant retrieval | Working + Episodic | Mid (Claude for copy) |
| **ProposalAgent** | Generates pitch decks, agendas, pricing documents | Trainer profile, templates, PDF render | Long-term Semantic | Mid (Claude) |
| **WhatsAppAgent** | Template management, 24h window, follow-ups | WA Business Cloud API | Short-term Conversational | Small + rule-based |
| **TelegramAgent** | Channel broadcasts, community nurture | Telegram Bot API | Short-term | Small |
| **InstagramAgent** | Reel captions, story automation, hashtag intelligence | IG Graph API, image gen | Episodic | Mid (creative) |
| **FacebookAgent** | Page publishing, event promotion, messenger | FB Graph API | Episodic | Mid |
| **LinkedInAgent** | Public company-page posts, public-data lookups (no DMs) | LI public APIs | Episodic | Mid |
| **CampaignOptimizer** | Post-hoc analysis: which segment × channel × tone wins | Analytics DB, Langfuse | Stateless | Small + analytical |
| **AnalyticsAgent** | Daily rollups, insight cards, anomaly detection | Postgres analytics, time-series | Stateless | Small |
| **ComplianceGuardAgent** | Gate every outbound message: opt-in, rate, dedup, content | Opt-in DB, rate buckets, classifier | Stateless | Small + rules |
| **LLMOpsGuardian** | Monitors quality, triggers retries, escalates to HITL | Promptfoo evals, Langfuse, schema validator | Stateless | Small + rule-based |

### 9.2 Reasoning Loop (Per Agent)

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ PERCEIVE │ ──▶│   PLAN   │ ──▶│ EXECUTE  │ ──▶│  VERIFY  │
└──────────┘    └──────────┘    └─────┬────┘    └─────┬────┘
     ▲                                │                │
     │           ┌────────────────────┘                │
     │           ▼                                     │
     │      ┌──────────┐    fail                       │
     └──────│  LEARN   │ ◀──────────  retry ◀──────────┤
            └──────────┘                               │
                 ▲                                     │
                 └────────── success ──────────────────┘
```

- **PERCEIVE:** Hydrate `TenantContext`, load short + semantic memory, normalize input.
- **PLAN:** Generate a structured `PlannerOutput` (Pydantic). LLM forced through `response_format=json_schema`.
- **EXECUTE:** Sandboxed tool executor with per-tool timeout, per-step token budget, idempotency keys.
- **VERIFY:** Schema validation → semantic validators (e.g. "does the HR contact actually exist and is opted-in?") → optional LLM-as-judge.
- **LEARN:** Trace + outcome shipped to Langfuse; periodic batch jobs feed DSPy/Promptfoo eval pipelines.

### 9.3 Memory Architecture (Summary — full spec in Appendix A)

| Memory Class | Backing Store | TTL | Scope | Purpose |
|---|---|---|---|---|
| Working | In-process dict | Workflow lifetime | Per-run | Plan state, intermediate outputs |
| Short-term Conversational | Redis `conv:{session_id}` | 30 min sliding | Per-session | Chat assistant turns |
| Episodic | Postgres `agent_runs` + `agent_events` | 90 days hot, archive cold | Per-tenant | "Last time we contacted this HR, here's what worked" |
| Semantic | Qdrant per-tenant collections | Indefinite, with pruning | Per-tenant | Trainer expertise vectors, HR/company vectors, campaign vectors |
| Procedural (skills) | `prompt_templates` table | Indefinite | Global + tenant overrides | "How to draft a wellness-coach outreach to a 5000+ employee tech firm" |

### 9.4 Guardrails

- **Input guardrails:** PII redaction (Presidio rules + regex), prompt-injection classifier (LLM-Guard), tenant-scope enforcement on tool calls.
- **Output guardrails:** JSON-schema validation, fact-grounding (output must cite tool/DB IDs when claiming a fact), regex denylists, profanity + competitor-name moderation.
- **Action guardrails:** Any agent action affecting > 200 recipients auto-routes to HITL. Any campaign cost > tenant threshold triggers approval webhook. First-week-of-tenant: everything HITL by default (**training-wheels mode**).

---

## 10. Autonomous Workflow Design

### 10.1 LangGraph State Machine

Every workflow is a directed graph with:
- Typed `WorkflowState` (Pydantic) as the single source of truth between nodes.
- Nodes are pure functions `(state) -> partial_state_update`.
- Edges are conditional functions returning the next node name or `END`.
- Every transition is checkpointed to Postgres (`workflow_checkpoints`) keyed by `(workflow_id, node_id, version)`.

### 10.2 Workflow Persistence & Resumption

A workflow can be paused at any node, persisted, and resumed hours later — critical for HITL gates ("trainer must approve this campaign before send"):

```
Event → Wakeup Handler → Load Checkpoint → Validate State Schema Version
       → Resume LangGraph from last node → Continue
```

If the state schema evolved (rare), a migration function registered per `(from_version, to_version)` pair runs on hydration. Workflows older than 30 days depending on a removed node are quarantined and surfaced for manual closure.

### 10.3 Retry, Backoff & Circuit Breakers

| Failure Class | Strategy |
|---|---|
| Transient (network, 5xx from Euri) | Exponential backoff: 1s, 3s, 9s; max 3 attempts |
| Rate-limit (429) | Token-bucket-aware retry with jitter; fall back to next model in routing matrix |
| Schema-invalid output | Self-repair: re-prompt with parsing error appended; max 2 retries; then escalate |
| Tool execution failure | Idempotency-key replay; if same failure twice, mark node failed and route to recovery |
| LLM hallucination (grounding fails) | Re-run with stricter system prompt + temperature 0; if still fails, HITL |
| Tenant budget exceeded | Fail fast, raise `BudgetExceeded`, notify org admin, do not retry |
| Channel provider failure (WA template rejected, IG API down) | Mark recipient `failed_transient`; reschedule with backoff; circuit-break after threshold |

Circuit breakers wrap every external dependency (Euri, WhatsApp, Resend, Telegram, IG, FB, LinkedIn, Cloudinary). Half-open after 60s; metric `circuit_state{dep}` exposed to Prometheus.

### 10.4 Dead-Letter Queue & Replay

Failed workflows land in `dlq_workflows` with full state, error fingerprint, trace ID. Daily reaper groups failures by fingerprint and surfaces top-10 patterns to LLMOpsGuardian. Replays triggered manually via admin API or programmatically once a fix ships.

---

## 11. Feature Breakdown (Functional Requirements)

### Feature 1 — Trainer Intelligence (AI Profile Extraction)

**User Story:** As a trainer, I upload my posters/videos/PDFs/voice intro and the platform builds a complete profile of my expertise without me filling a form.

**Acceptance Criteria:**
- Accepts: PDF, JPG/PNG, MP4, MOV, MP3, WAV, public URL
- Extracts: niche, workshop topics (multi-tag), industries served, experience years, communication tone, pricing hints, CTA, target seniority, language
- Produces: trainer profile vector (Qdrant) for semantic matching
- User can review + edit every extracted field before lock-in

**Edge Cases & Constraints:**
- **Vision pipeline:** Posters in Hindi/regional scripts handled via multilingual OCR.
- **Audio in Hinglish/code-switch:** handled natively, no translation hop.
- **Conflicting signals across uploads:** the latest upload wins; user prompted to resolve.
- **Sensitive content:** if upload contains PII other than the trainer's own, surfaced for redaction approval.

### Feature 2 — HR Discovery Engine

**User Story:** As a trainer, I want the system to find HR managers, L&D heads, and wellness leads at companies that match my expertise — without me building a list.

**Acceptance Criteria:**
- Discovers HR contacts from **opt-in / public sources only**: public company directories, company career pages, webinar registrations the trainer brings, public LinkedIn company pages (company-level data only, no scraping private profiles)
- Match score (0–1) per (trainer × company) using semantic similarity + rules
- Default ≥ 50 matched contacts within 30 minutes of profile lock
- Industry, size, region, role-level filters
- Dedup across the org

**Edge Cases & Constraints:**
- **Sources allowlist:** ComplianceGuard maintains an explicit allowed-sources registry; any scraper attempting an unlisted domain is rejected.
- **Opt-in proof:** Every contact stores `source`, `source_type`, `opted_in_at`, `opt_in_evidence` (URL, screenshot ref, consent timestamp).
- **Stale data:** Contacts older than 6 months are flagged and de-prioritized in segments.
- **PII:** Phone is hashed in analytics tables (HMAC with per-org salt); email stored as-is for delivery, redacted in logs.

### Feature 3 — AI Outreach Generator

**User Story:** As a trainer, I want every email, WhatsApp, and LinkedIn-post outreach to feel personally written for that specific HR person.

**Acceptance Criteria:**
- Per-recipient personalization referencing: their company industry, recent public news (opt-in source), trainer's matching expertise
- Channel-aware copy: Email (subject + preheader + body), WhatsApp (≤ 350 chars, emoji-aware), LinkedIn post (≤ 1200 chars), Telegram (multi-paragraph allowed)
- 2 variants per recipient for A/B
- Tone variants: formal / consultative / friendly
- Optimal send-time prediction per segment per channel
- Suppression list automatically enforced

**Edge Cases & Constraints:**
- **WhatsApp template compliance:** Marketing templates pre-cleared with Meta; template versioning + approval status tracked; non-approved templates blocked at send time.
- **Rate limits:** WA Business API tier-aware throttler; never exceed tier.
- **Cooldown:** No HR contact receives > 2 marketing messages in 7 days across all channels (cross-channel cap).
- **Hallucination check:** Any claim about the trainer's credentials must resolve to the trainer's locked profile — otherwise blocked.
- **HITL gate:** Sends > 200 recipients require trainer approval; sends > 1,000 require OrgAdmin.

### Feature 4 — Omnichannel Social Automation

**User Story:** As a trainer, I want my content distributed across my channels with the right copy for each platform — without me logging in to five apps.

**Channels & Capabilities:**

| Channel | Capabilities |
|---|---|
| Email | Personalized campaigns, sequence cadence, reply-detection |
| WhatsApp | Group outreach, broadcast lists, template send, follow-up flows |
| Telegram | Channel broadcast, community nurture, webinar drip |
| Instagram | Reel captions, story automation, carousel generation, hashtag intelligence, post scheduling |
| Facebook | Page publishing, event promotion, Messenger workflows |
| LinkedIn | **Public company-page posts only** (no personal DM automation) |

### Feature 5 — WhatsApp Automation Engine

**Capabilities:** Official WA Business Cloud API integration, AI outreach, HR follow-ups, webinar campaigns, group invite distribution, smart segmentation, campaign optimization.

**IMPORTANT COMPLIANCE:**
- ✅ Official WA Business Cloud API only
- ✅ Opt-in tracking per (tenant, contact)
- ✅ Rate limiting per WA tier
- ✅ Anti-spam (frequency cap, cooldown)
- ✅ Unsubscribe management (global per tenant)
- ✅ 24-hour customer-care window enforcement (templates required outside)

**Workflow:**
```
Workshop Upload → AI Generates Campaign → AI Finds Matching HRs
   → Campaign Approval → Rate-Limited Distribution → AI Follow-ups
```

### Feature 6 — Telegram Automation

Bot integration, auto-posting, webinar broadcasts, AI engagement campaigns, community nurturing, inline keyboards for replies.

### Feature 7 — Instagram & Facebook Automation

Instagram: AI reel captions, story automation, hashtag intelligence, carousel generation, post scheduling.
Facebook: Page publishing, campaign automation, event promotion, Messenger flows.

### Feature 8 — AI Proposal Generator

**User Story:** As a trainer, after a positive HR reply, I want a customized pitch deck + agenda + pricing in under 2 minutes.

**Acceptance Criteria:**
- Input: HR conversation context + trainer profile + workshop selection
- Output: PDF (via WeasyPrint), Google Doc, Notion (optional)
- Sections: cover, problem framing, solution, agenda, deliverables, pricing, case studies, next steps
- Trainer can edit any section in-app before send

### Feature 9 — CRM & Lead Intelligence

Tracks: leads, meetings, replies, open rates, click rates, conversion, industry analytics, AI campaign performance. Pipeline board (Kanban): `discovered → contacted → engaged → replied → meeting_scheduled → proposal_sent → booked | lost`.

### Feature 10 — Multi-Agent AI System

(Spec covered in §9, §10, §27, Appendix B.)

### Feature 11 — LLMOps & AI Observability

(Spec covered in §18, §19, §28, §29.)

---

## 12. User Journey Flows

### 12.1 Trainer Onboarding (Day 0 → Day 1)

```
Signup → Email/Phone OTP → Org creation → Workspace wizard (name, niche, language)
  → Upload assets (poster/video/PDF/voice) → AI extracts profile (<5 min)
  → Trainer reviews + edits profile → Connect channels (WA, Email, IG)
  → AI proposes first 50 HR matches (<30 min) → Trainer approves segment
  → First campaign drafts shown → Trainer approves → First sends within Hour 1
```

### 12.2 Autonomous Campaign Loop

```
Cron (08:00 daily) → AnalyticsAgent computes momentum → CampaignOptimizer proposes
3 next-action campaigns (re-engage Lapsed, nurture Engaged, expand to new industry)
→ ComplianceGuard validates → Trainer inbox card ("Approve / Edit / Reject")
→ On approve → Send pipeline (batched, throttled, cross-channel cap respected,
attribution links injected) → Outcome events streamed back → 72h post-send
attribution report → Outcome ingested into RLHF feedback store
```

### 12.3 HR Reply → Proposal → Meeting Flow

```
Inbound reply (Email / WA / Telegram) → Reply classifier (positive / neutral / negative
/ unsubscribe) → If positive → Conversation thread surfaced to trainer → Trainer triggers
"Generate proposal" → ProposalAgent drafts (<2 min) → Trainer edits + sends →
Calendly link auto-embedded → Booking webhook → meeting created → reminder sent →
post-meeting summary requested
```

### 12.4 Compliance Gate Flow

```
Any outbound message → ComplianceGuardAgent:
  - check opt-in for (contact, channel)
  - check unsubscribe list
  - check frequency cap (≤ 2 msgs / 7 days / cross-channel)
  - check WA 24h window if WA template
  - check content policy classifier
  - check tenant budget
→ Pass: queue for send | Block: log reason + notify trainer | HITL: route to approval
```

---

## 13. API Specifications & Governance

### 13.1 API Surface

- **Public REST API** (`/api/v1/*`): tenant-scoped, OAuth2 + JWT, OpenAPI 3.1 documented.
- **Internal gRPC** (Phase 2): agent-to-service for hot paths.
- **WebSocket** (`/ws/v1/agent-stream`): live LangGraph events to dashboard.
- **SSE** (`/sse/v1/insights`): one-way push for insight cards.
- **Webhooks (outbound):** tenant-registered endpoints receive `lead.*`, `campaign.*`, `proposal.*`, `meeting.*` events.
- **Webhooks (inbound):** WhatsApp, Telegram, IG, FB, Calendly, Stripe/Razorpay — all HMAC-verified.

### 13.2 Versioning & Lifecycle

URI versioning (`/api/v1`, `/api/v2`). **Never break a v.** Additive changes only within a major. Deprecation: 6-month sunset window with `Deprecation` + `Sunset` headers. Breaking changes ship behind `?api_preview=v2` opt-in for 90 days minimum.

### 13.3 Contracts & Schema Evolution

- All request/response bodies are Pydantic models → OpenAPI exported on every CI build.
- Schema-diff job in CI compares against previous spec; non-additive change requires PR label `api:breaking` and architect approval.
- SDK generation (TypeScript + Python) on every merge to `main`.

### 13.4 Idempotency & Pagination

- Every mutating endpoint accepts `Idempotency-Key` header; server stores result 24h.
- Pagination: cursor-based only (`cursor`, `limit`, default 50, max 200). Offset pagination forbidden by lint rule.

### 13.5 Webhook Standards

HMAC-SHA256 signed with `X-CM-Signature` header. Retries: 1m, 5m, 15m, 1h, 6h, 24h (jittered). Permanent failure after 6 attempts → DLQ + admin notification. At-least-once delivery; consumers must be idempotent on `event_id`.

### 13.6 Rate Limits (Default Tier)

| Endpoint Class | Starter | Growth | Enterprise |
|---|---|---|---|
| Read | 60 rpm | 300 rpm | Custom |
| Mutating | 30 rpm | 150 rpm | Custom |
| Agent-trigger | 10/hour | 100/hour | Custom |
| Outreach sends/day | 500 | 5,000 | Custom |

Enforced via Redis token bucket keyed on `(tenant_id, endpoint_class)`.

---

## 14. Database Design

### 14.1 Core Schema (PostgreSQL 16)

| Table | Purpose | Key Columns |
|---|---|---|
| `orgs` | Top-level tenant | id, name, plan, region |
| `workspaces` | Brand/trainer within org | id, org_id, brand_name, niche, voice_profile_id |
| `users` | Operators | id, org_id, email, role, mfa_enabled |
| `trainers` | Trainer profile | id, workspace_id, name, niche_tags, tone, pricing_range, experience_yrs |
| `uploads` | Posters/videos/PDFs | id, trainer_id, kind, status, cloudinary_url, ocr_text, transcript |
| `companies` | Discovered corporates | id, name, industry, size_band, region, source |
| `hr_contacts` | HR people | id, org_id, company_id, name, title, email_hash, phone_hash, opt_in_status, source |
| `lead_lists` | Saved segments | id, workspace_id, name, query_json |
| `campaigns` | Campaign lifecycle | id, workspace_id, channel(s), status, audience_query, schedule_at, approval_state |
| `campaign_recipients` | Per-recipient state | id, campaign_id, hr_contact_id, status, sent_at, replied_at |
| `outreach_messages` | All sent messages | id, channel, body, variant, sent_at, delivery/open/reply status |
| `conversations` | Threaded replies | id, hr_contact_id, channel, last_msg_at |
| `proposals` | Pitch decks | id, conversation_id, status, version, pdf_url |
| `meetings` | Calendar events | id, conversation_id, provider, scheduled_at, summary |
| `whatsapp_messages`, `telegram_posts`, `instagram_posts`, `facebook_posts`, `linkedin_posts` | Per-channel logs | ... |
| `agent_runs` | Workflow executions | id, tenant_id, agent_name, status, tokens, cost_cents |
| `agent_events` | Per-node events | id, run_id, node, payload_json, trace_id |
| `workflow_checkpoints` | Resumable state | workflow_id, node, state_json, schema_version |
| `events` | Domain event log | id, tenant_id, type, payload_json, occurred_at, source, version |
| `dlq_workflows` | Failed workflows | id, run_id, error_fingerprint, state_json |
| `prompt_templates` | Versioned prompts | id, name, version, body, eval_score, active_in_envs |
| `opt_ins`, `unsubscribes` | Compliance | id, tenant_id, contact_id, channel, evidence |
| `audit_events` | Append-only audit | id, tenant_id, actor, action, target, occurred_at |
| `billing_plans`, `subscriptions`, `usage_counters`, `invoices` | Monetization | ... |

### 14.2 Indexing & Partitioning

- `outreach_messages`: native partitioning by `RANGE (sent_at)` monthly; auto-detach > 18 months to cold S3 Parquet.
- `agent_events`: hot-cold split — last 14 days in Postgres, older shipped to R2/S3 Parquet, queryable via DuckDB.
- `events`: append-only; weekly compaction.
- Composite `(tenant_id, created_at DESC)` on every event-style table.
- GIN on JSONB metadata.

### 14.3 Multi-Tenant Isolation

- Small/mid tenants: RLS policies `USING (tenant_id = current_setting('app.tenant_id')::uuid)`. Tenant ID set per connection via `SET LOCAL app.tenant_id = ...`.
- Enterprise tier: dedicated `schema-per-org` with logical replication for analytics.

---

## 15. Vector Database Strategy

### 15.1 Qdrant Collections

| Collection | Vectors | Payload | Tenancy |
|---|---|---|---|
| `trainer_profiles_{org_id}` | 768-d bge-small | trainer_id, niche_tags | Per-org |
| `companies_{org_id}` | 768-d | company_id, industry, size | Per-org |
| `hr_contacts_{org_id}` | 768-d | contact_id, title, seniority | Per-org |
| `campaign_outcomes_{org_id}` | 768-d | campaign_id, segment, channel, outcome | Per-org |
| `prompt_cache_global` | 1024-d | prompt_hash, response_ref, hit_count, ttl | Cross-tenant (semantic cache only — **no PII**) |
| `proposal_templates_{org_id}` | 768-d | template_id, vertical | Per-org |

### 15.2 Retrieval Pipeline

```
Query → Embed (bge-small via local sentence-transformers) → Hybrid Search
(Qdrant ANN top-50 + Meilisearch BM25 top-50) → RRF Fusion → Cross-encoder
Rerank (bge-reranker-base) → Top-k (default 8) → Inject into prompt with
provenance IDs
```

### 15.3 Memory Pruning

- Trainer profile vectors: re-embed on every profile lock + quarterly refresh.
- HR contact vectors: 12-month rolling window; stale flag at 6 months.
- Campaign outcome vectors: retain indefinitely; this is the RLHF moat.
- Prompt cache: LFU eviction with 30-day TTL hard ceiling.

---

## 16. Infrastructure Architecture

### 16.1 Topology (MVP — Stage 1)

```
[ Vercel Edge ] ─────► Next.js 14 PWA
       │
       ▼
[ Railway: api-gateway ] ─── FastAPI (uvicorn workers × 4)
       │
       ├──► [ Railway: worker-agents     (Celery, queue=agents) ]
       ├──► [ Railway: worker-outreach   (Celery, queue=outreach) ]
       ├──► [ Railway: worker-social     (Celery, queue=social) ]
       ├──► [ Railway: worker-ingestion  (Celery, queue=ingestion) ]
       ├──► [ Railway: worker-scrapers   (Celery, queue=scrape, low-prio) ]
       │
       ├──► [ Railway PostgreSQL 16 ]
       ├──► [ Railway Redis (cache + queue + pubsub) ]
       │
       ├──► [ Qdrant Cloud Free tier ]
       ├──► [ Meilisearch on Railway ]
       │
       ├──► [ Cloudinary / S3 ]
       │
       └──► [ Euri AI Gateway ] ── [ Claude, GPT, Gemini, DeepSeek, ... ]
                                          │
                                          └─ fallback ──► [ Ollama on Hetzner ARM ]
```

### 16.2 Real-Time

- **Redis Pub/Sub** for fan-out (agent streaming tokens to dashboard).
- **WebSocket** server colocated with FastAPI (Redis subscriber bridge).
- **SSE** for one-way insight cards.
- **No Kafka** in Stage 1. Trigger for adoption: > 10k events/sec sustained.

### 16.3 Storage Tiers

| Tier | Store | Use |
|---|---|---|
| Hot OLTP | Postgres | Live transactional state |
| Hot Cache | Redis | Session, semantic cache, rate-limit buckets |
| Vector | Qdrant | Semantic memory |
| Object | Cloudinary / S3 | Uploads, generated PDFs, exports |
| Cold Analytics | R2/S3 Parquet + DuckDB | Long-tail event log, historical messages |

---

## 17. Deployment Strategy

### 17.1 Environments

`dev` (local Docker Compose) → `preview` (per-PR Vercel + Railway) → `staging` (mirrors prod, daily snapshot restore) → `prod`.

### 17.2 CI/CD (GitHub Actions)

```
PR opened ─► lint (ruff, eslint, mypy, tsc) ─► unit tests ─► OpenAPI diff check
          ─► alembic upgrade check ─► build Docker (multi-stage, distroless final)
          ─► deploy preview ─► e2e smoke (Playwright)

PR merged ─► deploy staging ─► run Promptfoo eval suite (gate)
          ─► canary 10% prod ─► metric/error budget check (15 min)
          ─► full rollout ─► tag release
```

### 17.3 Database Migrations

Alembic, one migration per PR, **expand-then-contract**:
1. Additive migration (add column, default null)
2. Backfill job (idempotent, batched)
3. App version that reads + writes new column
4. Cleanup migration (NOT NULL, drop old)

**Never deploy step 4 in same release as step 1.**

### 17.4 Rollback

- Vercel: instant via dashboard.
- Railway: previous image tag pinned, `railway rollback`.
- DB: forward-only philosophy; rollback via compensating migration.

---

## 18. LLMOps Architecture

### 18.1 Inference Gateway Topology

```
Agent ──► LiteLLM Proxy (in-process) ──► Euri AI Gateway ──► [Claude / GPT / Gemini / ...]
                │                                                      │
                │                                          └─ provider failover (in-gateway)
                │
                └─ on Euri down or > p95 SLA breach ──► Ollama local cluster
```

### 18.2 Model Routing Matrix

| Task | Primary | Secondary | Local Fallback |
|---|---|---|---|
| Outreach copy (personalized) | Claude Sonnet | GPT-4.1 | Llama 3.3 70B |
| Long-context planning | Claude Sonnet | GPT-4.1 | Qwen 2.5 32B |
| Structured extraction (JSON) | DeepSeek V3 | Gemini Flash | Qwen 2.5 14B |
| Social captions / creative | Gemini Flash | Claude Haiku | Llama 3.3 |
| Lead classification / ranking | DeepSeek | Qwen 14B | Phi-3.5 |
| Proposal generation | Claude Sonnet | GPT-4.1 | Llama 3.3 70B |
| Reply intent classification | GPT-4o-mini | Gemini Flash | Phi-3.5 |
| Embedding | bge-small (self-hosted) | OpenAI text-embedding-3-small | — |
| Reranking | bge-reranker-base (self-hosted) | Cohere Rerank | — |
| Moderation | Llama Guard 3 (self-hosted) | OpenAI Moderation | — |

Routing decision per request based on `task_class`, `tenant_plan`, `cost_budget_remaining`, `latency_target`.

### 18.3 Semantic Cache

Input prompt → embed → check `prompt_cache_global` for cosine ≥ 0.96 → if hit + same `task_class` + same `model_tier` → return cached response. Cache only deterministic-by-input tasks (extraction, classification). **Never cache personalized outreach copy** (would defeat personalization). Per-tenant private cache for prompts containing tenant data. PII filtered by Presidio before hash.

### 18.4 Prompt Optimization

- All prompts versioned in `prompt_templates`; promotion to `active` requires Promptfoo eval pass.
- Weekly cron: DSPy `BootstrapFewShot` over last 7 days of high-rated outcomes to propose new templates.
- Candidate vs. champion A/B at 10% traffic for 72h; promote on score lift > 5% and no guard regression.

### 18.5 Fallback Chains

```
Primary (Claude Sonnet) ──fail/timeout──► Secondary (GPT-4.1)
                          ──fail──► Tertiary (Gemini)
                          ──fail──► Local (Qwen 2.5 32B on Ollama)
                          ──fail──► Graceful degrade (cached response or HITL queue)
```

Every fallback decrement logged with reason; SRE alert on > 3% fallback-to-local rate over 5-min window.

### 18.6 Eval Pipelines

- **Pre-deploy gate (Promptfoo):** 200+ test cases per agent, run on every PR touching prompts; merge blocked on regression > 2%.
- **Continuous eval (daily):** sampled production traces re-scored by LLM judge for groundedness, format compliance, tone match.
- **Adversarial eval (weekly):** prompt-injection battery, jailbreak attempts; feed guardrail rule updates.

---

## 19. Monitoring & Observability

### 19.1 Stack

- **Langfuse** — LLM trace store; every agent run = one trace with nested spans per node/tool/model call.
- **OpenTelemetry** — application + workflow spans; `traceparent` propagated HTTP → Celery → DB.
- **Prometheus** — system + custom business metrics on FastAPI `/metrics` + Celery exporter.
- **Grafana** — dashboards (see §19.3).
- **Sentry** — error capture, release tracking, performance.

### 19.2 Correlation Strategy

Every inbound HTTP request gets a `request_id` (ULID). Propagated: HTTP → Celery task headers → LangGraph `RunnableConfig.metadata` → Langfuse trace `metadata.request_id`. One ID joins HTTP logs ↔ DB query logs ↔ Celery logs ↔ LLM trace.

### 19.3 Dashboards

| Dashboard | Panels |
|---|---|
| Tenant Health | Per-tenant request rate, p95 latency, error %, token spend, agent success % |
| Agent Runtime | Run count by agent, success rate, p50/p95/p99 latency, retry rate, HITL rate |
| LLMOps | Token usage by model, cost projection, fallback rate, cache hit rate, eval score trend |
| Workflow | DLQ size, replay rate, checkpoint count, longest-paused workflows |
| Channels | Per-channel send rate, delivery %, reply %, compliance-block rate |
| Business | New tenants, MRR, churn, avg reply rate, avg meetings/tenant/month |

### 19.4 SLOs & Alerts

| SLO | Target | Burn Alert |
|---|---|---|
| API availability | 99.9% monthly | 2% budget burn in 1h → Sentry alert |
| Agent run success | 96% rolling 24h | < 94% for 30 min → page on-call |
| Outreach send error rate | < 1% | > 2% for 15 min → page |
| Token cost / tenant / day | < ₹20 avg | > ₹40 for any tenant → notify ops |
| ComplianceGuard false-positive rate | < 0.5% | > 1% for 1h → notify |

### 19.5 Workflow Replay Debugging

Any failed run is fetchable via admin UI with full state diff per node and re-executable against staging with the exact same `WorkflowState` + sandbox tool registry — same input, deterministic replay.

---

## 20. Security Architecture

- **AuthN:** Email/Phone OTP for trainers; OAuth2 + JWT (RS256, 15-min access + 30-day refresh); MFA enforced for OrgAdmin+.
- **AuthZ:** Casbin policy engine; deny-overrides; policies version-controlled.
- **Secrets:** Doppler / Infisical (prod); Railway Secrets (preview); rotated 90-day; CI fails on `gitleaks` finding.
- **Transport:** TLS 1.3 everywhere; HSTS preload; mTLS between internal services (Stage 2+).
- **At-Rest:** Postgres TDE; Cloudinary/S3 SSE; secrets sealed.
- **PII Masking:** Presidio analyzer on every prompt pre-model; redacted tokens substituted; reversed only in tenant-scoped post-processing.
- **Prompt Injection:** LLM-Guard input filter; output validators with allowlist for tool invocation; no agent can call an unregistered tool.
- **Output Validation:** Structured outputs schema-validated; free-text outputs pass moderation + grounding (must cite tool IDs when claiming facts).
- **Rate Limits:** Per-tenant, per-endpoint, per-IP layered; abusive IP auto-blocked at Cloudflare WAF.
- **Audit:** Append-only `audit_events` for every privileged action; 7-year retention for Enterprise.
- **Compliance:** GDPR + India DPDP Act — right to erasure as cascading soft-delete + 30-day hard purge; per-tenant data residency tag; per-tenant data export endpoint.

---

## 21. AI Safety & Governance

- **Bias mitigation:** Audience selection cannot include/exclude on demographic attributes not explicitly consented. Forbidden filters (gender, religion, caste): hard denylist; lint at policy-creation.
- **Content moderation:** Llama Guard 3 on every outbound customer-facing message; block + alert on flagged categories.
- **Hallucination floor:** Any claim about a trainer's credentials, pricing, or workshop content must resolve to a locked profile row; unresolved claims trigger re-prompt or HITL.
- **HITL gates:**
  - Campaign sends to > 200 recipients
  - Any agent action with monetary impact > ₹2,000
  - First-week-of-tenant: everything HITL by default (**training-wheels mode**)
  - Any LinkedIn/Email/WA send to a "do-not-contact" flagged contact (defense-in-depth)
- **Explainability:** Every AI-proposed action carries a `rationale` field (≤ 280 chars) shown in UI.
- **Right to opt-out of AI training:** Tenants can opt out of contributing data to the cross-tenant model loop while still receiving model improvements.

---

## 22. Cost Estimation & Token Economics

### 22.1 Per-Tenant AI Cost Model (Growth Plan)

| Workload | Runs/Month | Avg Tokens (in+out) | Avg Cost @ Mid-tier (₹) | Subtotal |
|---|---|---|---|---|
| Trainer profile extraction (one-time + edits) | 8 | 18,000 | 2.40 | ₹19 |
| HR discovery runs | 12 | 28,000 | 3.80 | ₹46 |
| Outreach generation | 2,500 | 1,800 | 0.30 | ₹750 |
| Reply classification | 800 | 600 | 0.05 | ₹40 |
| Proposal generation | 35 | 22,000 | 3.20 | ₹112 |
| Social caption / creative | 120 | 1,400 | 0.18 | ₹22 |
| Analytics + optimizer (daily) | 30 | 12,000 | 1.60 | ₹48 |
| Guardrails + evals overhead | — | — | — | ₹160 |
| **Subtotal pre-cache** | | | | **₹1,197** |
| Semantic cache savings (~38%) | | | | −₹455 |
| **Net AI COGS / tenant / mo** | | | | **₹742** |

Target Growth-tier ASP ₹4,999/mo → **gross margin ~85% on AI alone**, before infra amortization. (Higher than RevenueTable because text-only — no voice COGS.)

### 22.2 Cloud Infrastructure

| Component | 100 Tenants | 1,000 Tenants | 10,000 Tenants |
|---|---|---|---|
| Vercel (frontend) | ₹0 | ₹1,800 | ₹14,000 |
| Railway (compute + Postgres + Redis) | ₹4,500 | ₹38,000 | ₹2,80,000 |
| Qdrant | ₹0 | ₹6,500 | ₹52,000 |
| Cloudinary / S3 | ₹400 | ₹3,500 | ₹32,000 |
| Euri AI inference (net of cache) | ₹74,200 | ₹7,42,000 | ₹74,20,000 |
| Observability (Langfuse self-host + Sentry) | ₹1,000 | ₹8,000 | ₹65,000 |
| **Total / month** | **₹80,100** | **₹7,99,800** | **₹78,63,000** |
| **Per-tenant / month** | **₹801** | **₹800** | **₹786** |

Per-tenant cost is nearly flat — infra scales linearly with inference; everything else amortizes.

### 22.3 AI Budget Enforcement

- Per-tenant monthly token ceiling in `TenantContext.ai_budget`.
- Pre-call estimator on every LLM call; if `spent + estimate > budget`, queued (best-effort) or rejected (hard ceiling).
- 70% / 85% / 95% threshold alerts to OrgAdmin via email + dashboard banner.
- Premium models (Claude/GPT-4-class) reserved for: personalized outreach, proposals, strategic copy. Cheap models (DeepSeek, Qwen, Gemini Flash, Haiku) for: classification, extraction, ranking.

---

## 23. Scaling Strategy & Infrastructure Evolution

### 23.1 Stage 1 — Solo-Dev MVP (0–500 tenants)

Modular monolith, 5 Celery worker pools, single Postgres + Redis, Qdrant free tier, optional Ollama on Hetzner ARM ($14/mo) for fallback. **Bottleneck:** Postgres connections + Celery concurrency.

### 23.2 Stage 2 — Multi-Worker, Service-Split (500–5,000 tenants)

Extract `social/` and `whatsapp/` modules as separate services (I/O-heavy). Postgres read-replica for analytics; PgBouncer for connection pooling. Redis clustered. Qdrant paid tier with replication. Cloudflare edge cache. Full OTel + Grafana stack. **Trigger:** p95 > 800ms at gateway OR Celery queue depth > 200 sustained.

### 23.3 Stage 3 — Distributed, Multi-Region (5,000+ tenants)

Kubernetes (Hetzner/EKS managed). Postgres sharded by `org_id` (Citus) or per-region cluster. Kafka/Redpanda for cross-service event bus; Redis Pub/Sub retained intra-service. Multi-region inference. Dedicated GPU pool for self-hosted Llama 70B + reranker. SOC2 Type II audit complete. **Trigger:** ARR > ₹4 Cr OR first Enterprise dedicated-VPC ask.

### 23.4 Migration Tradeoffs (Honest)

- **Premature K8s** is the #1 failure mode of agentic startups — defer until ≥ 3 engineers + clear scaling pain.
- **Premature Kafka** = 6 weeks of ops work for benefit only > 10k EPS.
- **Premature multi-region** introduces consistency headaches; defer until a paying tenant requires it.

---

## 24. Business Model

### 24.1 Pricing Tiers

| Tier | Starter | Growth | Enterprise | White-Label |
|---|---|---|---|---|
| **Price (INR/mo)** | ₹999 | ₹4,999 | ₹19,999+ (custom) | Custom |
| **AI runs/month** | 1,000 | 15,000 | Unlimited (fair-use) | Per agreement |
| **Outreach sends/month** | 500 | 5,000 | Unlimited | Per agreement |
| **Agents enabled** | Trainer, HRDiscovery, Outreach, Email + WA | + IG, FB, Telegram, Proposal | All + custom | All + branded |
| **Channels** | Email, WhatsApp | + IG, FB, Telegram, LinkedIn-post | + Custom integrations | All |
| **Workspaces** | 1 | 5 | Unlimited | Unlimited |
| **Support** | Email | Email + chat | Dedicated CSM | Dedicated team |
| **Data residency** | Shared India | Shared (India / US) | Dedicated cluster | On-prem option |

### 24.2 Add-Ons

- Extra outreach sends: ₹0.40 / message
- Extra AI runs: ₹40 / 1,000 runs
- Custom integration setup: ₹50,000 one-time
- White-label setup: ₹1,50,000 one-time + ₹25,000/mo per reseller

### 24.3 CAC / LTV Assumptions

- Blended CAC: ₹3,200 (organic content + community + paid)
- Average ARPU: ₹3,800/mo
- Gross margin: 75%
- Logo churn: 2.0%/mo target → 14-month payback
- **LTV/CAC target: ≥ 4×** within 18 months

---

## 25. ROI Analysis (Trainer's POV)

| Lever | Baseline | With CorporateMind AI | Annualized Impact (solo trainer) |
|---|---|---|---|
| HR research hours saved | 16 hrs/week | 1 hr/week | +780 hrs/yr |
| Outreach reply rate (2% → 14%) | 60 leads × 2% = 1.2 mtgs | 60 leads × 14% = 8.4 mtgs | +7.2 meetings/cycle |
| Workshops booked / month | 1 | 4 | +36 workshops/yr @ ₹40k = **+₹14.4 L** |
| Proposal turnaround (4h → 5m) | 12 proposals/yr lost to slow turnaround | All same-day | +6 closes/yr @ ₹40k = **+₹2.4 L** |
| Marketing tool stack replaced | ₹8k/mo (Apollo + Buffer + Calendly + ...) | ₹5k/mo CorporateMind | **−₹36 k/yr cost** |
| **Total annual impact** | | | **~₹17 L net upside** |
| CorporateMind cost (Growth, 12 mo) | | | −₹60 k |
| **Net** | | | **~₹16.4 L → 27× ROI** |

A solo trainer pays back the platform in **week 2**.

---

## 26. Competitive Differentiation

| Capability | Apollo | Lemlist | HubSpot | Buffer | Tagmango | Generic GPT | **CorporateMind AI** |
|---|---|---|---|---|---|---|---|
| HR discovery (intent-matched) | Partial | — | — | — | — | — | ✅ |
| Personalized outreach (per-recipient) | Partial | Partial | — | — | — | Partial | ✅ |
| Multi-agent orchestration | — | — | — | — | — | — | ✅ |
| Trainer-niche aware | — | — | — | — | Partial | — | ✅ |
| AI proposal generation | — | — | — | — | — | — | ✅ |
| Omnichannel (WA+TG+IG+FB+Email+LI-post) | Partial | — | Partial | Partial | Partial | — | ✅ |
| WhatsApp Business native | — | — | Partial | — | Partial | — | ✅ |
| Compliance-as-agent | — | — | — | — | — | — | ✅ |
| Self-healing workflows | — | — | — | — | — | — | ✅ |
| Indian pricing (₹999 entry) | — | — | — | — | ✅ | — | ✅ |
| **Positioning** | US-centric DB | Cold-email tool | Generic CRM | Social scheduler | Course platform | Chatbot | **Autonomous B2B Growth OS** |

---

## 27. Pillar-Based Platform Architecture (7 Pillars)

Each Pillar follows the same 5-stage autonomous loop (§9.2). The pattern is the moat: any future capability plugs in as a new Pillar using the same orchestrator + LLMOps spine.

### PILLAR 1 — TRAINER INTELLIGENCE
**What It Solves:** Trainer profiles in current SaaS are 30-field forms abandoned mid-completion. Trainers know their craft; they cannot articulate it as metadata. The result: bad segmentation, generic outreach, low fit.

**Workflow:**
```
Upload (poster/video/PDF/voice) → OCR + Vision + Whisper → Field extraction
        → Embedding → Profile lock → Match-ready vector
```

**Agents:** TrainerProfileAgent, ingestion workers.
**ROI:** Onboarding time 60+ min form → < 5 min upload. Activation rate +200%.

### PILLAR 2 — HR DISCOVERY
**What It Solves:** LinkedIn manual scrolling, stale CSVs, irrelevant lists. Trainers waste 12–20 hrs/week on research.

**Workflow:**
```
Trainer profile vector → Match candidate companies (industry/size/region rules + semantic)
   → Surface HR/L&D contacts from opt-in sources → Score (0–1) per (trainer × contact)
   → Trainer reviews segment → Lock for campaign
```

**Agents:** HRDiscoveryAgent, ScraperWorker (ToS-bounded), SentimentScorer.
**ROI:** 50+ matched contacts in < 30 min, 100% opt-in-verified.

### PILLAR 3 — OUTREACH AI
**What It Solves:** Cold outreach reply rates are < 3% because messages are channel-blind, recipient-blind, and tone-blind.

**Workflow:**
```
Recipient × Trainer → Personalization context (industry, recent news, fit angle)
   → Channel-aware draft (Email/WA/Telegram/LI-post) → A/B variants
   → ComplianceGuard → HITL if > 200 → Send → Track delivery/open/reply
```

**Agents:** OutreachAgent (lead), CopyWriter, Scheduler, AttributionAgent.
**ROI:** Reply rate 2% → 12–18%. Campaign cycle 3 days → 60 min.

### PILLAR 4 — SOCIAL AUTOMATION
**What It Solves:** Trainers post random content randomly. No cadence, no brand consistency, no funnel.

**Workflow:**
```
Content calendar (auto-generated from trainer profile + campaign goals)
   → Channel-specific drafts (IG reel caption, FB post, LI post, TG broadcast)
   → Trainer approves → Scheduled publish → Engagement tracking → Optimizer learns
```

**Agents:** InstagramAgent, FacebookAgent, TelegramAgent, LinkedInAgent (publish only).
**ROI:** 4× content output at same trainer time; consistent brand voice.

### PILLAR 5 — PROPOSAL AUTOMATION
**What It Solves:** Proposals take 3–5 hours. Slow proposals lose deals.

**Workflow:**
```
Positive reply detected → Trainer triggers proposal → ProposalAgent drafts:
  cover / problem / solution / agenda / pricing / case studies
→ PDF render → Trainer edits → Send → Tracked
```

**Agents:** ProposalAgent, PDFRenderer.
**ROI:** Turnaround 4h → 5 min. Close rate +30%.

### PILLAR 6 — CRM INTELLIGENCE
**What It Solves:** Generic CRMs require manual updating; trainers don't.

**Workflow:**
```
Every send / reply / open / meeting → auto-update lead state
   → Pipeline board reflects reality → Daily insight cards: who to nudge today
```

**Agents:** AnalyticsAgent, NextBestAction.
**ROI:** Zero manual CRM upkeep; pipeline always current.

### PILLAR 7 — MULTI-AGENT RUNTIME (LangGraph + Euri)
**What It Solves:** Single-model chatbots cannot orchestrate the above six. They lack memory, tools, gating, and observability.

**Provides:** Shared `WorkflowState`, checkpointing, HITL gates, tool sandboxing, ComplianceGuard, model routing, eval pipelines, replay debugging.

**ROI:** Enables Pillars 1–6 to exist as autonomous systems instead of GPT wrappers.

---

## 28. Self-Healing Workflow Systems

Failure is a first-class operating condition. Self-healing has six layers:

1. **Per-step retry with exponential backoff** for transient errors (network, 5xx, 429).
2. **Self-repair re-prompting** for schema-invalid LLM outputs (max 2 attempts, then escalate).
3. **Provider fallback chain** (Euri primary → secondary → tertiary → Ollama local → cached / HITL).
4. **Sandboxed tool execution** with per-tool timeouts, output validators, idempotency keys (safe replay).
5. **Checkpointed workflow state** so any node resumes after a process restart or HITL pause.
6. **DLQ + reaper + replay** to capture, group, diagnose, and replay failures once a fix ships.

**Failure isolation:** Every Celery worker pool bulkheaded by queue; one tenant's runaway loop cannot starve another's outreach send. Per-tenant concurrency caps enforce this at queue level.

**Circuit breakers** on every external dep: open after 5 consecutive failures or > 50% error rate in 60s; half-open after 60s; closed on 3 consecutive successes. Open-circuit responses are degraded but never silent — UI surfaces "AI temporarily unavailable; falling back to draft mode."

---

## 29. Continuous Learning Pipelines

```
User feedback (accept / edit / reject) → Outcome events → Postgres + Langfuse
                                              │
                                              ▼
Daily curation job → Quality-rated examples → RLHF candidate set
                                              │
                                              ▼
Weekly DSPy optimization → Prompt candidate → Promptfoo eval gate
                                              │
                                              ▼
A/B routing (10% traffic, 72h) → Outcome comparison → Promote / rollback
                                              │
                                              ▼
Drift monitor: weekly eval against frozen golden set → Alert on > 3% regression
```

The RLHF dataset is the **proprietary moat** — it compounds with every interaction, and cannot be replicated by a competitor without operating tenants of the same density and tenure.

---

## 30. Future Roadmap

| Phase | Timeline | Deliverables | Success Metric |
|---|---|---|---|
| **Phase 1: Cockpit** | Month 0–3 | Trainer Intel + HR Discovery + Outreach + Email + WA, single-workspace tenants | 80 paying tenants |
| **Phase 2: Omnichannel** | Month 4–6 | Telegram, IG, FB, LinkedIn-post, Proposal generation, multi-workspace | 400 tenants, ₹15 L MRR |
| **Phase 3: Optimization & White-Label** | Month 7–9 | CampaignOptimizer, semantic cache, prompt-opt loop, agency white-label v1 | 1,000 tenants, ₹45 L MRR |
| **Phase 4: Enterprise & Network** | Month 10–14 | SSO, dedicated cluster, audit, cross-tenant insight network (opt-in) | 1,600 tenants, ₹1.4 Cr ARR |
| **Phase 5: Platform** | Month 15–24 | Voice outreach (inbound + outbound), AI meeting summaries, public tool/plugin SDK, marketplace | 2,500+ tenants, ₹3 Cr ARR |

### Sprint-Level Milestones (Phase 1)

- **Sprint 1 (W1–2):** Monorepo, tenant + workspace + auth + onboarding wizard
- **Sprint 2 (W3–4):** Trainer upload + ingestion + TrainerProfileAgent + profile UI
- **Sprint 3 (W5–6):** HR Discovery agent + lead list UI + opt-in source registry
- **Sprint 4 (W7–8):** Outreach generation + Email channel + ComplianceGuard v1
- **Sprint 5 (W9–10):** WhatsApp channel + follow-up cadence + HITL approval queue
- **Sprint 6 (W11–12):** CRM/pipeline UI + insight cards + observability v1 + design-partner onboarding (10 tenants)

---

## 31. Risks & Assumptions

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Frontier LLM API breakage / pricing shock | Medium | High | Euri abstraction + Ollama fallback + monthly cost ceilings |
| WhatsApp policy change blocks marketing templates | Medium | High | Multi-channel (Email + IG + Telegram) so WA is not single point of failure |
| LinkedIn ToS tightening on automation | High | Medium | Strict policy: only public company data + page posts; no personal DM automation ever |
| Indian email deliverability (DKIM/SPF/DMARC) issues | Medium | Medium | Per-tenant subdomain warmup; Postmark/SES with reputation monitoring |
| Trainer/coach segment too small for ₹2 Cr ARR | Low | High | Expand to consultants, sales enablement firms, leadership coaches (TAM × 4) |
| Competitor (Apollo, Lemlist, HubSpot) adds agent layer | Medium | Medium | Speed + Indian channel-native (WA/UPI) + niche specialization is our moat |
| Founder bandwidth as solo-dev MVP | High | High | Phase 1 scope intentionally bounded; outsource design/QA |
| Compliance incident (spam complaint, opt-in dispute) | Medium | High | ComplianceGuard as first-class agent; audit log on every send; DPDP-compliant erasure |

**Assumptions:**
- Euri AI maintains ≥ 99.5% gateway availability.
- Frontier model token prices decline ~30% YoY.
- WhatsApp Business Cloud API remains the dominant Indian B2B messaging channel.
- Trainers accept HITL-gated automation (not full autonomy on Day 1).
- LinkedIn maintains public company-page API access on current terms.

---

## 32. Open Questions

1. Self-host Whisper for transcription at MVP, or use Deepgram free tier to ship 4 weeks earlier?
2. Should the cross-tenant "insight network" (Horizon 2) be opt-in or default with anonymization?
3. White-label: allow tenants to bring their own LLM keys (BYOK) and bypass our gateway?
4. Email provider for outbound: Postmark (deliverability), SES (cost), or Resend (DX)?
5. WhatsApp BSP: direct Cloud API or via AiSensy/Gupshup (cheaper templates, slower approvals)?
6. Where do we draw the line between "AI proposes" and "AI sends without approval" — per-feature default or tenant policy?
7. Phone-OTP via MSG91 (Indian) or Twilio Verify (global)?
8. Multi-region: second region after India — SEA (volume) or Middle East (avg deal size)?
9. Do we publish RLHF-derived insights back to tenants ("trainers like you saw X work") as a feature?
10. Voice outreach (Phase 5) — partner with Vapi/Bland, or extend in-house from RevenueTable AI's stack?
11. Pricing: per-workspace flat vs. per-send usage vs. hybrid?
12. SOC2: pre-revenue (Enterprise readiness) or post-Series-A (capital efficient)?
13. Do we offer a "managed migration" service from Apollo/Lemlist as a paid wedge?
14. Native mobile app vs. PWA + WhatsApp as distribution?
15. How is "trainer/coach" distinguished from "consultant/freelancer" in pricing — same product, different acquisition channel?
16. Public stance on AI-generated reviews/testimonials and inbound UGC moderation?
17. Long-term: monetize anonymized hiring-intent signals as a B2B data product to L&D vendors?

---

## 33. Enterprise Expansion Strategy

- **Agency Rollout Playbook:** Pilot with 1 lead trainer at the agency → 60-day metrics review → batch-onboard remaining trainers with shared HR DB + brand guardrails; HQ approves brand-level templates; per-trainer autonomy within those guardrails.
- **White-Label:** Re-brandable theme, custom domain, BYOK (Enterprise+), sub-tenant management UI for the reseller, revenue share or wholesale pricing.
- **LMS Partner Integrations:** Tagmango, Exly, Graphy — bidirectional sync of trainer profiles + booked workshops.
- **Marketplace (Horizon 3):** Third-party agents (e.g., "Diwali campaign pack", "Q1 L&D budget cycle pack", "GST proposal pack") sold via marketplace; revenue share with publishers.
- **Data Residency & Sovereignty:** Region-pinned tenants; India region default; expansion to SEA (Singapore) and ME (Bahrain) by Phase 5.

---

## 34. Final Strategic Positioning

CorporateMind AI is **not** competing for "best email tool" or "best CRM" slot. Those categories are commoditized races to zero margin. We are creating — and intend to own — the category of **Autonomous AI Business Growth Operating System for Expert-Services Professionals**, where the trainer's role shifts from orchestrator to approver-and-deliverer, and where every Pillar plugged into the LangGraph spine compounds the moat:

**more agents → more outcomes → better RLHF → cheaper inference → higher margin → faster shipping → more agents**

The technical bet: a tightly-scoped 12-agent system, on a free-OSS-first stack, with provider-abstracted inference and ruthless cost telemetry, can deliver investor-grade unit economics from tenant #1 while remaining a single-engineer-feasible MVP.

The product bet: trainers and coaches — once they have one workshop booked through CorporateMind in week 2 — will never voluntarily return to Apollo + Buffer + spreadsheets.

Every architectural choice in this document is in service of that two-part bet: **ship fast on a defensible substrate, evolve the substrate without rewriting it.**

---

## Appendix A — AI Memory Architecture (Deep Spec)

### A.1 Memory Class Definitions

| Class | Definition | Backing | Retrieval Pattern |
|---|---|---|---|
| Working | Per-workflow-run scratchpad | In-process Pydantic state | Direct attribute access |
| Short-term Conversational | Last N turns of a chat session | Redis hash, `conv:{session_id}`, TTL 30m sliding | Full-load on turn |
| Episodic | "What happened" — past agent runs and outcomes | Postgres `agent_runs`, `agent_events`; vectors in Qdrant `campaign_outcomes_{org}` | Vector search + recency-weighted rerank |
| Semantic | "What is true" — trainer expertise, HR/company facts | Qdrant per-tenant; primary in Postgres | Hybrid search + cross-encoder rerank |
| Procedural | "How to do X" — versioned prompts and skills | `prompt_templates` table | Template fetch by `(name, version, env)` |

### A.2 Retrieval Scoring

`final_score = α · cosine + β · BM25 + γ · recency_decay + δ · outcome_weight`
Default `(α, β, γ, δ) = (0.55, 0.20, 0.15, 0.10)` — tunable per agent.

### A.3 Pruning & TTL

- Conversational: hard 30-min sliding TTL.
- Episodic: 90 days hot in Postgres, archived to S3 Parquet cold; vectors retained 12 months.
- Semantic: re-embed quarterly; old vectors archived; never destructively deleted within retention window.
- Procedural: versioned, never deleted (audit trail).

### A.4 Memory Observability

Every retrieval emits a Langfuse span with: query, top-k IDs, scores, latency, tokens-injected. A "Memory Inspector" admin view shows what context any past run saw.

### A.5 Cost Discipline

- Memory-injected tokens budgeted per run (default 2,400 tokens).
- Truncation order: oldest episodic > lowest-scored semantic > lowest-scored conversational.
- Cache-aware: identical retrieval queries within a run hit Redis-side memo.

---

## Appendix B — AI Agent Runtime System (Deep Spec)

### B.1 Lifecycle

```
INIT → HYDRATE_CONTEXT → PLAN → (EXECUTE ↔ VERIFY)* → FINALIZE → EMIT_EVENTS → ARCHIVE
                                          │
                                          └─ on fail ─► RETRY / FALLBACK / HITL / DLQ
```

### B.2 Planner-Executor Split

- **Planner** generates a strict-schema `Plan { steps: List[Step] }` with explicit `tool`, `inputs`, `expected_output_schema`.
- **Executor** is a deterministic dispatcher — it does not reason; it executes the plan. This split makes every action auditable and replayable.

### B.3 Checkpointing

Every state transition writes `(workflow_id, node, version, state_blob, ts)` to `workflow_checkpoints`. Workflows are resumable from any checkpoint, in any process. Resumption validates `schema_version`; migrations registered per `(from, to)`.

### B.4 Task Delegation

The RootOrchestrator decomposes high-level intent into sub-agent invocations. Sub-agents are first-class: own state, memory, tools. They communicate **only** via the shared `WorkflowState`, never directly — which makes the topology a tree (deterministic, debuggable), not a mesh.

### B.5 Concurrency

- Per-tenant concurrency cap on `agents` Celery queue (default: Starter=2, Growth=8, Enterprise=32).
- Within a workflow, parallel sub-agent calls fan out via `asyncio.gather` with per-call timeouts.

### B.6 Tool Sandboxing

Tools registered with explicit schemas + per-tool budgets (`max_calls_per_run`, `max_tokens_per_call`, `timeout_s`). Executor enforces. Tools marked `read_only` (default), `mutating_low_risk`, or `mutating_high_risk` — the last requires HITL or explicit policy approval.

### B.7 Runtime Observability

Each node emits an OTel span carrying `tenant_id`, `agent`, `node`, `model`, `tokens_in`, `tokens_out`, `latency_ms`, `result_status`, `request_id`. Langfuse correlates the LLM trace; Sentry captures any exception with the same `request_id`.

---

## Appendix C — Event Catalog & Contracts

### C.1 Event Envelope

```json
{
  "event_id": "01J4...",
  "event_type": "outreach.message_sent",
  "version": "1.0",
  "occurred_at": "2026-05-23T14:32:11.482Z",
  "tenant_id": "org_...",
  "workspace_id": "ws_...",
  "actor": { "type": "agent", "id": "OutreachAgent" },
  "payload": { "...": "..." },
  "trace_id": "..."
}
```

### C.2 Naming Convention

`<domain>.<entity>.<verb_past>` — e.g. `lead.discovered`, `outreach.message_sent`, `campaign.approval_requested`.

### C.3 Core Events

| Event | Producer | Consumers |
|---|---|---|
| `trainer.profile_extracted` | TrainerProfileAgent | HR discovery trigger, dashboard |
| `lead.discovered` | HRDiscoveryAgent | Enrichment, dashboard |
| `outreach.draft_ready` | OutreachAgent | HITL approval notifier |
| `outreach.message_sent` | Send pipeline | Attribution, analytics |
| `outreach.replied` | Reply ingester | Conversation thread, NextBestAction |
| `campaign.approval_requested` | OutreachAgent | Trainer inbox |
| `proposal.draft_ready` | ProposalAgent | Trainer review |
| `meeting.scheduled` | Calendly webhook | CRM, reminder scheduler |
| `agent.run_failed` | LLMOpsGuardian | DLQ persister, SRE alert |
| `compliance.block` | ComplianceGuardAgent | Audit log, trainer notification |

### C.4 Delivery Semantics

At-least-once, idempotent on `event_id`. Consumers register handlers with explicit `is_idempotent: true` declaration — non-idempotent handlers rejected at registration.

### C.5 Replay

Event log append-only; per-consumer cursor in Redis. Replay is consumer-scoped: rewind cursor to a timestamp; consumer re-processes. Replays gated by feature flag per environment.

---

## Appendix D — Multi-Tenancy Reference Model

```
Organization (LeadIn Coaching LLP — agency)
├── Workspace: Priya NLP (lead trainer)
│   ├── Trainer profile: Priya
│   └── Trainers: Priya, Asha (junior)
├── Workspace: Rajiv Leadership (sister brand)
│   └── Trainer: Rajiv
└── Settings
    ├── Subscription: Growth × 2 workspaces
    ├── AI Budget: ₹4,000/mo
    ├── Feature Flags: linkedin_post=on, proposal_v2=on, semantic_cache=on
    └── Compliance: DPDP region=India, retention=24mo
```

- Per-workspace brand voice, brand assets, template library.
- Per-workspace channels (each trainer connects own WA/IG/FB).
- Per-org billing, RBAC, AI budget, feature flags, data residency.
- Per-user role (scope = org / workspace / specific resource).

This hierarchy is the **single source of truth** referenced by every service, agent, and policy. Every other capability — from semantic memory partitioning to inference rate-limits — derives from it.

---

## Appendix E — Proposed `CLAUDE.MD` (engineering operating manual)

> To be written to `./CLAUDE.MD` in Phase 0. Adapted from the AI Customer Support Copilot reference for CorporateMind AI's actual scope.

```markdown
# CLAUDE.md — CorporateMind AI

## Role
Act as a staff engineer, AI architect, and SaaS production reviewer for CorporateMind AI — an autonomous AI corporate-outreach and multi-channel growth OS for trainers, coaches, consultants, and speakers.

## Project context
- Frontend: Next.js 14 (App Router, RSC, TanStack Query, Tailwind, shadcn/ui)
- Backend: FastAPI (async) — modular monolith
- Data: PostgreSQL (primary), Redis (cache/queue/rate-limit), Qdrant (embeddings/semantic cache)
- AI runtime: LangGraph multi-agent
- AI gateway: Euri AI Gateway — the ONLY egress to LLM providers
- Workers: Celery (Redis broker) + Celery beat
- Storage: Cloudinary / S3-compatible
- Channels: Email, WhatsApp Business Cloud API, Telegram, Instagram Graph, Facebook Graph, LinkedIn (public-only)
- Deploy: Vercel (web) + Railway (api/workers/db/redis)
- Observability: Langfuse, Prometheus + Grafana, Sentry, OpenTelemetry

## Architecture (modular monolith, 7 pillars)
Modules under `apps/api/src/corpmind/modules/`:
`identity, trainer_intel, hr_discovery, outreach, social, whatsapp, proposals, crm, campaigns, analytics, billing, compliance`.

Each module follows Ports & Adapters: `api.py | service.py | repo.py | models.py | schemas.py | events.py`.
Inter-module rule: modules MUST NOT import each other's `repo.py` or `models.py`. Cross-module talk via service interfaces (DI) or in-process event bus.

## Core behavior
- Production-grade code over quick hacks. No demo scaffolding.
- Preserve patterns; don't refactor opportunistically.
- Inspect neighbors before editing.
- Briefly justify tradeoffs when introducing new patterns.
- Design for horizontal scale and per-tenant isolation from day one.
- Stage 1 = modular monolith on Railway. Do NOT preemptively introduce Kafka, k8s, or microservices.

## Multi-tenancy rules (NON-NEGOTIABLE)
- Every business table has `tenant_id UUID NOT NULL` + composite index.
- `TenantContext` contextvar set in middleware; every query MUST filter by it.
- Postgres RLS enabled as defense-in-depth.
- Qdrant filters include `tenant_id` predicate on every search.
- Cross-tenant access is a P0 bug; regression test per new table.

## Backend engineering rules
- Async FastAPI endpoints unless strong reason not to.
- Route handlers ≤ 15 lines; logic in `service.py`, persistence in `repo.py`.
- Pydantic v2 for ALL schemas — no raw dicts cross boundaries.
- SQLAlchemy 2.0 async + Alembic. Never edit applied migrations.
- Structured JSON logging (structlog); correlation IDs propagated.
- Explicit exception handling; stable error envelope.
- No hardcoded secrets/URLs — `pydantic-settings` only.
- DI via FastAPI `Depends()`; no global state.
- Idempotency-Key on all mutating endpoints (Redis, 24h TTL).

## Frontend engineering rules
- Next.js App Router, RSC by default.
- Strict TypeScript — no `any`.
- Small reusable components; feature-sliced layout.
- Separate UI from data fetching (TanStack Query hooks).
- Every async surface has loading, empty, error states.
- API client centralized; types generated from OpenAPI.
- SSE hook for agent-run / campaign-progress streams.

## Database rules
- UUID v7 primary keys.
- Indexes on hot paths.
- JSONB + GIN for flexible metadata; never for fields queried by equality often.
- Soft-delete for customer-facing entities.
- Partition `outreach_messages`, `whatsapp_messages`, `analytics_daily` monthly at scale.
- No destructive schema changes without reversible migration.

## Euri AI Gateway rules (sole LLM egress)
- All LLM calls via `corpmind.ai.euri_client.EuriClient`. Importing `openai`, `anthropic`, `google.generativeai` directly is forbidden.
- `routing.py` maps `task_type → (primary, fallback_chain)`.
- Wrap every call: `PromptInjectionFilter → PIIRedactor → SemanticCache → Euri → OutputModerator`.
- Every call traced to Langfuse with `tenant_id`, `agent`, `prompt_version`, `cost_tokens`.
- Prompts versioned (file-backed registry); never inline a prompt in business logic.
- Token budgets enforced per tenant; over-budget returns typed error.

## AI agent rules (LangGraph)
- One responsibility per agent. Tools explicit and minimal.
- Shared `AgentState` TypedDict; no untyped graph state.
- Deterministic helpers around fragile model behavior.
- Fallback path for low-confidence outputs.
- Never expose raw model output without post-processing + moderation.
- HITL interrupts when: recipients > 200, enterprise tier, ComplianceGuard flag, sensitive content classifier.
- Log key decisions to Langfuse.

## Semantic cache rules
- Qdrant `prompt_cache` keyed by (tenant_id, task_type, embedding).
- Cache only deterministic-by-input tasks. Never cache personalized outreach copy.
- TTL + invalidation on prompt-version bump.

## RAG / retrieval rules
- Separate ingestion → chunking → embedding → retrieval → generation.
- Chunk size/overlap configurable per source.
- Source attribution on every retrieval result.
- Log low-confidence retrievals.

## Campaign & lead lifecycle rules
- Campaign states: `draft → pending_approval → scheduled → sending → completed | paused | failed`.
- Lead pipeline: `discovered → contacted → engaged → replied → meeting_scheduled → meeting_done → booked | lost`.
- Auto-classification user-overridable.
- Duplicate-detection logs matches + confidence.
- Routing rules configurable in DB, not code.

## Channel adapter rules
- Every channel implements `corpmind.channels.base.ChannelAdapter` (`send`, `fetch_status`, `handle_webhook`).
- No provider SDKs in business modules.
- Circuit breakers + exponential backoff.
- All outbound calls logged with status + latency.
- Webhooks verify HMAC BEFORE parsing.
- Per-channel Redis token-bucket rate limiters tuned to provider limits.

## Compliance & anti-spam rules (NON-NEGOTIABLE)
- Every outbound message via `ComplianceGuardAgent` before send.
- Opt-ins tracked per (tenant, contact, channel); unsubscribes global per tenant.
- WhatsApp: enforce 24-hour window; approved templates outside.
- Email: physical address + unsubscribe footer; honor `List-Unsubscribe`.
- LinkedIn: NEVER automate personal DMs or scrape private data. Public company data + opt-in only.
- Duplicate detection (content + recipient) before send.
- Frequency cap per (tenant, contact, channel) — default 1/week.
- Audit log every send + every block.

## Integration rules
- Third-party via adapter pattern; no direct SDK calls in business modules.
- Endpoints config-driven.
- Circuit breakers + retries with jitter.
- Secrets in Doppler/Infisical for prod.

## Security rules
- Validate + sanitize ALL untrusted input.
- Never expose stack traces.
- JWT (RS256), refresh rotation; httpOnly cookies.
- RBAC via Casbin.
- PII detection + masking in logs.
- Treat uploaded posters/videos and scraped HR data as untrusted; sandbox parsing.
- Encrypt sensitive columns at rest (channel tokens, OAuth refresh tokens).
- Audit log for every privileged operation; append-only.
- GDPR + DPDP-compliant; per-tenant data export + deletion.
- Prompt injection: scrub retrieved/user content before LLM call.

## Architecture Decision Records (ADR)
- Significant change → ADR in `docs/adr/NNNN-title.md`.
- ADRs immutable after acceptance; change by writing superseding ADR.
- Significant: DB strategy, AI gateway, queue, tenancy, observability, deploy topology, agent topology, channel-adapter contracts, billing model.
- ADR states: context, decision, alternatives, consequences, date.

## Feature flags
- All risky/user-visible features ship behind a flag.
- AI behavior changes support gradual rollout (% of tenants).
- New agent workflows ship with kill-switch.
- Experimental prompts/models tenant-gated before general rollout.
- Flags have owner + expiry; stale flags removed quarterly.

## AI cost governance
- Every agent run records: prompt_tokens, completion_tokens, latency_ms, estimated_cost_inr, model, cached. Mirrored to Langfuse.
- Hard budget ceiling per tenant per period; exceed → `BudgetExceededError`.
- Soft thresholds 70/85/95% → events + UI banner.
- Expensive workflows (>500-recipient outreach, full proposal gen) require explicit UI confirmation.
- Small models for: classification, extraction, ranking. Premium for: proposals, personalized outreach, viral hooks.
- Cache hit rate is a tracked SLO.

## Queue & worker safety (Celery)
- Every task idempotent (`task_key` deterministic).
- Declares: `max_retries`, `retry_backoff`, `time_limit`, `soft_time_limit`, `acks_late=True`.
- DLQ for exhausted retries; alert on depth.
- Emits Prometheus metrics: `task_duration_seconds`, `task_outcome{status}`, `task_retries_total`.
- Long workflows checkpoint to Postgres.
- Fan-out chunks recipients; self-throttle to channel limits.
- Queue-depth circuit breaker: defer new campaigns above threshold.
- Separate queues: `ingestion`, `outreach`, `social`, `analytics`.

## Prompt engineering standards
- Prompts in `apps/api/src/corpmind/ai/prompts/` (versioned files); loaded via registry — never inlined.
- Each prompt declares: role, constraints, input schema, output schema (JSON), safety rules, examples.
- Prefer structured output (JSON mode / function calling); avoid hidden chain-of-thought in prod.
- Each prompt has: semver, regression suite (fixtures + Langfuse evals), tracked metrics, rollback.
- Promotion via feature-flag flow: shadow → % rollout → 100%.
- Prompt diffs go through code review.

## Incident response
- SEV ladder: SEV1 (data loss / cross-tenant leak / outage), SEV2 (major feature down, mass-send failure, billing broken), SEV3 (degraded UX), SEV4 (cosmetic).
- SEV1/SEV2 → page on-call, incident channel, IC assigned, status-page update within 15 min.
- Updates every 30 min (SEV1) / hourly (SEV2).
- Stop the bleeding first: kill-switch, pause queues, rotate keys — before RCA.
- Runbooks in `ops/runbooks/` per failure mode (Euri down, WA template storm, queue backlog, DB connection exhaustion, mass-send compliance flag).
- Blameless postmortem within 5 business days; architectural root cause → ADR.
- Blast-radius check in first 10 min: tenant-isolated or platform-wide?
- Customer-data incidents trigger DPDP/GDPR breach-notification workflow (legal owner, 72h clock).

## Deployment guardrails
- Trunk-based; `main` always deployable; squash-merge.
- CI gates: ruff, mypy, eslint, tsc, pytest, alembic upgrade check, OpenAPI diff, container build.
- Migrations deploy BEFORE app code that depends; every migration reversible; destructive changes two-step.
- Environments: dev → preview → staging → prod. No direct prod deploys; staging soak ≥ 1h for risky changes.
- Progressive rollout: blue/green or canary; new agent graphs / channel adapters 5% → 25% → 100% behind flag.
- Auto-rollback on SLO burn (error rate, p95, LLM fallback) within first 15 min.
- No prod deploys Fridays after 14:00 IST, weekends, or during known customer campaigns.
- Secrets never logged; secret-scanning per PR; rotation scheduled.
- Long migrations gated by maintenance flag, run via one-off worker with `lock_timeout` and `statement_timeout`.
- Every new integration ships with kill-switch flag + rollback plan.
- Pre-deploy PR template: migrations? flag? rollback? Langfuse dashboard? alerts reviewed?

## Testing rules
- Unit tests per `service.py` function.
- API tests (httpx + testcontainers) per endpoint.
- Integration tests for multi-step flows (upload → extract → discover → generate).
- AI: fixture-based assertions on shape/schema, NOT exact text match.
- Tenant-isolation regression test per new table.
- Don't mark complete without running ruff, mypy, pytest, eslint, tsc.

## Observability rules
- Structured JSON logs; request-id + tenant-id + run-id in every line.
- OTel traces span FastAPI → Celery → Euri → Qdrant.
- Langfuse for LLM traces: prompt version, model, tokens, latency, cost, eval scores.
- Prometheus: HTTP RED, queue depth, channel send rate, token spend per tenant.
- Alerts: SLA breach, error rate > 1%, fallback rate > 5%, queue backlog > 1k.

## Review checklist (before merge)
- Module boundaries respected.
- `tenant_id` propagated and filtered on every query.
- LLM calls via `EuriClient`; prompt versioned.
- Outbound messages pass through `ComplianceGuardAgent`.
- Idempotency keys handled on mutating endpoints.
- Edge cases: empty, timeouts, rate limits, partial failures.
- Structured logs + Langfuse trace for important flows.
- Tests added/updated; tenant-isolation test if new table.
- No PII in logs.
- No direct provider SDKs imported.
- Migration reversible; no destructive change without backup.
- Safe to deploy: feature-flagged if user-visible.
```

---

## Appendix F — Step-by-Step Implementation Roadmap

### Phase 0 — Foundations (Week 1)
Monorepo (`apps/api`, `apps/web`, `packages/`, `infra/`); ruff + mypy + pre-commit; ESLint + Prettier; dev compose (PG/Redis/Qdrant); CI (lint + test + migrate-check); empty FastAPI + Next.js deployed to Railway/Vercel; write `CLAUDE.MD` (from Appendix E); ADR-0001 (modular monolith), ADR-0002 (Euri as sole LLM egress).

### Phase 1 — Identity & Multi-Tenancy (Week 2)
`orgs`, `workspaces`, `users`, `memberships`, `api_keys`; signup/login/refresh; JWT; Casbin RBAC; TenantContext middleware; RLS policies; frontend auth + protected dashboard shell.

### Phase 2 — AI Plane (Week 3)
`EuriClient` with routing matrix + fallback; prompt registry (file-backed); semantic cache (Qdrant `prompt_cache`); guardrails (injection filter, PII redactor, output moderation); Langfuse integration; LangGraph runtime + `AgentState`; RootOrchestrator skeleton.

### Phase 3 — Trainer Intelligence (Week 4)
Cloudinary upload API; ingestion Celery tasks (OCR, transcription); TrainerProfileAgent extracts profile; Qdrant `trainer_profiles_{org}`; upload + profile-review UI.

### Phase 4 — HR Discovery (Week 5)
`companies`, `hr_contacts`; HRDiscoveryAgent (web.search + companies.lookup, opt-in only); semantic match trainer ↔ company; lead-list builder UI; CSV export; dedupe.

### Phase 5 — Outreach + Email Channel (Week 6)
OutreachAgent generates A/B variants; Email adapter (Postmark/SES/Resend); campaigns + recipients + messages tables; ComplianceGuard v1; campaign builder UI + approval-gate flow.

### Phase 6 — WhatsApp Channel (Week 7)
WA Business Cloud adapter (templates, sessions); opt-in tracking, 24h window; webhooks; WhatsAppAgent follow-ups; WA campaign UI; template management.

### Phase 7 — CRM, Meetings, Proposals (Week 8)
Conversation threading; pipeline Kanban; Calendly/Google Meet webhooks → meetings; ProposalAgent generates pitch deck (markdown → PDF via WeasyPrint).

### Phase 8 — Telegram + Instagram + Facebook + LinkedIn-post (Weeks 9–10)
One channel per sprint week via same `ChannelAdapter`; scheduling via Celery beat; per-channel tone tuning.

### Phase 9 — Analytics, Optimizer, Compliance v2 (Week 11)
`analytics_daily` rollups; Grafana + in-app dashboards; CampaignOptimizer nightly job; ComplianceGuard v2 (dup detection, frequency cap, classifier); HITL approval queue UI.

### Phase 10 — Billing, Limits, Polish (Week 12)
Razorpay subscriptions (₹999/₹4,999/Custom); usage counters; per-tenant budgets; white-label theming hooks; k6 load test to 1K concurrent tenants; SLO verification; security review (OWASP top-10).

### Post-MVP (Phase 11+)
- WhatsApp AI chatbot (inbound replies by agent)
- Voice outreach (Vapi/Bland integration, reuses RevenueTable AI patterns)
- DSPy nightly prompt optimization at scale
- Extract WhatsApp & Social as separate services (Stage 2 trigger)

---

### Critical Files (created in Phase 0)

- `apps/api/src/corpmind/main.py` — FastAPI app factory
- `apps/api/src/corpmind/core/config.py` — pydantic-settings
- `apps/api/src/corpmind/core/db.py` — async SQLAlchemy
- `apps/api/src/corpmind/ai/euri_client.py` — sole LLM egress
- `apps/api/alembic/env.py` — migration env
- `apps/web/app/layout.tsx` — Next.js root
- `infra/docker/compose.dev.yml` — local stack
- `.github/workflows/ci.yml` — lint/test/migrate
- `docs/adr/0001-modular-monolith.md`
- `docs/adr/0002-euri-as-sole-llm-egress.md`
- `CLAUDE.MD` (from Appendix E)

### Verification Plan

End-to-end smoke after each phase:
1. `docker compose up` → PG/Redis/Qdrant up; `make dev` → api+worker+web up.
2. Trainer flow: upload poster → extracted profile in UI within 30s.
3. HR discovery: trainer profile → ≥ 10 matching opt-in HR leads.
4. Outreach: generate + approve → emails sent → tracked in CRM.
5. Compliance: > 200-recipient campaign blocks until manual approval.
6. Observability: Langfuse shows full agent trace; Grafana shows token spend.
7. Tenant isolation: two tenants, verify queries cannot cross (automated + manual).
8. Load: k6 to 100 RPS, p95 < 400ms, error < 0.5%.

---

*Document prepared by Shyam Sundar G — AI Generalist & Automation Engineer | 2026*
*For questions: shyamgenaiengineer@gmail.com*
