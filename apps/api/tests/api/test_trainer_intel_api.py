"""HTTP-layer tests for /api/v1/trainer/*.

Test matrix (21 tests):

  POST /trainer/extract
    - success → 201, full profile shape, niche/topics populated from LLM mock
    - content too short (< 20 chars) → 422 validation
    - missing body → 422 validation
    - locked profile → 409 conflict
    - unauthenticated → 401

  GET /trainer/profile
    - no profile yet → 404 not_found
    - after extract → 200, correct profile shape
    - unauthenticated → 401

  PATCH /trainer/profile
    - success → 200, updated fields reflected
    - no profile → 404 not_found
    - locked profile → 409 conflict
    - unauthenticated → 401

  POST /trainer/profile/lock
    - success → 200, is_locked=True
    - missing niche/bio/topics → 422 validation_error
    - already locked → 409 conflict
    - no profile → 404 not_found
    - unauthenticated → 401

  POST /trainer/upload
    - success → 202, task_id returned, status=queued
    - invalid file_type → 422 validation
    - unauthenticated → 401

  Tenant isolation
    - tenant B cannot read tenant A's profile → 404
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import AsyncClient

from tests.api.conftest import make_user

# ── LLM mock payloads ─────────────────────────────────────────────────────────

_FULL_EXTRACT_JSON = json.dumps({
    "niche": "Leadership Training",
    "topics": ["Leadership", "Team Building"],
    "bio": "Expert leadership trainer with ten years of industry experience.",
    "tone": "professional",
    "target_industries": ["IT", "Finance"],
    "languages": ["English", "Hindi"],
})

_EMPTY_EXTRACT_JSON = json.dumps({})

_FULL_EXTRACT_RESPONSE = {"content": _FULL_EXTRACT_JSON}
_EMPTY_EXTRACT_RESPONSE = {"content": _EMPTY_EXTRACT_JSON}

_VALID_CONTENT = "I am a leadership trainer with ten years of corporate training experience."


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _extract_profile(
    client: AsyncClient,
    token: str,
    *,
    llm_response: dict | None = None,
    content: str = _VALID_CONTENT,
) -> dict:
    """POST /trainer/extract with a mocked LLM and return the parsed body."""
    mock_response = llm_response if llm_response is not None else _FULL_EXTRACT_RESPONSE
    with patch(
        "corpmind.ai.euri_client.EuriClient.chat",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        resp = await client.post(
            "/api/v1/trainer/extract",
            json={"content": content},
            headers=_auth(token),
        )
    assert resp.status_code == 201, f"_extract_profile failed: {resp.text}"
    return resp.json()


async def _lock_profile(client: AsyncClient, token: str) -> dict:
    resp = await client.post("/api/v1/trainer/profile/lock", headers=_auth(token))
    assert resp.status_code == 200, f"_lock_profile failed: {resp.text}"
    return resp.json()


# ── POST /extract ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_profile_returns_201(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    profile = await _extract_profile(api_client, user["tokens"]["access_token"])

    assert "id" in profile
    assert "workspace_id" in profile
    assert profile["niche"] == "Leadership Training"
    assert "Leadership" in profile["topics"]
    assert profile["is_locked"] is False
    assert profile["bio"] is not None


@pytest.mark.asyncio
async def test_extract_short_content_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.post(
        "/api/v1/trainer/extract",
        json={"content": "Too short"},  # < 20 chars
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_extract_missing_body_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.post(
        "/api/v1/trainer/extract",
        json={},
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_extract_locked_profile_returns_409(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    await _extract_profile(api_client, token)
    await _lock_profile(api_client, token)

    with patch(
        "corpmind.ai.euri_client.EuriClient.chat",
        new_callable=AsyncMock,
        return_value=_FULL_EXTRACT_RESPONSE,
    ):
        resp = await api_client.post(
            "/api/v1/trainer/extract",
            json={"content": _VALID_CONTENT},
            headers=_auth(token),
        )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_extract_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/trainer/extract",
        json={"content": _VALID_CONTENT},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── GET /profile ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_profile_no_profile_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.get(
        "/api/v1/trainer/profile",
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_get_profile_returns_200_after_extract(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    await _extract_profile(api_client, token)

    resp = await api_client.get("/api/v1/trainer/profile", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert "workspace_id" in body
    assert isinstance(body["topics"], list)
    assert isinstance(body["is_locked"], bool)
    assert "created_at" in body


@pytest.mark.asyncio
async def test_get_profile_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/trainer/profile")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── PATCH /profile ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_profile_returns_200(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    await _extract_profile(api_client, token)

    resp = await api_client.patch(
        "/api/v1/trainer/profile",
        json={"niche": "Sales Training", "pricing_min_inr": 50000},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["niche"] == "Sales Training"
    assert body["pricing_min_inr"] == 50000


@pytest.mark.asyncio
async def test_update_profile_no_profile_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.patch(
        "/api/v1/trainer/profile",
        json={"niche": "Sales Training"},
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_update_locked_profile_returns_409(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    await _extract_profile(api_client, token)
    await _lock_profile(api_client, token)

    resp = await api_client.patch(
        "/api/v1/trainer/profile",
        json={"niche": "Sales Training"},
        headers=_auth(token),
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_update_profile_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.patch("/api/v1/trainer/profile", json={"niche": "X"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── POST /profile/lock ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lock_profile_returns_200_and_is_locked(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    await _extract_profile(api_client, token)

    resp = await api_client.post("/api/v1/trainer/profile/lock", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["is_locked"] is True


@pytest.mark.asyncio
async def test_lock_profile_missing_fields_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    # Empty LLM JSON → no niche, no bio, no topics → lock rejects with 422
    await _extract_profile(api_client, token, llm_response=_EMPTY_EXTRACT_RESPONSE)

    resp = await api_client.post("/api/v1/trainer/profile/lock", headers=_auth(token))
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_lock_already_locked_profile_returns_409(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    await _extract_profile(api_client, token)
    await _lock_profile(api_client, token)

    resp = await api_client.post("/api/v1/trainer/profile/lock", headers=_auth(token))
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_lock_no_profile_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.post(
        "/api/v1/trainer/profile/lock",
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_lock_profile_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post("/api/v1/trainer/profile/lock")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── POST /upload ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_enqueues_task_returns_202(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    fake_task = Mock()
    fake_task.id = "celery-test-task-abc123"

    with patch("corpmind.workers.tasks.ingestion.ingest_trainer_upload") as mock_ingest:
        mock_ingest.apply_async.return_value = fake_task
        resp = await api_client.post(
            "/api/v1/trainer/upload",
            json={
                "cloudinary_url": "https://res.cloudinary.com/demo/raw/upload/sample.pdf",
                "file_type": "pdf",
            },
            headers=_auth(token),
        )

    assert resp.status_code == 202
    body = resp.json()
    assert body["task_id"] == "celery-test-task-abc123"
    assert body["status"] == "queued"


@pytest.mark.asyncio
async def test_upload_invalid_file_type_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.post(
        "/api/v1/trainer/upload",
        json={
            "cloudinary_url": "https://res.cloudinary.com/demo/raw/upload/doc.docx",
            "file_type": "docx",  # not in pattern ^(pdf|image|video)$
        },
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_upload_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/trainer/upload",
        json={
            "cloudinary_url": "https://res.cloudinary.com/demo/raw/upload/sample.pdf",
            "file_type": "pdf",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── Tenant isolation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation_profile_invisible_to_other_tenant(api_client: AsyncClient) -> None:
    user_a = await make_user(api_client)
    user_b = await make_user(api_client)

    await _extract_profile(api_client, user_a["tokens"]["access_token"])

    resp = await api_client.get(
        "/api/v1/trainer/profile",
        headers=_auth(user_b["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"
