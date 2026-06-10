"""Inbox repository: InboxConnectionRepo and InboxMessageRepo."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.inbox.models import InboxConnection, InboxMessage


class InboxConnectionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, connection: InboxConnection) -> InboxConnection:
        self._session.add(connection)
        await self._session.flush()
        return connection

    async def find_by_id(self, connection_id: uuid.UUID) -> InboxConnection | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(InboxConnection).where(
                InboxConnection.id == connection_id,
                InboxConnection.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InboxConnection]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(InboxConnection)
            .where(
                InboxConnection.tenant_id == ctx.org_id,
                InboxConnection.workspace_id == workspace_id,
            )
            .order_by(InboxConnection.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_workspace(self, workspace_id: uuid.UUID) -> int:
        """Total connections in a workspace for this tenant — pagination support."""
        from sqlalchemy import func as sql_func

        ctx = get_tenant_context()
        result = await self._session.execute(
            select(sql_func.count())
            .select_from(InboxConnection)
            .where(
                InboxConnection.tenant_id == ctx.org_id,
                InboxConnection.workspace_id == workspace_id,
            )
        )
        return result.scalar_one()

    async def find_by_email_hash(
        self, email_address_hash: str
    ) -> InboxConnection | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(InboxConnection).where(
                InboxConnection.tenant_id == ctx.org_id,
                InboxConnection.email_address_hash == email_address_hash,
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        connection_id: uuid.UUID,
        values: dict[str, object],
    ) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(InboxConnection)
            .where(
                InboxConnection.id == connection_id,
                InboxConnection.tenant_id == ctx.org_id,
            )
            .values(**values)
        )

    async def delete(self, connection_id: uuid.UUID) -> bool:
        """Delete a connection owned by the current tenant.

        Returns True if a row was deleted, False when not found or owned by a
        different tenant — callers can treat False as a 404 without leaking the
        existence of other tenants' connections.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            delete(InboxConnection).where(
                InboxConnection.id == connection_id,
                InboxConnection.tenant_id == ctx.org_id,
            )
        )
        return result.rowcount > 0  # type: ignore[union-attr]


class InboxMessageRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, message: InboxMessage) -> InboxMessage:
        self._session.add(message)
        await self._session.flush()
        return message

    async def find_by_id(self, message_id: uuid.UUID) -> InboxMessage | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(InboxMessage).where(
                InboxMessage.id == message_id,
                InboxMessage.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_if_not_exists(self, message: InboxMessage) -> bool:
        """Insert a message; silently skip if (connection_id, provider_message_id) exists.

        Returns True when the row was inserted, False when the unique constraint
        fired (duplicate sync run).  Uses ON CONFLICT DO NOTHING so the operation
        is atomic — concurrent sync workers hitting the same Gmail message ID each
        get a definitive result with no IntegrityError raised.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        import uuid as _uuid
        ctx = get_tenant_context()
        stmt = (
            pg_insert(InboxMessage)
            .values(
                id=message.id if message.id is not None else _uuid.uuid4(),
                tenant_id=ctx.org_id,
                connection_id=message.connection_id,
                provider_message_id=message.provider_message_id,
                provider_thread_id=message.provider_thread_id,
                smtp_message_id=message.smtp_message_id,
                in_reply_to=message.in_reply_to,
                references_header=message.references_header,
                outbound_message_id=message.outbound_message_id,
                match_method=message.match_method,
                from_address=message.from_address,
                subject=message.subject,
                received_at=message.received_at,
                body_snippet_enc=message.body_snippet_enc,
                body_truncated=message.body_truncated,
                reply_intent=message.reply_intent,
            )
            .on_conflict_do_nothing(
                constraint="uq_inbox_messages_connection_provider_message"
            )
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[union-attr]

    async def get_by_provider_message_id(
        self,
        connection_id: uuid.UUID,
        provider_message_id: str,
    ) -> InboxMessage | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(InboxMessage).where(
                InboxMessage.tenant_id == ctx.org_id,
                InboxMessage.connection_id == connection_id,
                InboxMessage.provider_message_id == provider_message_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_smtp_message_id(
        self, smtp_message_id: str
    ) -> InboxMessage | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(InboxMessage).where(
                InboxMessage.tenant_id == ctx.org_id,
                InboxMessage.smtp_message_id == smtp_message_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_connection(
        self,
        connection_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InboxMessage]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(InboxMessage)
            .where(
                InboxMessage.tenant_id == ctx.org_id,
                InboxMessage.connection_id == connection_id,
            )
            .order_by(InboxMessage.received_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_recent(
        self,
        limit: int = 50,
        offset: int = 0,
        *,
        connection_id: uuid.UUID | None = None,
        intent: str | None = None,
    ) -> list[InboxMessage]:
        """Tenant-scoped paginated list ordered by received_at DESC.

        Optional filters keep the same SQL path so the index plan is unchanged:
          - connection_id: limits to messages for one Gmail account.
          - intent:        filters on reply_intent for "show only interested".
        """
        ctx = get_tenant_context()
        stmt = select(InboxMessage).where(InboxMessage.tenant_id == ctx.org_id)
        if connection_id is not None:
            stmt = stmt.where(InboxMessage.connection_id == connection_id)
        if intent is not None:
            stmt = stmt.where(InboxMessage.reply_intent == intent)
        stmt = stmt.order_by(InboxMessage.received_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        connection_id: uuid.UUID | None = None,
        intent: str | None = None,
    ) -> int:
        """Total count under the same filters used by list_recent — for pagination UI."""
        from sqlalchemy import func as sql_func

        ctx = get_tenant_context()
        stmt = (
            select(sql_func.count())
            .select_from(InboxMessage)
            .where(InboxMessage.tenant_id == ctx.org_id)
        )
        if connection_id is not None:
            stmt = stmt.where(InboxMessage.connection_id == connection_id)
        if intent is not None:
            stmt = stmt.where(InboxMessage.reply_intent == intent)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def update_classification(
        self,
        message_id: uuid.UUID,
        *,
        intent: str,
        confidence: float,
        model_name: str,
        classified_at: datetime,
    ) -> None:
        """Set the four classification columns for one inbox_message row.

        Tenant-scoped UPDATE — the WHERE clause filters on tenant_id alongside id
        so a leaked message_id from another tenant cannot mutate this tenant's row
        even before RLS engages (defense-in-depth).  Casting confidence to Decimal
        preserves the [0,1] precision the model emitted (Numeric(4,3)).
        """
        ctx = get_tenant_context()
        await self._session.execute(
            update(InboxMessage)
            .where(
                InboxMessage.id == message_id,
                InboxMessage.tenant_id == ctx.org_id,
            )
            .values(
                reply_intent=intent,
                confidence=Decimal(str(round(confidence, 3))),
                classification_model=model_name,
                classified_at=classified_at,
            )
        )
