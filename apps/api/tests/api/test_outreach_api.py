"""HTTP-layer tests for /api/v1/outreach/*.

Test matrix (16 tests):

  POST /outreach/generate
    - success → 201, full OutboundMessageOut shape, status=draft
    - unsupported channel (whatsapp — valid schema, fails service) → 422
    - invalid channel pattern (fax — fails Pydantic regex) → 422
    - unknown contact_id → 404
    - non-contactable contact → 422 (ComplianceBlockError)
    - unauthenticated → 401

  POST /outreach/{id}/send
    - success → 200, status=queued (Celery mocked)
    - unknown message_id → 404
    - already queued → 409 conflict
    - compliance blocked after draft creation → 200, status=blocked with reason
    - unauthenticated → 401

  GET /outreach/{id}
    - success → 200, OutboundMessageOut shape
    - not found → 404
    - unauthenticated → 401

  Tenant isolation
    - tenant B cannot read tenant A's message → 404

NOTE: OutreachService._fetch_contact uses raw SQL against hr_contacts; contacts
must be seeded via NullPool (same pattern as test_campaigns_api.py) rather than
the HR import API, which would add an extra LLM mock layer and slower setup.
"""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from tests.api.conftest import make_user

# ── LLM copy mock ─────────────────────────────────────────────────────────────

_COPY_JSON = json.dumps({
    "subject": "Leadership Training for Your Team",
    "body": (
        "Dear Priya, I hope this message finds you well. "
        "I would love to share how my leadership training programme "
        "could benefit your team at Acme Corp."
    ),
})
_COPY_RESPONSE = {"content": _COPY_JSON}

_VALID_CONTENT = (
    "I am a leadership trainer with ten years of corporate training experience."
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _claims(token: str) -> dict:
    """Decode JWT payload without signature verification."""
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


async def _seed_contact(
    engine: AsyncEngine,
    tenant_id: str,
    *,
    is_contactable: bool = True,
    email: str | None = "seed@example.com",
) -> str:
    """Insert an hr_contacts row with a NullPool connection and return its UUID.

    NullPool guarantees a fresh postgres-superuser connection that has never
    had SET ROLE corpmind_test applied, so the insert is not restricted by RLS.
    """
    contact_id = str(uuid.uuid4())
    seed = create_async_engine(
        engine.url.render_as_string(hide_password=False), poolclass=NullPool
    )
    try:
        async with seed.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO hr_contacts"
                    " (id, tenant_id, company_id, full_name, email, source, source_type,"
                    "  email_deliverable, is_contactable)"
                    " VALUES (:id, :tid, :cid, 'Priya Sharma', :email, 'test',"
                    "         'webinar_registration', TRUE, :contactable)"
                ),
                {
                    "id": contact_id,
                    "tid": tenant_id,
                    "cid": str(uuid.uuid4()),
                    "email": email,
                    "contactable": is_contactable,
                },
            )
    finally:
        await seed.dispose()
    return contact_id


async def _revoke_opt_in(engine: AsyncEngine, contact_id: str) -> None:
    """Flip is_contactable=FALSE on an existing contact via NullPool."""
    seed = create_async_engine(
        engine.url.render_as_string(hide_password=False), poolclass=NullPool
    )
    try:
        async with seed.begin() as conn:
            await conn.execute(
                text("UPDATE hr_contacts SET is_contactable = FALSE WHERE id = :id"),
                {"id": contact_id},
            )
    finally:
        await seed.dispose()


async def _generate_draft(
    client: AsyncClient,
    token: str,
    contact_id: str,
    *,
    channel: str = "email",
) -> dict:
    """POST /outreach/generate with mocked LLM; asserts 201 and returns body."""
    with patch(
        "corpmind.ai.euri_client.EuriClient.chat",
        new_callable=AsyncMock,
        return_value=_COPY_RESPONSE,
    ):
        resp = await client.post(
            "/api/v1/outreach/generate",
            json={"contact_id": contact_id, "channel": channel},
            headers=_auth(token),
        )
    assert resp.status_code == 201, f"_generate_draft failed: {resp.text}"
    return resp.json()


# ── POST /generate ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_returns_201(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    contact_id = await _seed_contact(db_engine, claims["org_id"])
    draft = await _generate_draft(api_client, token, contact_id)

    assert "id" in draft
    assert draft["contact_id"] == contact_id
    assert draft["channel"] == "email"
    assert draft["status"] == "draft"
    assert draft["body"] != ""
    assert draft["subject"] is not None
    assert "created_at" in draft
    assert draft["sent_at"] is None


@pytest.mark.asyncio
async def test_generate_unsupported_channel_returns_422(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """whatsapp passes the Pydantic pattern but is not in _SUPPORTED_CHANNELS → 422."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)
    contact_id = await _seed_contact(db_engine, claims["org_id"])

    resp = await api_client.post(
        "/api/v1/outreach/generate",
        json={"contact_id": contact_id, "channel": "whatsapp"},
        headers=_auth(token),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_generate_invalid_channel_pattern_returns_422(
    api_client: AsyncClient,
) -> None:
    """channel=fax does not match Pydantic pattern ^(email|whatsapp|telegram)$ → 422."""
    user = await make_user(api_client)
    resp = await api_client.post(
        "/api/v1/outreach/generate",
        json={"contact_id": str(uuid.uuid4()), "channel": "fax"},
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_generate_unknown_contact_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.post(
        "/api/v1/outreach/generate",
        json={"contact_id": str(uuid.uuid4()), "channel": "email"},
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_generate_non_contactable_returns_422(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Contact exists but is_contactable=False → opt-in check blocks → 422."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    contact_id = await _seed_contact(db_engine, claims["org_id"], is_contactable=False)

    resp = await api_client.post(
        "/api/v1/outreach/generate",
        json={"contact_id": contact_id, "channel": "email"},
        headers=_auth(token),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "opt_in_required"


@pytest.mark.asyncio
async def test_generate_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/outreach/generate",
        json={"contact_id": str(uuid.uuid4()), "channel": "email"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── POST /{id}/send ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_returns_queued(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    contact_id = await _seed_contact(db_engine, claims["org_id"])
    draft = await _generate_draft(api_client, token, contact_id)
    message_id = draft["id"]

    fake_task = Mock()
    fake_task.id = "celery-outreach-task-xyz"

    with patch("corpmind.workers.tasks.outreach.send_message") as mock_send:
        mock_send.apply_async.return_value = fake_task
        resp = await api_client.post(
            f"/api/v1/outreach/{message_id}/send",
            headers=_auth(token),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["message_id"] == message_id
    assert body["status"] == "queued"
    assert body["compliance_reason"] is None


@pytest.mark.asyncio
async def test_send_unknown_message_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.post(
        f"/api/v1/outreach/{uuid.uuid4()}/send",
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_send_already_queued_returns_409(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Sending a message that is already queued raises ConflictError → 409."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    contact_id = await _seed_contact(db_engine, claims["org_id"])
    draft = await _generate_draft(api_client, token, contact_id)
    message_id = draft["id"]

    with patch("corpmind.workers.tasks.outreach.send_message") as mock_send:
        mock_send.apply_async.return_value = Mock(id="task-1")
        await api_client.post(
            f"/api/v1/outreach/{message_id}/send",
            headers=_auth(token),
        )

    resp2 = await api_client.post(
        f"/api/v1/outreach/{message_id}/send",
        headers=_auth(token),
    )
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_send_compliance_blocked_returns_blocked_status(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Contact's opt-in is revoked between draft creation and send.

    The send endpoint returns HTTP 200 with status='blocked' and a compliance_reason —
    it persists the blocked state for the audit log rather than raising an exception.
    """
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    contact_id = await _seed_contact(db_engine, claims["org_id"])
    draft = await _generate_draft(api_client, token, contact_id)
    message_id = draft["id"]

    # Revoke opt-in between draft creation and send
    await _revoke_opt_in(db_engine, contact_id)

    resp = await api_client.post(
        f"/api/v1/outreach/{message_id}/send",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message_id"] == message_id
    assert body["status"] == "blocked"
    assert body["compliance_reason"] is not None


@pytest.mark.asyncio
async def test_send_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(f"/api/v1/outreach/{uuid.uuid4()}/send")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── GET /{id} ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_message_returns_200(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    contact_id = await _seed_contact(db_engine, claims["org_id"])
    draft = await _generate_draft(api_client, token, contact_id)
    message_id = draft["id"]

    resp = await api_client.get(
        f"/api/v1/outreach/{message_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == message_id
    assert body["status"] == "draft"
    assert body["channel"] == "email"
    assert body["body"] != ""


@pytest.mark.asyncio
async def test_get_message_not_found_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.get(
        f"/api/v1/outreach/{uuid.uuid4()}",
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_get_message_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get(f"/api/v1/outreach/{uuid.uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── Tenant isolation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation_message_not_visible_to_other_tenant(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user_a = await make_user(api_client)
    user_b = await make_user(api_client)

    token_a = user_a["tokens"]["access_token"]
    claims_a = _claims(token_a)

    contact_id = await _seed_contact(db_engine, claims_a["org_id"])
    draft = await _generate_draft(api_client, token_a, contact_id)
    message_id = draft["id"]

    resp = await api_client.get(
        f"/api/v1/outreach/{message_id}",
        headers=_auth(user_b["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"
