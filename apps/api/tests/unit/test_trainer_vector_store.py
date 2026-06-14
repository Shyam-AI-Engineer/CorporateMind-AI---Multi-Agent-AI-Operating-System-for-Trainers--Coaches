"""Unit tests for TrainerVectorStore.

All Qdrant client calls and the fastembed model are mocked — no live Qdrant
or model download required.

Key pattern:
  TrainerVectorStore.__new__(TrainerVectorStore) bypasses __init__ so that
  qdrant_client is never imported (importing it triggers fastembed →
  onnxruntime, which raises a non-fatal Windows access violation during
  test collection).  The mock client is wired in via store._client directly.

Tests cover:
  _build_text
    - field ordering (niche/topics first so they survive truncation)
    - empty fields omitted
    - truncation at MAX_INDEX_CHARS
    - topics joined with comma

  upsert_profile
    - calls _embed and client.upsert with the correct payload shape
    - uses profile UUID as the Qdrant point ID (idempotent re-lock)
    - skips upsert when all fields are empty (no embed call)
    - locked_at serialised into payload when provided
    - locked_at is None in payload when not provided

  _ensure_collection
    - skips create_collection when collection already exists
    - creates collection with correct vector size / distance when missing
    - handles concurrent-creation race gracefully
    - re-raises when create fails AND the collection is still absent

  search_profiles
    - always injects tenant_id FieldCondition in the must filter
    - returns empty list and skips embed for blank query
    - maps query_points result fields to the expected dict shape
    - filter value is scoped to the requesting org, not any other
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.ai.trainer_vector_store import TrainerVectorStore, _build_text


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_vector() -> list[float]:
    return [0.01] * 384


def _mock_client(*, collection_exists: bool = True) -> MagicMock:
    """Return a fully async-mocked Qdrant client.

    When collection_exists=True, get_collections() returns a response that
    already contains the trainer_profiles collection.
    """
    client = MagicMock()
    client.get_collections = AsyncMock()
    client.create_collection = AsyncMock()
    client.upsert = AsyncMock()
    client.query_points = AsyncMock()
    client.close = AsyncMock()

    coll = MagicMock()
    coll.name = "trainer_profiles"
    resp = MagicMock()
    resp.collections = [coll] if collection_exists else []
    client.get_collections.return_value = resp

    return client


def _make_store(client: MagicMock | None = None) -> TrainerVectorStore:
    """Create a TrainerVectorStore instance without importing qdrant_client.

    TrainerVectorStore.__new__ skips __init__, so qdrant_client is never
    imported — no onnxruntime crash during test collection.
    """
    store = TrainerVectorStore.__new__(TrainerVectorStore)
    store._client = client or _mock_client()
    return store


# ── _build_text ───────────────────────────────────────────────────────────────

class TestBuildText:
    def test_niche_is_first_line(self) -> None:
        text = _build_text("Leadership coaching", "Long bio text", None, [], [])
        assert text.startswith("Niche: Leadership coaching")

    def test_topics_precede_bio(self) -> None:
        text = _build_text("Niche", "Bio text", None, ["T1", "T2"], [])
        lines = text.split("\n")
        topics_idx = next(i for i, ln in enumerate(lines) if "Topics:" in ln)
        bio_idx = next(i for i, ln in enumerate(lines) if "Bio:" in ln)
        assert topics_idx < bio_idx

    def test_empty_fields_produce_empty_string(self) -> None:
        assert _build_text(None, None, None, [], []) == ""

    def test_truncated_to_max_chars(self) -> None:
        long_bio = "y" * 3_000
        text = _build_text("Niche", long_bio, None, [], [])
        assert len(text) <= 1_500

    def test_niche_survives_long_bio_truncation(self) -> None:
        long_bio = "y" * 3_000
        text = _build_text("Leadership coaching", long_bio, None, [], [])
        assert "Leadership coaching" in text

    def test_topics_joined_with_comma(self) -> None:
        text = _build_text(None, None, None, ["A", "B", "C"], [])
        assert "A, B, C" in text

    def test_usp_appears_last(self) -> None:
        text = _build_text("Niche", "Bio text", "My unique angle", [], [])
        assert text.endswith("My unique angle")

    def test_industries_included_when_present(self) -> None:
        text = _build_text(None, None, None, [], ["BFSI", "Pharma"])
        assert "BFSI" in text
        assert "Pharma" in text


# ── upsert_profile ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_calls_embed_and_upsert() -> None:
    client = _mock_client()
    store = _make_store(client)
    profile_id = uuid.uuid4()
    org_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    mock_embed = AsyncMock(return_value=_fake_vector())

    with patch("corpmind.ai.trainer_vector_store._embed", mock_embed):
        await store.upsert_profile(
            profile_id=profile_id,
            org_id=org_id,
            workspace_id=ws_id,
            niche="Leadership coaching",
            bio="15 years in BFSI coaching",
            usp="Behavioural science + finance",
            topics=["Executive Presence"],
            target_industries=["BFSI"],
        )

    mock_embed.assert_awaited_once()
    client.upsert.assert_awaited_once()

    call_kw = client.upsert.await_args.kwargs
    assert call_kw["collection_name"] == "trainer_profiles"
    point = call_kw["points"][0]
    assert point.id == str(profile_id)
    assert point.vector == _fake_vector()
    assert point.payload["tenant_id"] == str(org_id)
    assert point.payload["workspace_id"] == str(ws_id)
    assert point.payload["profile_id"] == str(profile_id)
    assert point.payload["niche"] == "Leadership coaching"


@pytest.mark.asyncio
async def test_upsert_skips_when_all_fields_empty() -> None:
    """If there is nothing meaningful to index, skip the embed + upsert calls."""
    client = _mock_client()
    store = _make_store(client)
    mock_embed = AsyncMock(return_value=_fake_vector())

    with patch("corpmind.ai.trainer_vector_store._embed", mock_embed):
        await store.upsert_profile(
            profile_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            niche=None,
            bio=None,
            usp=None,
            topics=[],
            target_industries=[],
        )

    mock_embed.assert_not_awaited()
    client.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_locked_at_serialised_in_payload() -> None:
    client = _mock_client()
    store = _make_store(client)
    locked_at = datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC)

    with patch("corpmind.ai.trainer_vector_store._embed", AsyncMock(return_value=_fake_vector())):
        await store.upsert_profile(
            profile_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            niche="Sales training",
            bio=None,
            usp=None,
            topics=[],
            target_industries=[],
            locked_at=locked_at,
        )

    point = client.upsert.await_args.kwargs["points"][0]
    assert "2026-06-12" in point.payload["locked_at"]


@pytest.mark.asyncio
async def test_upsert_locked_at_none_when_not_provided() -> None:
    client = _mock_client()
    store = _make_store(client)

    with patch("corpmind.ai.trainer_vector_store._embed", AsyncMock(return_value=_fake_vector())):
        await store.upsert_profile(
            profile_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            niche="Sales training",
            bio=None,
            usp=None,
            topics=[],
            target_industries=[],
        )

    point = client.upsert.await_args.kwargs["points"][0]
    assert point.payload["locked_at"] is None


# ── _ensure_collection ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_collection_skips_create_when_already_exists() -> None:
    client = _mock_client(collection_exists=True)
    store = _make_store(client)
    await store._ensure_collection()
    client.create_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_collection_creates_with_correct_params() -> None:
    client = _mock_client(collection_exists=False)
    store = _make_store(client)
    await store._ensure_collection()

    client.create_collection.assert_awaited_once()
    call_kw = client.create_collection.await_args.kwargs
    assert call_kw["collection_name"] == "trainer_profiles"
    assert call_kw["vectors_config"].size == 384


@pytest.mark.asyncio
async def test_ensure_collection_handles_concurrent_creation_race() -> None:
    """create_collection raises because another process won the race.

    The second get_collections call shows the collection now exists — no error.
    """
    client = _mock_client(collection_exists=False)
    client.create_collection = AsyncMock(side_effect=Exception("already exists"))

    coll = MagicMock()
    coll.name = "trainer_profiles"
    exists_resp = MagicMock()
    exists_resp.collections = [coll]

    empty_resp = client.get_collections.return_value  # has empty collections
    client.get_collections = AsyncMock(side_effect=[empty_resp, exists_resp])

    store = _make_store(client)
    await store._ensure_collection()  # must not raise


@pytest.mark.asyncio
async def test_ensure_collection_reraises_on_genuine_create_error() -> None:
    """create_collection raises AND the collection still does not exist → re-raise."""
    client = _mock_client(collection_exists=False)
    client.create_collection = AsyncMock(side_effect=Exception("Qdrant connection refused"))

    store = _make_store(client)
    with pytest.raises(Exception, match="connection refused"):
        await store._ensure_collection()


# ── search_profiles ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_always_injects_tenant_id_filter() -> None:
    """The tenant_id must filter must be present in every query_points call."""
    client = _mock_client()
    org_id = uuid.uuid4()

    hit = MagicMock()
    hit.score = 0.92
    hit.payload = {"tenant_id": str(org_id), "profile_id": str(uuid.uuid4()), "niche": "Sales"}
    response = MagicMock()
    response.points = [hit]
    client.query_points.return_value = response

    store = _make_store(client)
    with patch("corpmind.ai.trainer_vector_store._embed", AsyncMock(return_value=_fake_vector())):
        results = await store.search_profiles("leadership trainer BFSI", org_id=org_id)

    client.query_points.assert_awaited_once()
    call_kw = client.query_points.await_args.kwargs
    must_conditions = call_kw["query_filter"].must
    assert len(must_conditions) == 1
    assert must_conditions[0].key == "tenant_id"
    assert must_conditions[0].match.value == str(org_id)

    assert len(results) == 1
    assert results[0]["score"] == 0.92
    assert results[0]["profile_id"] == hit.payload["profile_id"]


@pytest.mark.asyncio
async def test_search_returns_empty_list_for_blank_query() -> None:
    client = _mock_client()
    store = _make_store(client)
    mock_embed = AsyncMock(return_value=_fake_vector())

    with patch("corpmind.ai.trainer_vector_store._embed", mock_embed):
        results = await store.search_profiles("   ", org_id=uuid.uuid4())

    assert results == []
    mock_embed.assert_not_awaited()
    client.query_points.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_filter_scoped_to_requesting_org() -> None:
    """Filter value must match the calling org, not any other org."""
    client = _mock_client()
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    response = MagicMock()
    response.points = []
    client.query_points.return_value = response

    store = _make_store(client)
    with patch("corpmind.ai.trainer_vector_store._embed", AsyncMock(return_value=_fake_vector())):
        await store.search_profiles("coaching", org_id=org_a)

    call_kw = client.query_points.await_args.kwargs
    filter_value = call_kw["query_filter"].must[0].match.value
    assert filter_value == str(org_a)
    assert filter_value != str(org_b)
