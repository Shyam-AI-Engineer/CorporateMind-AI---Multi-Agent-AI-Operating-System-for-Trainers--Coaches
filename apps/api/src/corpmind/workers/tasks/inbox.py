"""Inbox Celery tasks — Gmail message sync."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import redis
import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from corpmind.workers.celery_app import app

log = structlog.get_logger(__name__)

# Prevents concurrent sync runs on the same connection.  10-minute TTL means a
# crashed worker releases the lock automatically without manual intervention.
_SYNC_LOCK_TTL = 600

# Safety ceiling: 10 pages × 100 messages = 1,000 messages per sync run.
# Prevents a single task from running indefinitely against a high-volume inbox.
_MAX_PAGES = 10

# Chars to store from Gmail's snippet field (the first ~100-char plain-text
# preview the API already computes).  body_truncated=True is always set
# because a snippet is by definition shorter than the full body.
_SNIPPET_MAX = 500


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    soft_time_limit=270,
    time_limit=300,
    queue="ingestion",
    name="corpmind.workers.tasks.inbox.sync_gmail_messages",
)
def sync_gmail_messages(
    self: Task,
    *,
    connection_id: str,
    tenant_id: str,
    workspace_id: str,
    request_id: str,
) -> dict:
    """Sync recent Gmail messages for a single inbox connection.

    Idempotency: a Redis NX lock keyed by connection_id prevents concurrent
    runs on the same connection.  The lock is deleted on completion or failure,
    and expires automatically after _SYNC_LOCK_TTL seconds if the worker dies.

    Revoked tokens cause an immediate non-retryable return so we do not burn
    retries on a condition that requires human re-authorization.

    Rate-limit errors (429) and transient failures propagate and trigger
    Celery's exponential backoff retry.  SoftTimeLimitExceeded uses a fixed
    30-second countdown so any in-progress DB commit can be cleanly flushed.
    """
    from corpmind.core.config import settings

    lock_key = f"inbox:syncing:{connection_id}"
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        if not r.set(lock_key, "1", ex=_SYNC_LOCK_TTL, nx=True):
            log.info("inbox.sync.already_running", connection_id=connection_id)
            return {"status": "skipped", "connection_id": connection_id, "reason": "lock_held"}

        try:
            result = asyncio.run(
                _run_sync(
                    connection_id=connection_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    request_id=request_id,
                )
            )
        except SoftTimeLimitExceeded:
            log.warning("inbox.sync.soft_timeout", connection_id=connection_id)
            raise self.retry(countdown=30)
        except Exception as exc:
            log.error("inbox.sync.error", connection_id=connection_id, error=str(exc))
            raise self.retry(exc=exc)
        finally:
            r.delete(lock_key)

        return result
    finally:
        r.close()


# ── Async implementation ───────────────────────────────────────────────────────

async def _run_sync(
    *,
    connection_id: str,
    tenant_id: str,
    workspace_id: str,
    request_id: str,
) -> dict:
    """Fetch, deduplicate, and persist recent Gmail messages for one connection.

    Steps:
      1. Load InboxConnection — skip if not found or already revoked.
      2. Refresh access token via Google — mark revoked and return on rejection.
      3. Paginate Gmail INBOX (up to _MAX_PAGES pages, _MAX_PAGES×100 messages).
      4. For each message: extract headers, attempt reply matching, persist via
         InboxService.create_if_not_exists (idempotent ON CONFLICT DO NOTHING).
      5. Update last_sync_at and clear last_error on success.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    from corpmind.core.config import settings
    from corpmind.core.database import set_rls_tenant
    from corpmind.core.encryption import decrypt, encrypt
    from corpmind.core.exceptions import ValidationError
    from corpmind.core.tenancy import TenantContext, set_tenant_context, clear_tenant_context
    from corpmind.modules.inbox.gmail_client import get_message, list_inbox_messages
    from corpmind.modules.inbox.models import InboxMessage
    from corpmind.modules.inbox.oauth import refresh_google_token
    from corpmind.modules.inbox.repo import InboxConnectionRepo
    from corpmind.modules.inbox.service import InboxService

    conn_uuid = uuid.UUID(connection_id)
    tenant_uuid = uuid.UUID(tenant_id)
    ws_uuid = uuid.UUID(workspace_id)

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    ctx = TenantContext(
        org_id=tenant_uuid,
        workspace_id=ws_uuid,
        user_id=tenant_uuid,
        role="system",
        request_id=request_id,
    )
    token = set_tenant_context(ctx)

    try:
        async with factory() as session:
            await set_rls_tenant(session, tenant_uuid)

            conn_repo = InboxConnectionRepo(session)
            service = InboxService(session)

            # ── 1. Load connection ─────────────────────────────────────────────
            conn = await conn_repo.find_by_id(conn_uuid)
            if conn is None:
                log.warning("inbox.sync.connection_not_found", connection_id=connection_id)
                return {"status": "not_found", "connection_id": connection_id}

            if conn.status == "revoked":
                log.info("inbox.sync.skip_revoked", connection_id=connection_id)
                return {"status": "skipped", "connection_id": connection_id, "reason": "revoked"}

            # ── 2. Refresh access token ────────────────────────────────────────
            refresh_token = decrypt(conn.refresh_token_enc)
            try:
                new_tokens = await refresh_google_token(refresh_token)
            except ValidationError:
                await conn_repo.update(conn_uuid, {
                    "status": "revoked",
                    "last_error": "Refresh token revoked — re-authorization required",
                })
                await session.commit()
                log.warning("inbox.sync.token_revoked", connection_id=connection_id)
                return {"status": "revoked", "connection_id": connection_id}

            access_token = new_tokens.access_token
            token_expiry: datetime | None = None
            if new_tokens.expires_in is not None:
                token_expiry = datetime.now(UTC) + timedelta(seconds=new_tokens.expires_in)

            await conn_repo.update(conn_uuid, {
                "access_token_enc": encrypt(access_token),
                "token_expiry_at": token_expiry,
                "status": "active",
                "last_error": None,
            })
            await session.commit()

            # ── 3. Paginate Gmail messages ─────────────────────────────────────
            inserted_count = 0
            duplicate_count = 0
            page_token: str | None = None
            pages_fetched = 0

            while pages_fetched < _MAX_PAGES:
                summaries, next_page_token = await list_inbox_messages(
                    access_token, page_token=page_token
                )
                pages_fetched += 1

                for summary in summaries:
                    msg_detail = await get_message(access_token, summary.message_id)

                    # ── 4a. Reply matching via RFC 2822 header chaining ────────
                    # The In-Reply-To header holds the Message-ID of the email
                    # this inbound is replying to — which is our outbound's
                    # smtp_message_id.  Fall back to the last References entry.
                    match_key: str | None = msg_detail.in_reply_to
                    if not match_key and msg_detail.references_header:
                        parts = msg_detail.references_header.split()
                        match_key = parts[-1] if parts else None

                    outbound_message_id: uuid.UUID | None = None
                    match_method: str | None = None

                    if match_key:
                        outbound_message_id = await service.match_reply(match_key)
                        if outbound_message_id:
                            match_method = "in_reply_to" if msg_detail.in_reply_to else "references"

                    # ── 4b. Body snippet ───────────────────────────────────────
                    # Gmail's snippet is already a short plain-text preview;
                    # we store it as-is.  body_truncated is always True because
                    # a snippet is shorter than the full email body by definition.
                    body_snippet: str | None = None
                    body_truncated = False
                    if msg_detail.snippet:
                        body_snippet = msg_detail.snippet[:_SNIPPET_MAX]
                        body_truncated = True

                    # ── 4c. Build ORM object and persist ──────────────────────
                    inbox_msg = InboxMessage(
                        tenant_id=tenant_uuid,
                        connection_id=conn_uuid,
                        provider_message_id=summary.message_id,
                        provider_thread_id=msg_detail.thread_id,
                        smtp_message_id=match_key,          # stored for future re-matching
                        in_reply_to=msg_detail.in_reply_to,
                        references_header=msg_detail.references_header,
                        outbound_message_id=outbound_message_id,
                        match_method=match_method,
                        from_address=msg_detail.from_address,
                        subject=msg_detail.subject,
                        received_at=msg_detail.received_at,
                        body_snippet_enc=None,  # service.create_if_not_exists encrypts this
                        body_truncated=body_truncated,
                        reply_intent=None,      # populated by ReplyClassifierAgent (Phase 2)
                    )

                    was_inserted, _ = await service.create_if_not_exists(inbox_msg, body_snippet)
                    if was_inserted:
                        inserted_count += 1
                    else:
                        duplicate_count += 1

                if not next_page_token:
                    break
                page_token = next_page_token

            # ── 5. Update sync metadata ────────────────────────────────────────
            await conn_repo.update(conn_uuid, {
                "last_sync_at": datetime.now(UTC),
                "status": "active",
                "last_error": None,
            })
            await session.commit()

            log.info(
                "inbox.sync.complete",
                connection_id=connection_id,
                inserted=inserted_count,
                duplicates=duplicate_count,
                pages=pages_fetched,
            )
            return {
                "status": "synced",
                "connection_id": connection_id,
                "inserted": inserted_count,
                "duplicates": duplicate_count,
                "pages": pages_fetched,
            }
    finally:
        clear_tenant_context(token)
        await engine.dispose()
