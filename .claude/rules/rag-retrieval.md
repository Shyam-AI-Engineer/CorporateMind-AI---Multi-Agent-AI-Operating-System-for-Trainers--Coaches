# RAG / Retrieval Rules

CorporateMind AI's retrieval surfaces:
- **Trainer profiles** — semantic similarity for HR matching.
- **HR/company context** — recent public news, industry, prior conversation history.
- **Campaign outcomes** — RLHF signal: "what worked for trainers like this with HRs like that".
- **Prompt cache** — semantic dedupe of deterministic LLM calls.

## Separation of concerns
Each stage is its own module — never collapsed into a route or service file:
```
ingestion  → chunking  → embedding  → retrieval  → generation
```
- **Ingestion** lives in `apps/api/src/corpmind/ingestion/` (OCR, transcription, parsing).
- **Embedding** uses bge-small via local sentence-transformers; bge-reranker-base for rerank.
- **Retrieval** is hybrid: Qdrant ANN top-50 + Meilisearch BM25 top-50 → RRF fusion → cross-encoder rerank → top-k (default 8).
- **Generation** is the LLM call, always via `EuriClient` (see `euri-gateway.md`).

## Chunking
- Chunk size and overlap configurable per source type:
  - Poster/PDF: 512 tokens, 64 overlap.
  - Video transcript: 800 tokens, 100 overlap, paragraph-boundary aware.
  - Brochure: 1024 tokens, 128 overlap.
- Override via source-type config; never hardcode in business logic.

## Tenant isolation
- Per-tenant Qdrant collections: `trainer_profiles_{org_id}`, `companies_{org_id}`, `hr_contacts_{org_id}`, `campaign_outcomes_{org_id}`.
- The global `prompt_cache_global` collection contains NO PII — Presidio-redacted before hash.

## Quality
- Source attribution returned with every retrieval result (`{id, score, source, source_type}`).
- Log low-confidence retrievals (top-1 score < 0.55) and fallback conditions.
- Cache-aware: identical retrieval queries within a workflow run hit Redis-side memo.

## Memory budget
- Memory-injected tokens budgeted per agent run (default 2,400 tokens).
- Truncation order if over budget: oldest episodic → lowest-scored semantic → lowest-scored conversational.

## Pruning & TTL
- Trainer profile vectors: re-embed on profile lock + quarterly refresh.
- HR contact vectors: 12-month rolling window; stale flag at 6 months.
- Campaign outcome vectors: retain indefinitely (this is the RLHF moat).
- Prompt cache: LFU eviction with 30-day TTL hard ceiling.

## Forbidden
- Mixing retrieval into route files.
- Cross-tenant retrieval (the search filter MUST include `tenant_id`).
- Caching personalized outreach copy — defeats personalization.
