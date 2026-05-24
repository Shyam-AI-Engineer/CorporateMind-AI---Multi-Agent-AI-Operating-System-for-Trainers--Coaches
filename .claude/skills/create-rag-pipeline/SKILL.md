---
name: create-rag-pipeline
description: Scaffold a new retrieval pipeline (ingestion → chunking → embedding → hybrid retrieval → rerank → generation) for a new source type
---

# Create RAG Pipeline Skill

## Goal
Add a new retrieval pipeline for a new source type (e.g., trainer transcripts, HR company profiles, prior outreach history). Each stage is separated; never collapsed into a route or service.

## Steps
1. **Ask for:**
   - Source type name (e.g., `trainer_brochure`, `competitor_review`).
   - Input format (PDF / image / audio / video / URL / text).
   - Tenancy (per-org, per-workspace, global PII-free).
   - Expected retrieval use cases.
2. **Add ingestion** in `apps/api/src/corpmind/ingestion/<source>.py`:
   - Parser (OCR via Tesseract → Google Vision fallback; transcription via Whisper).
   - Idempotent Celery task (key = `ingest:{source}:{file_hash}`).
   - Emits `ingest.<source>.completed` event with extracted text reference.
3. **Add chunking config** in `apps/api/src/corpmind/ingestion/chunking.py`:
   - Source-type-specific chunk size + overlap (defaults: PDF 512/64, transcript 800/100).
   - Paragraph-boundary aware where applicable.
   - Override via DB config table; never hardcoded.
4. **Add embedding step:**
   - bge-small via local sentence-transformers (default).
   - Batch in groups of 32; cache by content hash to avoid re-embedding identical chunks.
5. **Add Qdrant collection:**
   - Per-tenant: `<source>_<scope>` (e.g., `trainer_brochures_{org_id}`).
   - Payload: `{tenant_id, source_id, chunk_idx, source_type, ingested_at}`.
   - Schema and index params documented in `apps/api/src/corpmind/core/qdrant.py`.
6. **Add retrieval helper:**
   - Hybrid: Qdrant ANN top-50 + Meilisearch BM25 top-50 → RRF fusion → cross-encoder rerank (bge-reranker-base) → top-k (default 8).
   - Return `[{chunk, score, source_id, source_type}, ...]` with provenance.
7. **Wire generation:** caller composes the prompt via the prompt registry; injects retrieved chunks as context with provenance IDs. Caller still goes through `EuriClient`.
8. **Add pruning policy** to `apps/api/src/corpmind/ingestion/lifecycle.py`:
   - TTL or rolling window per source type.
   - Re-embed schedule (e.g., quarterly for trainer profiles).
9. **Tests:**
   - End-to-end fixture: ingest → chunk → embed → search → expected top-1.
   - Tenancy: ingested into tenant A, search as tenant B returns zero results.
   - Cache: re-ingest identical file → no new embeddings, same vector IDs.

## Quality rules
- Stages are separate modules. NEVER mix retrieval into a route or service file.
- Chunk size/overlap configurable per source — no inline constants.
- Source attribution on every result (`{id, score, source, source_type}`).
- Log low-confidence retrievals (top-1 < 0.55).
- Tenant filter included on every Qdrant search.
- Global collections (e.g., `prompt_cache_global`) MUST be PII-redacted before insertion.
- Cache-aware: identical retrieval within a workflow hits Redis memo.

## References
- `.claude/rules/rag-retrieval.md`
- `.claude/rules/euri-gateway.md`
- `.claude/rules/multi-tenancy.md`
