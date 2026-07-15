"""Integration Hub REST API — Sprint 55: API Keys and Webhooks."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.config import settings
from corpmind.core.database import get_session
from corpmind.core.rate_limit import make_rate_limiter
from corpmind.modules.integrations.schemas import (
    ApiKeyCreate,
    ApiKeyCreatedOut,
    ApiKeyListOut,
    ApiKeyOut,
    WebhookCreate,
    WebhookCreatedOut,
    WebhookListOut,
    WebhookOut,
    WebhookUpdate,
)
from corpmind.modules.integrations.service import IntegrationService

router = APIRouter()

_api_key_rl = make_rate_limiter(
    "api_key_create",
    max_requests=settings.RATE_LIMIT_API_KEY_MAX,
    window_seconds=settings.RATE_LIMIT_API_KEY_WINDOW,
)
_webhook_rl = make_rate_limiter(
    "webhook_create",
    max_requests=settings.RATE_LIMIT_WEBHOOK_MAX,
    window_seconds=settings.RATE_LIMIT_WEBHOOK_WINDOW,
)


def _svc(session: AsyncSession = Depends(get_session)) -> IntegrationService:
    return IntegrationService(session)


# ── API Keys ──────────────────────────────────────────────────────────────────


@router.get(
    "/api-keys",
    response_model=ApiKeyListOut,
    summary="List API keys for a workspace",
)
async def list_api_keys(
    workspace_id: uuid.UUID = Query(...),
    svc: IntegrationService = Depends(_svc),
) -> ApiKeyListOut:
    return await svc.list_api_keys(workspace_id)


@router.post(
    "/api-keys",
    response_model=ApiKeyCreatedOut,
    status_code=201,
    summary="Create a new API key — returns plaintext key once",
)
async def create_api_key(
    body: ApiKeyCreate,
    _rl: None = Depends(_api_key_rl),
    svc: IntegrationService = Depends(_svc),
) -> ApiKeyCreatedOut:
    return await svc.create_api_key(body)


@router.get(
    "/api-keys/{key_id}",
    response_model=ApiKeyOut,
    summary="Get API key metadata",
)
async def get_api_key(
    key_id: uuid.UUID,
    svc: IntegrationService = Depends(_svc),
) -> ApiKeyOut:
    return await svc.get_api_key(key_id)


@router.post(
    "/api-keys/{key_id}/revoke",
    response_model=ApiKeyOut,
    summary="Revoke an API key (irreversible)",
)
async def revoke_api_key(
    key_id: uuid.UUID,
    svc: IntegrationService = Depends(_svc),
) -> ApiKeyOut:
    return await svc.revoke_api_key(key_id)


# ── Webhooks ──────────────────────────────────────────────────────────────────


@router.get(
    "/webhooks",
    response_model=WebhookListOut,
    summary="List webhooks for a workspace",
)
async def list_webhooks(
    workspace_id: uuid.UUID = Query(...),
    svc: IntegrationService = Depends(_svc),
) -> WebhookListOut:
    return await svc.list_webhooks(workspace_id)


@router.post(
    "/webhooks",
    response_model=WebhookCreatedOut,
    status_code=201,
    summary="Register a new webhook — returns signing secret once",
)
async def create_webhook(
    body: WebhookCreate,
    _rl: None = Depends(_webhook_rl),
    svc: IntegrationService = Depends(_svc),
) -> WebhookCreatedOut:
    return await svc.create_webhook(body)


@router.patch(
    "/webhooks/{webhook_id}",
    response_model=WebhookOut,
    summary="Update a webhook",
)
async def update_webhook(
    webhook_id: uuid.UUID,
    body: WebhookUpdate,
    svc: IntegrationService = Depends(_svc),
) -> WebhookOut:
    return await svc.update_webhook(webhook_id, body)


@router.delete(
    "/webhooks/{webhook_id}",
    status_code=204,
    summary="Delete a webhook",
)
async def delete_webhook(
    webhook_id: uuid.UUID,
    svc: IntegrationService = Depends(_svc),
) -> None:
    await svc.delete_webhook(webhook_id)
