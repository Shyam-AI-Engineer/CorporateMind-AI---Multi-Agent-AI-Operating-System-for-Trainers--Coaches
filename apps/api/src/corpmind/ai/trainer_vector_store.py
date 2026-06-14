"""TrainerVectorStore — index and search locked trainer profiles in Qdrant.

Design decisions (Sprint 9A):
- Single collection `trainer_profiles` shared across all tenants.
- Tenant isolation via payload filter on `tenant_id` in every search call.
  The filter is enforced server-side by Qdrant; this module never omits it.
- Embedding via Euri gateway (text-embedding-3-small, 384 dims) — no local
  ONNX/fastembed dependency, avoids Windows onnxruntime DLL issues, and keeps
  all AI calls tracked through the gateway per euri-gateway.md.
- Collection created lazily on first upsert; concurrent-creation race handled.
- Qdrant failures in lock_profile() must not prevent the DB lock from
  completing — callers catch and log but do not re-raise.

Import note:
  `qdrant_client` is imported lazily inside __init__ and each method so that
  importing this module doesn't trigger fastembed → onnxruntime at load time.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog

from corpmind.core.config import settings

log = structlog.get_logger(__name__)

_COLLECTION_NAME = "trainer_profiles"
# text-embedding-3-small with dimensions=384 (Matryoshka reduction).
# Matches the collection schema; no local ONNX runtime required.
_VECTOR_SIZE = 384
_MAX_INDEX_CHARS = 1_500  # ~512 tokens — truncate before sending to the gateway


# ── Text assembly ─────────────────────────────────────────────────────────────

def _build_text(
    niche: str | None,
    bio: str | None,
    usp: str | None,
    topics: list[str],
    target_industries: list[str],
) -> str:
    """Assemble a single indexable string from profile intelligence fields.

    Field order is intentional: niche + topics are the most discriminative
    signals for outreach matching, so they appear first and survive truncation.
    """
    parts: list[str] = []
    if niche:
        parts.append(f"Niche: {niche}")
    if topics:
        parts.append(f"Topics: {', '.join(topics)}")
    if target_industries:
        parts.append(f"Industries: {', '.join(target_industries)}")
    if bio:
        parts.append(f"Bio: {bio}")
    if usp:
        parts.append(f"USP: {usp}")
    return "\n".join(parts)[:_MAX_INDEX_CHARS]


# ── Embedding ─────────────────────────────────────────────────────────────────

async def _embed(text: str) -> list[float]:
    """Embed text via the Euri gateway (text-embedding-3-small, 384 dims).

    Routes through EuriHTTPProvider so there is no local ONNX/fastembed
    dependency — avoids the Windows onnxruntime DLL incompatibility and keeps
    all AI calls tracked through the gateway.
    """
    from corpmind.ai.providers.euri_http import EuriHTTPProvider  # noqa: PLC0415
    provider = EuriHTTPProvider()
    try:
        return await provider.embed(text, dimensions=_VECTOR_SIZE)
    finally:
        await provider.aclose()


# ── Vector store ──────────────────────────────────────────────────────────────

class TrainerVectorStore:
    """Qdrant-backed index for locked trainer profiles.

    All points land in a single ``trainer_profiles`` collection.
    Every search call is scoped by a ``tenant_id`` payload filter so that
    one tenant's profiles are never visible to another.
    """

    def __init__(self) -> None:
        from qdrant_client import AsyncQdrantClient  # noqa: PLC0415
        api_key = settings.QDRANT_API_KEY or None
        self._client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=api_key)

    async def upsert_profile(
        self,
        *,
        profile_id: uuid.UUID,
        org_id: uuid.UUID,
        workspace_id: uuid.UUID,
        niche: str | None,
        bio: str | None,
        usp: str | None,
        topics: list[str],
        target_industries: list[str],
        locked_at: datetime | None = None,
    ) -> None:
        """Embed and upsert a locked trainer profile into the vector store.

        Uses the profile UUID as the Qdrant point ID so re-locking the same
        profile is an idempotent upsert, not a duplicate insert.
        """
        from qdrant_client import models  # noqa: PLC0415

        text = _build_text(niche, bio, usp, topics, target_industries)
        if not text.strip():
            log.warning("trainer_vector_store.skip_empty_text", profile_id=str(profile_id))
            return

        await self._ensure_collection()
        vector = await _embed(text)

        await self._client.upsert(
            collection_name=_COLLECTION_NAME,
            points=[
                models.PointStruct(
                    id=str(profile_id),
                    vector=vector,
                    payload={
                        "tenant_id": str(org_id),
                        "workspace_id": str(workspace_id),
                        "profile_id": str(profile_id),
                        "niche": niche,
                        "locked_at": locked_at.isoformat() if locked_at else None,
                    },
                )
            ],
        )
        log.info(
            "trainer_vector_store.indexed",
            profile_id=str(profile_id),
            org_id=str(org_id),
            text_len=len(text),
        )

    async def search_profiles(
        self,
        query: str,
        org_id: uuid.UUID,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search over a tenant's locked profiles.

        The ``tenant_id`` payload filter is always applied — cross-tenant
        results are structurally impossible even if Qdrant is misconfigured.
        """
        from qdrant_client import models  # noqa: PLC0415

        if not query.strip():
            return []
        vector = await _embed(query)
        response = await self._client.query_points(
            collection_name=_COLLECTION_NAME,
            query=vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="tenant_id",
                        match=models.MatchValue(value=str(org_id)),
                    )
                ]
            ),
            limit=limit,
        )
        return [
            {
                "profile_id": (r.payload or {}).get("profile_id"),
                "score": r.score,
                "payload": r.payload or {},
            }
            for r in response.points
        ]

    async def aclose(self) -> None:
        """Close the underlying Qdrant HTTP client."""
        await self._client.close()

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _ensure_collection(self) -> None:
        """Create the collection if absent; handle concurrent-creation race.

        Two processes may both pass the existence check and then both call
        create_collection. The second call raises; we verify the collection
        now exists before re-raising so the race is transparent to callers.
        """
        from qdrant_client import models  # noqa: PLC0415

        response = await self._client.get_collections()
        existing = {c.name for c in response.collections}
        if _COLLECTION_NAME in existing:
            return

        try:
            await self._client.create_collection(
                collection_name=_COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=_VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )
        except Exception:
            response = await self._client.get_collections()
            if _COLLECTION_NAME not in {c.name for c in response.collections}:
                raise
