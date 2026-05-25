# CorporateMind AI

**Autonomous AI corporate-outreach and multi-channel growth OS for trainers, coaches, consultants, and speakers.**

CorporateMind AI discovers HR decision-makers, generates hyper-personalized outreach across 6 channels, qualifies replies, and books meetings — autonomously, while the trainer sleeps.

---

## What It Does

| Capability | Description |
|---|---|
| **Trainer Intelligence** | Extracts niche, topics, tone, and pricing from uploaded content (PDF, video, poster) |
| **HR Discovery** | Finds matching companies and opted-in HR contacts from public sources |
| **AI Outreach** | Drafts per-recipient personalized messages with A/B variants at scale |
| **Multi-Channel** | Email, WhatsApp Business, Telegram, Instagram, Facebook, LinkedIn (public posts only) |
| **Compliance** | Non-bypassable ComplianceGuard: opt-in check, frequency cap, content policy, DPDP/GDPR |
| **Proposals** | AI-generated pitch decks, agendas, and pricing documents |
| **CRM + Analytics** | Lead pipeline, reply tracking, campaign optimization, cost dashboard |
| **HITL** | Human-in-the-loop approval gates for high-risk actions |

---

## Architecture at a Glance

```
Next.js 14 PWA  ──HTTPS/WSS──▶  FastAPI (async, modular monolith)
                                        │
                          ┌─────────────┴──────────────┐
                          │                            │
                   LangGraph Agents             Celery Workers
                   (14 agents, typed            (per-queue, per-tenant
                    shared state)                concurrency caps)
                          │                            │
                    Euri AI Gateway  ◀─── ALL LLM calls route here
                    (sole LLM egress)
                          │
                 PostgreSQL (RLS) │ Redis │ Qdrant │ Meilisearch
```

**The 7 Pillars (product framing):** `trainer_intel | hr_discovery | outreach | social | proposals | crm | multi_agent_runtime`

**12 technical modules (implementation):** `identity | trainer_intel | hr_discovery | outreach | social | whatsapp | proposals | crm | campaigns | analytics | billing | compliance`

Full architecture: [docs/architecture.md](docs/architecture.md)

---

## Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.12, FastAPI (async), SQLAlchemy 2, Alembic, Pydantic v2 |
| **Frontend** | Next.js 14 App Router, TypeScript, Tailwind, shadcn/ui, TanStack Query |
| **AI Runtime** | LangGraph multi-agent, Euri AI Gateway (sole LLM egress) |
| **Workers** | Celery + Redis broker + Celery Beat |
| **Databases** | PostgreSQL 16 (RLS), Redis, Qdrant, Meilisearch |
| **Observability** | Langfuse (LLM traces), OpenTelemetry, Prometheus, Grafana, Sentry |
| **Deploy** | Vercel (web) + Railway (api, workers, postgres, redis) |
| **CI/CD** | GitHub Actions — lint, test, migrate, build, canary deploy |

---

## Monorepo Layout

```
CorporateMind AI/
├── apps/
│   ├── api/          # FastAPI modular monolith + Celery workers
│   └── web/          # Next.js 14 App Router
├── packages/
│   └── shared-types/ # TypeScript types generated from OpenAPI
├── infra/
│   ├── docker/       # compose.dev.yml + Dockerfile
│   ├── grafana/      # Dashboard JSON files
│   └── scripts/      # deploy.sh, rollback.sh
├── ops/
│   ├── runbooks/     # Incident runbooks (euri-down, compliance-block, etc.)
│   └── secrets.md    # Secret owners + rotation schedule
├── docs/
│   ├── PRD.md        # Full product spec (34 sections + 6 appendices)
│   ├── architecture.md
│   ├── adr/          # Architecture Decision Records (ADR-0001 through ADR-0006+)
│   └── exports/      # PDF exports: prd.pdf, architecture.pdf, CLAUDE.pdf
├── .claude/
│   ├── rules/        # 22 domain rule files (loaded on-demand by Claude)
│   └── skills/       # 15 reusable workflow skills (slash commands)
├── CLAUDE.md         # Operating manual for engineers (human + AI)
└── README.md         # This file
```

---

## Getting Started

### Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Backend runtime |
| Node.js | 20 LTS | Frontend runtime |
| Docker + Compose | Latest | Local data services |
| `uv` | Latest | Python package management |
| `pnpm` | 9+ | Node package management |

### Environment Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd "CorporateMind AI"

# 2. Copy environment template
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
# Edit both files — fill in the required secrets (see ops/secrets.md for the inventory)

# 3. Install dependencies
cd apps/api && uv sync
cd ../web && pnpm install
cd ../..

# 4. Start local data services
docker compose -f infra/docker/compose.dev.yml up -d
# Starts: PostgreSQL, Redis, Qdrant, Meilisearch, Mailhog

# 5. Run database migrations
cd apps/api
uv run alembic upgrade head

# 6. Start development servers
# Terminal 1 — Backend:
cd apps/api && uv run uvicorn corpmind.main:app --reload --port 8000

# Terminal 2 — Celery worker:
cd apps/api && uv run celery -A corpmind.workers.celery_app worker -l info -Q agents,outreach

# Terminal 3 — Frontend:
cd apps/web && pnpm dev
```

### `make dev` (coming in Phase 0 scaffold)

```bash
make dev
# Runs all of the above in tmux panes — API, Celery, Web, and data services
```

### Verify it works

- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Frontend: [http://localhost:3000](http://localhost:3000)
- Grafana: [http://localhost:3001](http://localhost:3001)
- Mailhog: [http://localhost:8025](http://localhost:8025)

---

## Running Tests

```bash
# Backend (from apps/api/)
uv run ruff check .
uv run mypy src
uv run pytest -q

# Frontend (from apps/web/)
pnpm lint
pnpm typecheck
pnpm test
```

All CI gates must pass before a PR can merge. See `.claude/rules/testing.md` for the full test pyramid and coverage requirements.

---

## Key Documentation

| Document | Purpose |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Operating manual — rules, invariants, pre-PR checklist |
| [docs/PRD.md](docs/PRD.md) | Full product specification (investor-grade, 34 sections) |
| [docs/architecture.md](docs/architecture.md) | System wiring — planes, agents, data flows, ADR index |
| [docs/adr/](docs/adr/) | Architecture Decision Records — the "why" behind key choices |
| [docs/exports/](docs/exports/) | PDF exports of all above documents |
| [ops/runbooks/](ops/runbooks/) | Incident runbooks — what to do when things break |
| [.claude/rules/](\.claude/rules/) | 22 domain rule files — loaded by Claude Code on-demand |

---

## Governance & AI Safety

This system sends outbound messages on behalf of trainers to real HR professionals. Governance is a product requirement, not an afterthought.

**Hard invariants (P0) — never compromised:**

1. **Tenant isolation** — every business table has `tenant_id`. Postgres RLS as defense-in-depth. Cross-tenant leaks are P0 bugs (see [ADR-0003](docs/adr/0003-postgres-rls-as-tenant-isolation-default.md)).
2. **Euri-only LLM egress** — all LLM calls route through `EuriClient`. Direct provider SDK imports are mechanically blocked. (see [ADR-0002](docs/adr/0002-euri-as-sole-llm-egress.md)).
3. **ComplianceGuard before every send** — opt-in check, frequency cap, content policy, DPDP/GDPR compliance. No bypass path.
4. **No LinkedIn personal-DM automation. Ever.** Public company-page posts only.
5. **Expand-then-contract migrations** — zero-downtime schema evolution (see [ADR-0006](docs/adr/0006-expand-then-contract-migrations.md)).
6. **HMAC-verified webhooks** — replay-protected.

---

## Multi-Tenancy

Every API request carries a `tenant_id` extracted from the validated JWT. FastAPI middleware sets `SET LOCAL app.tenant_id = {tenant_id}` on the database connection. Postgres RLS blocks any query that doesn't filter by this value — even if the application code forgets.

Redis keys, Qdrant collections, Celery task headers, and object storage paths all carry tenant namespace prefixes. No cross-tenant read is possible without an explicitly audited admin override.

Full rules: [.claude/rules/multi-tenancy.md](.claude/rules/multi-tenancy.md)

---

## AI Architecture

14 specialized agents coordinate via a shared `AgentState` (TypedDict):

| Agent | Role |
|---|---|
| **RootOrchestrator** | Decomposes intent, manages global state, HITL escalator |
| **TrainerProfileAgent** | Extracts niche, topics, tone, pricing from uploads |
| **HRDiscoveryAgent** | Finds matching companies + HR contacts |
| **OutreachAgent** | Drafts per-recipient messages with A/B variants |
| **ProposalAgent** | Generates pitch decks, agendas, pricing |
| **WhatsAppAgent** | Template management, 24h window enforcement |
| **TelegramAgent** | Channel broadcasts, community nurture |
| **InstagramAgent** | Reel captions, story automation, hashtag intelligence |
| **FacebookAgent** | Page publishing, event promotion |
| **LinkedInAgent** | Public company-page posts only |
| **CampaignOptimizer** | Post-hoc analysis: segment × channel × tone performance |
| **AnalyticsAgent** | Daily rollups, insight cards, anomaly detection |
| **ComplianceGuardAgent** | Gate every outbound message |
| **LLMOpsGuardian** | Monitors quality, triggers retries, escalates to HITL |

All agents use LangGraph with checkpointed state, planner-executor split, and HITL gates (see [ADR-0004](docs/adr/0004-langgraph-for-agent-orchestration.md)).

---

## Contributing

1. **Read [CLAUDE.md](CLAUDE.md)** before writing a line of code.
2. Check the relevant `.claude/rules/` file for the area you're working in.
3. Use the `.claude/skills/` slash commands to scaffold new agents, modules, migrations, etc.
4. All PRs must pass the [Pre-PR checklist in CLAUDE.md](CLAUDE.md#pre-pr-checklist).
5. Architectural changes require an ADR in `docs/adr/`.

**Branch strategy:** trunk-based. `main` is always deployable. Short-lived feature branches. Squash-merge.

---

## Deployment

- **Web:** Vercel (auto-deploys from `main`)
- **API + Workers:** Railway (canary → 100% with auto-rollback on SLO burn)
- **Preview environments:** per-PR (Vercel + Railway)

Full pipeline: [docs/architecture.md §9](docs/architecture.md#9-operational-layers-cicd--environments) · Deploy guardrails: [.claude/rules/deployment-guardrails.md](.claude/rules/deployment-guardrails.md)

---

## License

Proprietary. All rights reserved. © 2026 CorporateMind AI.
