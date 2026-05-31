"""HTTP-layer tests for /api/v1/hr/*.

Test matrix (18 tests):

  POST /hr/contacts/import
    - success → 201, imported=1, non_contactable=0, contact_ids populated
    - missing contacts list → 422 validation
    - invalid source_type (not in enum) → 422 validation
    - raw_data too short (< 10 chars) → 422 validation
    - unauthenticated → 401

  GET /hr/contacts
    - empty list initially → 200, contacts=[], total=0
    - after import → 200, contact visible, is_contactable=True
    - pagination params honoured → limit/offset reflected
    - filter by company_id → returns only matching contacts
    - unauthenticated → 401

  GET /hr/contacts/{id}
    - success → 200, correct shape
    - random UUID not found → 404 not_found
    - unauthenticated → 401

  POST /hr/contacts/rank
    - success → 200, ranked list with score and reason
    - contact IDs not in DB → 404 not_found
    - empty contact_ids (< min_length=1) → 422 validation
    - unauthenticated → 401

  Tenant isolation
    - tenant B list → empty
    - tenant B GET specific contact → 404
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.api.conftest import make_user

# ── LLM mock payloads ─────────────────────────────────────────────────────────

_ENRICH_JSON = json.dumps({
    "full_name": "Priya Sharma",
    "title": "HR Manager",
    "title_normalized": "HR Manager",
    "email": "priya.sharma@example.com",
    "company_name": "Acme Corp",
    "preferred_language": "en",
})
_ENRICH_RESPONSE = {"content": _ENRICH_JSON}

_OPT_IN_AT = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat()

_CONTACT_PAYLOAD: dict = {
    "raw_data": "Priya Sharma is the HR Manager at Acme Corp who attended our webinar.",
    "source": "https://webinar.example.com/2025-01-15",
    "source_type": "webinar_registration",
    "opted_in_at": _OPT_IN_AT,
    "opt_in_evidence": "webinar-reg-12345",
    "company_name": "Acme Corp",
    "company_industry": "IT",
    "company_city": "Bangalore",
    "company_country": "India",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _import_contacts(
    client: AsyncClient,
    token: str,
    *,
    contacts: list[dict] | None = None,
) -> dict:
    """POST /hr/contacts/import with a mocked LLM enrichment call."""
    payload = contacts if contacts is not None else [_CONTACT_PAYLOAD]
    with patch(
        "corpmind.ai.euri_client.EuriClient.chat",
        new_callable=AsyncMock,
        return_value=_ENRICH_RESPONSE,
    ):
        resp = await client.post(
            "/api/v1/hr/contacts/import",
            json={"contacts": payload},
            headers=_auth(token),
        )
    assert resp.status_code == 201, f"_import_contacts failed: {resp.text}"
    return resp.json()


# ── POST /contacts/import ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_import_contacts_returns_201(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    result = await _import_contacts(api_client, user["tokens"]["access_token"])

    assert result["imported"] == 1
    assert result["non_contactable"] == 0
    assert result["failed"] == 0
    assert len(result["contact_ids"]) == 1


@pytest.mark.asyncio
async def test_import_contacts_missing_body_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.post(
        "/api/v1/hr/contacts/import",
        json={},
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_import_invalid_source_type_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    bad_contact = {**_CONTACT_PAYLOAD, "source_type": "linkedin_scrape"}
    resp = await api_client.post(
        "/api/v1/hr/contacts/import",
        json={"contacts": [bad_contact]},
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_import_short_raw_data_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    bad_contact = {**_CONTACT_PAYLOAD, "raw_data": "Too short"}  # < 10 chars
    resp = await api_client.post(
        "/api/v1/hr/contacts/import",
        json={"contacts": [bad_contact]},
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_import_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/hr/contacts/import",
        json={"contacts": [_CONTACT_PAYLOAD]},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── GET /contacts ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_contacts_empty_initially(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.get(
        "/api/v1/hr/contacts",
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["contacts"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_list_contacts_after_import(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    await _import_contacts(api_client, token)

    resp = await api_client.get("/api/v1/hr/contacts", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["contacts"]) == 1
    contact = body["contacts"][0]
    assert "id" in contact
    assert "full_name" in contact
    assert contact["is_contactable"] is True


@pytest.mark.asyncio
async def test_list_contacts_pagination_params_reflected(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    await _import_contacts(api_client, token)

    resp = await api_client.get(
        "/api/v1/hr/contacts",
        params={"limit": 10, "offset": 0},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 10
    assert body["offset"] == 0


@pytest.mark.asyncio
async def test_list_contacts_filter_by_company_id(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    imported = await _import_contacts(api_client, token)

    # Resolve the company_id for the imported contact
    contact_id = imported["contact_ids"][0]
    contact_resp = await api_client.get(
        f"/api/v1/hr/contacts/{contact_id}",
        headers=_auth(token),
    )
    company_id = contact_resp.json()["company_id"]

    resp = await api_client.get(
        "/api/v1/hr/contacts",
        params={"company_id": company_id},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["contacts"][0]["company_id"] == company_id


@pytest.mark.asyncio
async def test_list_contacts_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/hr/contacts")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── GET /contacts/{id} ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_contact_returns_200(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    imported = await _import_contacts(api_client, token)

    contact_id = imported["contact_ids"][0]
    resp = await api_client.get(
        f"/api/v1/hr/contacts/{contact_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == contact_id
    assert "full_name" in body
    assert "company_id" in body
    assert isinstance(body["is_contactable"], bool)
    assert "created_at" in body


@pytest.mark.asyncio
async def test_get_contact_not_found_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.get(
        f"/api/v1/hr/contacts/{uuid.uuid4()}",
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_get_contact_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get(f"/api/v1/hr/contacts/{uuid.uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── POST /contacts/rank ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rank_contacts_returns_200(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    imported = await _import_contacts(api_client, token)

    contact_id = imported["contact_ids"][0]
    rank_json = json.dumps([
        {
            "contact_id": contact_id,
            "score": 8,
            "reason": "Strong fit for leadership training programmes.",
        }
    ])

    with patch(
        "corpmind.ai.euri_client.EuriClient.chat",
        new_callable=AsyncMock,
        return_value={"content": rank_json},
    ):
        resp = await api_client.post(
            "/api/v1/hr/contacts/rank",
            json={
                "contact_ids": [contact_id],
                "trainer_niche": "Leadership Training",
                "trainer_topics": ["Leadership", "Team Building"],
                "trainer_target_industries": ["IT", "Finance"],
            },
            headers=_auth(token),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "ranked" in body
    assert len(body["ranked"]) == 1
    ranked_item = body["ranked"][0]
    assert ranked_item["contact_id"] == contact_id
    assert 1 <= ranked_item["score"] <= 10
    assert "reason" in ranked_item
    assert "contact" in ranked_item


@pytest.mark.asyncio
async def test_rank_contacts_unknown_ids_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.post(
        "/api/v1/hr/contacts/rank",
        json={
            "contact_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
            "trainer_niche": "Leadership Training",
            "trainer_topics": ["Leadership"],
            "trainer_target_industries": ["IT"],
        },
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_rank_contacts_empty_ids_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.post(
        "/api/v1/hr/contacts/rank",
        json={
            "contact_ids": [],  # min_length=1 → 422
            "trainer_niche": "Leadership Training",
            "trainer_topics": ["Leadership"],
            "trainer_target_industries": ["IT"],
        },
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_rank_contacts_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/hr/contacts/rank",
        json={
            "contact_ids": [str(uuid.uuid4())],
            "trainer_niche": "Training",
            "trainer_topics": ["Topic"],
            "trainer_target_industries": ["IT"],
        },
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── Tenant isolation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation_contact_invisible_to_other_tenant(
    api_client: AsyncClient,
) -> None:
    user_a = await make_user(api_client)
    user_b = await make_user(api_client)

    imported = await _import_contacts(api_client, user_a["tokens"]["access_token"])
    contact_id = imported["contact_ids"][0]

    # Tenant B's list must be empty
    list_resp = await api_client.get(
        "/api/v1/hr/contacts",
        headers=_auth(user_b["tokens"]["access_token"]),
    )
    assert list_resp.json()["total"] == 0

    # Tenant B cannot fetch tenant A's contact by ID
    get_resp = await api_client.get(
        f"/api/v1/hr/contacts/{contact_id}",
        headers=_auth(user_b["tokens"]["access_token"]),
    )
    assert get_resp.status_code == 404
