"""Inbox service — connection management, message storage, and reply matching.

Phase 1 surface
───────────────
• create_connection()    — encrypt credentials, dedup check, persist.
• get_connection()       — fetch + decrypt email address for the caller.
• update_connection()    — update mutable fields (status, token refresh, sync state).
• delete_connection()    — remove a connection; inbox_messages cascade via FK.

• create_message()       — encrypt body snippet, persist synced inbound message.
• create_if_not_exists() — idempotent insert for sync workers (ON CONFLICT DO NOTHING).
• get_message()          — fetch + decrypt body snippet.

• match_reply()          — resolve smtp_message_id → outbound_message_id.

Encryption ownership
────────────────────
This service is the sole caller of encrypt() and decrypt() for inbox fields.
Repositories receive ORM objects with body_snippet_enc / email_address_enc already
set — they never see or handle plaintext credentials or message bodies.

Cross-module data access
────────────────────────
match_reply() reads outbound_messages via raw text() SQL.
No cross-module ORM model or repo imports — same boundary rule as OutreachService.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.encryption import decrypt, encrypt
from corpmind.core.exceptions import ConflictError, NotFoundError
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.inbox.models import InboxConnection, InboxMessage
from corpmind.modules.inbox.repo import InboxConnectionRepo, InboxMessageRepo
from corpmind.modules.inbox.schemas import (
    InboxConnectionCreate,
    InboxConnectionOut,
    InboxMessageOut,
)

log = structlog.get_logger(__name__)


class InboxService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._conn_repo = InboxConnectionRepo(session)
        self._msg_repo = InboxMessageRepo(session)

    # ── Connection Management ─────────────────────────────────────────────────

    async def create_connection(self, req: InboxConnectionCreate) -> InboxConnectionOut:
        """Encrypt credentials, run dedup check, and persist a new inbox connection.

        Raises:
            ConflictError: The same email address is already connected for this tenant.
        """
        ctx = get_tenant_context()
        email_hash = _email_address_hash(req.email_address, ctx.org_id)

        if await self._conn_repo.find_by_email_hash(email_hash) is not None:
            raise ConflictError(
                "An inbox connection for this email address already exists for this tenant."
            )

        conn = InboxConnection(
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            provider=req.provider,
            email_address_enc=encrypt(req.email_address),
            refresh_token_enc=encrypt(req.refresh_token),
            access_token_enc=encrypt(req.access_token) if req.access_token else None,
            email_address_hash=email_hash,
            scopes=req.scopes,
            token_expiry_at=req.token_expiry_at,
            status="active",
            connected_by=req.connected_by,
        )
        await self._conn_repo.create(conn)
        await self._session.commit()
        await self._session.refresh(conn)

        log.info("inbox.connection_created", connection_id=str(conn.id), provider=conn.provider)
        return _to_connection_out(conn, req.email_address)

    async def get_connection(self, connection_id: uuid.UUID) -> InboxConnectionOut:
        """Fetch a connection and decrypt its email address.

        Raises:
            NotFoundError: Connection not found for this tenant.
            DecryptionError: Stored ciphertext is corrupted or uses an unknown key version.
        """
        conn = await self._conn_repo.find_by_id(connection_id)
        if conn is None:
            raise NotFoundError(f"Inbox connection {connection_id} not found")
        return _to_connection_out(conn, decrypt(conn.email_address_enc))

    async def update_connection(
        self, connection_id: uuid.UUID, values: dict[str, object]
    ) -> None:
        """Update mutable fields on a connection (status, sync state, token expiry).

        Raises:
            NotFoundError: Connection not found for this tenant.
        """
        if await self._conn_repo.find_by_id(connection_id) is None:
            raise NotFoundError(f"Inbox connection {connection_id} not found")
        await self._conn_repo.update(connection_id, values)
        await self._session.commit()

    async def delete_connection(self, connection_id: uuid.UUID) -> None:
        """Delete a connection; inbox_messages are cascade-deleted by the FK.

        Raises:
            NotFoundError: Connection not found for this tenant.
        """
        if not await self._conn_repo.delete(connection_id):
            raise NotFoundError(f"Inbox connection {connection_id} not found")
        await self._session.commit()
        log.info("inbox.connection_deleted", connection_id=str(connection_id))

    # ── Message Operations ─────────────────────────────────────────────────────

    async def create_message(
        self, message: InboxMessage, body_snippet: str | None = None
    ) -> InboxMessageOut:
        """Encrypt body snippet (when provided) and persist a synced inbound message."""
        if body_snippet is not None:
            message.body_snippet_enc = encrypt(body_snippet)
        msg = await self._msg_repo.create(message)
        await self._session.commit()
        return _to_message_out(msg, body_snippet)

    async def create_if_not_exists(
        self, message: InboxMessage, body_snippet: str | None = None
    ) -> tuple[bool, InboxMessageOut]:
        """Idempotent insert — safe to call on duplicate sync runs.

        Returns (True, out) when the row was inserted.
        Returns (False, out) when ON CONFLICT DO NOTHING fired (already synced).
        The out DTO is built from the message object either way so the caller can
        log or inspect fields without issuing a separate fetch.
        """
        if body_snippet is not None:
            message.body_snippet_enc = encrypt(body_snippet)
        was_inserted = await self._msg_repo.create_if_not_exists(message)
        if was_inserted:
            await self._session.commit()
        return was_inserted, _to_message_out(message, body_snippet)

    async def get_message(self, message_id: uuid.UUID) -> InboxMessageOut:
        """Fetch a message and decrypt its body snippet.

        Raises:
            NotFoundError: Message not found for this tenant.
            DecryptionError: Stored ciphertext is corrupted or uses an unknown key version.
        """
        msg = await self._msg_repo.find_by_id(message_id)
        if msg is None:
            raise NotFoundError(f"Inbox message {message_id} not found")
        body_snippet = decrypt(msg.body_snippet_enc) if msg.body_snippet_enc else None
        return _to_message_out(msg, body_snippet)

    # ── Reply Matching ─────────────────────────────────────────────────────────

    async def match_reply(self, smtp_message_id: str) -> uuid.UUID | None:
        """Resolve an inbound smtp_message_id to the outbound message it replies to.

        Uses raw SQL — outbound_messages lives in the outreach module; we cannot
        import its ORM model or repo here (cross-module boundary rule).
        Returns the outbound_message_id UUID on match, None when unmatched.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            text(
                "SELECT id FROM outbound_messages"
                " WHERE tenant_id = :tid AND smtp_message_id = :mid"
                " LIMIT 1"
            ),
            {"tid": str(ctx.org_id), "mid": smtp_message_id},
        )
        row = result.one_or_none()
        return uuid.UUID(str(row[0])) if row else None


# ── Module-level helpers ───────────────────────────────────────────────────────

def _email_address_hash(email: str, tenant_id: uuid.UUID) -> str:
    """HMAC-SHA256(email, tenant_id.bytes) — deterministic, tenant-scoped dedup hash.

    Uses tenant_id.bytes (16-byte binary UUID) as the HMAC key, as documented on
    InboxConnection.email_address_hash.  This is intentionally distinct from
    outreach.service.recipient_hmac which uses str(tenant_id).encode() — the two
    hashes serve different purposes and must not collide.
    """
    return hmac.new(tenant_id.bytes, email.encode("utf-8"), hashlib.sha256).hexdigest()


def _to_connection_out(conn: InboxConnection, email_address: str) -> InboxConnectionOut:
    return InboxConnectionOut(
        id=conn.id,
        workspace_id=conn.workspace_id,
        provider=conn.provider,
        email_address=email_address,
        scopes=conn.scopes,
        token_expiry_at=conn.token_expiry_at,
        status=conn.status,
        last_sync_at=conn.last_sync_at,
        last_error=conn.last_error,
        connected_by=conn.connected_by,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


def _to_message_out(msg: InboxMessage, body_snippet: str | None) -> InboxMessageOut:
    return InboxMessageOut(
        id=msg.id,
        connection_id=msg.connection_id,
        provider_message_id=msg.provider_message_id,
        provider_thread_id=msg.provider_thread_id,
        smtp_message_id=msg.smtp_message_id,
        in_reply_to=msg.in_reply_to,
        outbound_message_id=msg.outbound_message_id,
        match_method=msg.match_method,
        from_address=msg.from_address,
        subject=msg.subject,
        received_at=msg.received_at,
        body_snippet=body_snippet,
        body_truncated=msg.body_truncated,
        reply_intent=msg.reply_intent,
        synced_at=msg.synced_at,
    )
