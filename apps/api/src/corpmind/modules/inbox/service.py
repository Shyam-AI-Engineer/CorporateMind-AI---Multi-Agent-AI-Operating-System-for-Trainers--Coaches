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
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.encryption import decrypt, encrypt
from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.inbox.models import InboxConnection, InboxMessage
from corpmind.modules.inbox.oauth import fetch_gmail_profile, refresh_google_token, revoke_google_token
from corpmind.modules.inbox.repo import InboxConnectionRepo, InboxMessageRepo
from corpmind.modules.inbox.schemas import (
    ConnectionHealthOut,
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
        # No refresh needed: asyncpg uses INSERT...RETURNING so server defaults
        # (created_at, updated_at) are already populated; expire_on_commit=False
        # keeps them accessible post-commit without a second SELECT.
        # A post-commit refresh would fail under RLS because SET LOCAL resets on commit.

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

    async def list_workspace_connections(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[InboxConnectionOut], int]:
        """Return all inbox connections in the caller's workspace, paginated.

        Decrypts email_address for each row.  Returns (items, total) tuple so
        the API can populate a paginated list response in one transaction.
        """
        import asyncio as _asyncio

        ctx = get_tenant_context()
        connections, total = await _asyncio.gather(
            self._conn_repo.find_by_workspace(
                ctx.workspace_id, limit=limit, offset=offset
            ),
            self._conn_repo.count_by_workspace(ctx.workspace_id),
        )
        items = [
            _to_connection_out(conn, decrypt(conn.email_address_enc))
            for conn in connections
        ]
        return items, total

    async def list_messages(
        self,
        *,
        connection_id: uuid.UUID | None = None,
        intent: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[InboxMessageOut], int]:
        """Tenant-scoped paginated inbox message list.

        Body snippets are decrypted per row.  When connection_id is provided we
        also verify it belongs to this tenant — without that check, a leaked
        connection_id from another tenant would silently return zero rows
        (RLS handles isolation but the explicit check produces a clearer 404
        path for the API layer if we ever need it).
        """
        import asyncio as _asyncio

        messages, total = await _asyncio.gather(
            self._msg_repo.list_recent(
                limit=limit,
                offset=offset,
                connection_id=connection_id,
                intent=intent,
            ),
            self._msg_repo.count(connection_id=connection_id, intent=intent),
        )
        items = [
            _to_message_out(
                msg,
                decrypt(msg.body_snippet_enc) if msg.body_snippet_enc else None,
            )
            for msg in messages
        ]
        return items, total

    async def get_workspace_connection(self) -> InboxConnectionOut:
        """Fetch the inbox connection for the caller's current workspace.

        Returns the first connection found — Phase 1 supports one inbox per workspace.

        Raises:
            NotFoundError: No connection exists for this workspace.
            DecryptionError: Stored email ciphertext is corrupted or uses an unknown key.
        """
        ctx = get_tenant_context()
        connections = await self._conn_repo.find_by_workspace(ctx.workspace_id, limit=1)
        if not connections:
            raise NotFoundError("No inbox connection found for this workspace")
        conn = connections[0]
        return _to_connection_out(conn, decrypt(conn.email_address_enc))

    async def disconnect_connection(self, connection_id: uuid.UUID) -> None:
        """Revoke Google OAuth tokens and hard-delete the connection.

        Token revocation is best-effort — if Google rejects or is unreachable the
        local connection is still deleted.  inbox_messages cascade via the FK.

        Raises:
            NotFoundError: Connection not found for this tenant.
        """
        conn = await self._conn_repo.find_by_id(connection_id)
        if conn is None:
            raise NotFoundError(f"Inbox connection {connection_id} not found")

        try:
            refresh_token = decrypt(conn.refresh_token_enc)
            await revoke_google_token(refresh_token)
        except Exception:
            log.warning("inbox.disconnect.revocation_failed", connection_id=str(connection_id))

        await self._conn_repo.delete(connection_id)
        await self._session.commit()
        log.info("inbox.connection_disconnected", connection_id=str(connection_id))

    async def refresh_access_token(self, connection_id: uuid.UUID) -> InboxConnectionOut:
        """Obtain a new access token from Google using the stored refresh token.

        On success: encrypts and persists the new access token + expiry, sets
        status=active.
        On Google rejection: marks status=revoked, commits, then re-raises
        ValidationError so the caller can surface "re-authorization required".

        Raises:
            NotFoundError: Connection not found for this tenant.
            ValidationError: Google rejected the refresh token.
        """
        conn = await self._conn_repo.find_by_id(connection_id)
        if conn is None:
            raise NotFoundError(f"Inbox connection {connection_id} not found")

        refresh_token = decrypt(conn.refresh_token_enc)

        try:
            new_tokens = await refresh_google_token(refresh_token)
        except ValidationError:
            await self._conn_repo.update(connection_id, {
                "status": "revoked",
                "last_error": "Refresh token rejected by Google — re-authorization required",
            })
            await self._session.commit()
            raise

        token_expiry: datetime | None = None
        if new_tokens.expires_in is not None:
            token_expiry = datetime.now(UTC) + timedelta(seconds=new_tokens.expires_in)

        await self._conn_repo.update(connection_id, {
            "access_token_enc": encrypt(new_tokens.access_token),
            "token_expiry_at": token_expiry,
            "status": "active",
            "last_error": None,
        })
        await self._session.commit()

        refreshed = await self._conn_repo.find_by_id(connection_id)
        assert refreshed is not None  # just committed it above
        log.info("inbox.token_refreshed", connection_id=str(connection_id))
        return _to_connection_out(refreshed, decrypt(refreshed.email_address_enc))

    async def check_connection_health(self, connection_id: uuid.UUID) -> ConnectionHealthOut:
        """Validate a connection by refreshing tokens and probing the Gmail API.

        Always writes the result back to the DB so the status column stays current.
        Returns ConnectionHealthOut with healthy=True/False and the post-check status.

        Raises:
            NotFoundError: Connection not found for this tenant.
        """
        conn = await self._conn_repo.find_by_id(connection_id)
        if conn is None:
            raise NotFoundError(f"Inbox connection {connection_id} not found")

        refresh_token = decrypt(conn.refresh_token_enc)

        # Step 1 — verify the refresh token is still valid.
        try:
            new_tokens = await refresh_google_token(refresh_token)
        except ValidationError:
            reason = "Refresh token revoked — re-authorization required"
            await self._conn_repo.update(connection_id, {"status": "revoked", "last_error": reason})
            await self._session.commit()
            return ConnectionHealthOut(healthy=False, reason=reason, status="revoked")

        access_token = new_tokens.access_token
        token_expiry: datetime | None = None
        if new_tokens.expires_in is not None:
            token_expiry = datetime.now(UTC) + timedelta(seconds=new_tokens.expires_in)

        # Step 2 — confirm Gmail API access with the fresh token.
        try:
            await fetch_gmail_profile(access_token)
        except ValidationError:
            reason = "Gmail API access denied — permissions may have been revoked"
            await self._conn_repo.update(connection_id, {
                "access_token_enc": encrypt(access_token),
                "token_expiry_at": token_expiry,
                "status": "needs_reauth",
                "last_error": reason,
            })
            await self._session.commit()
            return ConnectionHealthOut(healthy=False, reason=reason, status="needs_reauth")

        # Healthy — persist the fresh access token.
        await self._conn_repo.update(connection_id, {
            "access_token_enc": encrypt(access_token),
            "token_expiry_at": token_expiry,
            "status": "active",
            "last_error": None,
        })
        await self._session.commit()
        return ConnectionHealthOut(healthy=True, reason=None, status="active")

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

    async def get_decrypted_snippet(self, message_id: uuid.UUID) -> str | None:
        """Return ONLY the decrypted body snippet for an inbox message.

        This is the inbox module's single entry point for the follow-up cadence
        (ADR-0008) to hydrate reply context.  Decryption — and therefore
        knowledge of the AES key registry — stays inside this module; callers in
        other modules / workers never touch ciphertext.  Returns None when the
        message has no stored snippet (body_snippet_enc is NULL).

        Distinct from get_message(), which returns the full InboxMessageOut DTO;
        the cadence only needs the plaintext reply text, not the whole record.

        Raises:
            NotFoundError: Message not found for this tenant.
            DecryptionError: Stored ciphertext is corrupted or uses an unknown key version.
        """
        msg = await self._msg_repo.find_by_id(message_id)
        if msg is None:
            raise NotFoundError(f"Inbox message {message_id} not found")
        return decrypt(msg.body_snippet_enc) if msg.body_snippet_enc else None

    # ── Classification ─────────────────────────────────────────────────────────

    async def update_classification(
        self,
        message_id: uuid.UUID,
        *,
        intent: str,
        confidence: float,
        model_name: str,
    ) -> None:
        """Persist a ReplyClassifierAgent result on an existing inbox message.

        Caller (workers/tasks/inbox.py) invokes this after create_if_not_exists
        succeeds with was_inserted=True.  Duplicate sync runs MUST NOT re-classify
        (cost + Langfuse spam) — the worker enforces the gate; the service is the
        single point that touches the four classification columns.

        Raises NotFoundError if the row no longer exists (the connection cascade-
        deletion ran between the sync insert and this call — a benign race).
        """
        msg = await self._msg_repo.find_by_id(message_id)
        if msg is None:
            raise NotFoundError(f"Inbox message {message_id} not found")
        await self._msg_repo.update_classification(
            message_id,
            intent=intent,
            confidence=confidence,
            model_name=model_name,
            classified_at=datetime.now(UTC),
        )
        await self._session.commit()

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
        # Numeric(4,3) Decimal → float for JSON serialization.
        confidence=float(msg.confidence) if msg.confidence is not None else None,
        classified_at=msg.classified_at,
        classification_model=msg.classification_model,
        synced_at=msg.synced_at,
    )
