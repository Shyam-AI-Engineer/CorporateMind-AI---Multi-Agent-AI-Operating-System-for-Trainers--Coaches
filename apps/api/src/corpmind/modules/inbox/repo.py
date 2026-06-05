"""Inbox repository: InboxConnectionRepo and InboxMessageRepo."""

from __future__ import annotations

import uuid

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

        ctx = get_tenant_context()
        stmt = (
            pg_insert(InboxMessage)
            .values(
                id=message.id,
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
    ) -> list[InboxMessage]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(InboxMessage)
            .where(InboxMessage.tenant_id == ctx.org_id)
            .order_by(InboxMessage.received_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
