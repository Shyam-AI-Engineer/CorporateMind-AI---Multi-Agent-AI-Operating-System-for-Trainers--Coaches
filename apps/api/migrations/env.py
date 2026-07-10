"""Alembic environment configuration for CorporateMind AI.

Uses asyncpg for async migrations. Imports all SQLAlchemy models so
autogenerate can detect table changes.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so Alembic can see them for autogenerate
from corpmind.core.database import Base
from corpmind.modules.identity.models import Org, Workspace, User  # noqa: F401
from corpmind.modules.campaigns.models import Campaign, CampaignRecipient  # noqa: F401
from corpmind.modules.compliance.models import AuditEvent, UnsubscribeEntry  # noqa: F401
from corpmind.modules.outreach.models import OutboundMessage  # noqa: F401
from corpmind.modules.trainer_intel.models import TrainerProfile  # noqa: F401
from corpmind.modules.hr_discovery.models import Company, HRContact  # noqa: F401
from corpmind.modules.social.models import SocialPost  # noqa: F401
from corpmind.modules.whatsapp.models import WhatsAppTemplate, WhatsAppSession  # noqa: F401
from corpmind.modules.proposals.models import Proposal  # noqa: F401
from corpmind.modules.crm.models import Lead, BookingWebhookEvent  # noqa: F401
from corpmind.modules.analytics.models import AnalyticsDaily  # noqa: F401
from corpmind.modules.billing.models import Subscription, UsageMeter  # noqa: F401
from corpmind.ai.models import ModelRun  # noqa: F401
from corpmind.modules.inbox.models import InboxConnection, InboxMessage  # noqa: F401
from corpmind.modules.bulk_operations.models import BulkOperation  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: object) -> None:
    context.configure(
        connection=connection,  # type: ignore[arg-type]
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
