# CorporateMind AI — Documentation

This folder is the **single source of truth** for all project documentation. Markdown files here are the editable originals; the `exports/` subfolder holds generated PDFs for sharing.

---

## Core Docs

| File | Purpose | Audience |
|---|---|---|
| [PRD.md](PRD.md) | Full product requirements: vision, personas, business goals, feature specs, ROI, roadmap (34 sections + appendices) | Product, investors, stakeholders |
| [architecture.md](architecture.md) | System architecture reference: planes, module layout, agent topology, data stores, key flows, inference routing, CI/CD stages | Engineers (onboarding + day-to-day) |

> **PRD.md is the "what and why."  architecture.md is the "how it's wired."**  
> Read both before touching production code.

---

## Architecture Decision Records (ADRs)

Located in [`adr/`](adr/). Each ADR captures a significant architectural decision with context, alternatives considered, and consequences.

| ADR | Title | Status |
|---|---|---|
| [0001](adr/0001-modular-monolith.md) | Modular Monolith (Stage 1) | Accepted |
| [0002](adr/0002-euri-as-sole-llm-egress.md) | Euri as Sole LLM Egress | Accepted |
| [0003](adr/0003-postgres-rls-as-tenant-isolation-default.md) | Postgres RLS for Tenant Isolation | Accepted |
| [0004](adr/0004-redis-streams-for-event-bus.md) | Redis Streams as Event Bus (Stage 1) | Accepted |
| [0005](adr/0005-qdrant-per-tenant-collections.md) | Per-Tenant Qdrant Collections | Accepted |
| [0006](adr/0006-celery-over-kafka.md) | Celery Over Kafka (Stage 1) | Accepted |

**Rules:** ADRs are immutable after acceptance. New decisions supersede old ones — they never edit them. See [`.claude/rules/adr.md`](../.claude/rules/adr.md).

---

## Exported PDFs

Located in [`exports/`](exports/). These are generated from the markdown sources and are intended for distribution, investor decks, and offline sharing.

| PDF | Source | Description |
|---|---|---|
| [prd.pdf](exports/prd.pdf) | `docs/PRD.md` | Full product requirements document |
| [architecture.pdf](exports/architecture.pdf) | `docs/architecture.md` | System architecture reference |
| [CLAUDE.pdf](exports/CLAUDE.pdf) | `CLAUDE.md` (root) | Engineering operating manual |

**To regenerate** — see [`exports/README.md`](exports/README.md).

---

## Documentation Rules

1. **Markdown is the source of truth.** Never edit PDFs directly — they are regenerated from `.md` sources.
2. **PRD is product-owned.** Edits require a product review + version bump in the document header.
3. **architecture.md is code-coupled.** When you change the system topology (new agent, new data store, new module), update `architecture.md` in the same PR.
4. **ADRs are immutable.** Supersede, never edit. See `adr.md` rules.
5. **No "TBD" sections in committed docs.** Placeholder sections must be removed or filled before merging.

---

## Contribution Rules

- New significant architectural decisions → write a new ADR in `adr/`.
- New agent, new pillar, or new data store → update `architecture.md` (agent topology table, data stores table, ADR index).
- Breaking PRD change → bump `Version` in `PRD.md` header + summarize in a changelog comment at the top.
- After editing `PRD.md`, `architecture.md`, or `CLAUDE.md` → regenerate the corresponding PDF in `exports/`.

---

*Source of truth: these `.md` files. Questions on conventions? See [`CLAUDE.md`](../CLAUDE.md) and [`.claude/rules/`](../.claude/rules/).*
