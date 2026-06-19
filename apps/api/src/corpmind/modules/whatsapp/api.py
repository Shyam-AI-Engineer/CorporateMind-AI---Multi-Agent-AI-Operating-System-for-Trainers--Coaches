"""WhatsApp module REST API — templates list + delivery-receipt webhook."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_public_session, get_session
from corpmind.modules.whatsapp.schemas import WhatsAppTemplateListOut
from corpmind.modules.whatsapp.service import WhatsAppService

router = APIRouter()


@router.get(
    "/templates",
    response_model=WhatsAppTemplateListOut,
    summary="List approved WhatsApp templates",
)
async def list_whatsapp_templates(
    session: AsyncSession = Depends(get_session),
) -> WhatsAppTemplateListOut:
    """Return all Meta-approved WhatsApp templates for the current tenant."""
    svc = WhatsAppService(session)
    templates = await svc.list_approved_templates()
    return WhatsAppTemplateListOut(
        items=templates,  # type: ignore[arg-type]
        total=len(templates),
    )


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Meta WhatsApp delivery-receipt webhook",
)
async def whatsapp_webhook(request: Request) -> dict:
    """Receive Meta webhook events (delivery receipts).

    HMAC-SHA256 verified via X-Hub-Signature-256 before body is parsed.
    Inbound messages are silently dropped in Sprint 16A (Sprint 17 scope).
    Returns {"status": "ok"} — Meta requires a 200 within 20s to avoid retries.
    """
    from corpmind.channels.registry import get as registry_get  # noqa: PLC0415
    from corpmind.modules.outreach.repo import OutboundMessageRepo  # noqa: PLC0415

    payload = await request.body()
    headers = request.headers

    try:
        adapter = registry_get("whatsapp")
        events = await adapter.handle_webhook(payload, headers)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    if not events:
        return {"status": "ok", "processed": 0}

    processed = 0
    async for session in get_public_session():
        repo = OutboundMessageRepo(session)
        for event in events:
            if event.event_type != "delivery_report":
                continue
            wa_msg_id = event.provider_message_id
            if not wa_msg_id:
                continue
            delivery_status = event.metadata.get("delivery_status", "sent")
            await repo.update_status_by_provider_id(wa_msg_id, delivery_status)
            processed += 1
        await session.commit()
        break

    return {"status": "ok", "processed": processed}


@router.get(
    "/webhook",
    summary="Meta webhook verification (GET challenge)",
    include_in_schema=False,
)
async def whatsapp_webhook_verify(request: Request) -> int:
    """Meta calls GET with hub.challenge during webhook registration."""
    from corpmind.core.config import settings  # noqa: PLC0415

    params = request.query_params
    if params.get("hub.verify_token") != settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bad verify token")
    challenge = params.get("hub.challenge", "")
    return int(challenge)
