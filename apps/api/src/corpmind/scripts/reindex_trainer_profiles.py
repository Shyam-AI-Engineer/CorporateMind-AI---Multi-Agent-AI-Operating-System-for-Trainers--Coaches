"""Reindex locked trainer profiles into Qdrant.

Run this script when Qdrant was unavailable during lock_profile() and some
profiles are locked in Postgres but have no corresponding vector point.
The upsert is idempotent — re-running never creates duplicates.

Requirements:
  DATABASE_URL must be set in the environment (or apps/api/.env).
  The database user does NOT need BYPASSRLS because this script enumerates
  org IDs from the `orgs` table (which has no RLS policy) and then activates
  SET LOCAL app.tenant_id for each org before querying trainer_profiles.

Usage:
    # Reindex all locked profiles across all orgs
    uv run python -m corpmind.scripts.reindex_trainer_profiles

    # Preview what would be indexed without writing to Qdrant
    uv run python -m corpmind.scripts.reindex_trainer_profiles --dry-run

    # Reindex a single org
    uv run python -m corpmind.scripts.reindex_trainer_profiles --org-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid as _uuid_mod

import structlog

log = structlog.get_logger(__name__)


async def _run(*, dry_run: bool, org_id_filter: _uuid_mod.UUID | None) -> int:
    """Return count of failures (0 = clean exit)."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.ai.trainer_vector_store import TrainerVectorStore
    from corpmind.core.config import settings
    from corpmind.core.database import set_rls_tenant
    from corpmind.modules.identity.models import Org
    from corpmind.modules.trainer_intel.models import TrainerProfile

    engine = create_async_engine(settings.DATABASE_URL, pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = TrainerVectorStore()
    indexed = skipped = failures = 0

    try:
        # Step 1: Collect org IDs.
        # `orgs` inherits from Base (no RLS policy) — no SET LOCAL needed here.
        async with factory() as session:
            if org_id_filter is not None:
                org_ids = [org_id_filter]
            else:
                result = await session.execute(
                    select(Org.id).where(Org.is_active.is_(True))
                )
                org_ids = [row[0] for row in result.all()]

        log.info("reindex.start", total_orgs=len(org_ids), dry_run=dry_run)

        # Step 2: For each org, activate RLS and query locked profiles.
        for org_id in org_ids:
            async with factory() as session:
                await set_rls_tenant(session, org_id)
                result = await session.execute(
                    select(TrainerProfile).where(
                        TrainerProfile.tenant_id == org_id,
                        TrainerProfile.is_locked.is_(True),
                    )
                )
                profiles = result.scalars().all()

            log.info("reindex.org", org_id=str(org_id), locked_count=len(profiles))

            for profile in profiles:
                if dry_run:
                    log.info(
                        "reindex.would_index",
                        profile_id=str(profile.id),
                        org_id=str(org_id),
                        niche=profile.niche,
                    )
                    skipped += 1
                    continue

                try:
                    await store.upsert_profile(
                        profile_id=profile.id,
                        org_id=org_id,
                        workspace_id=profile.workspace_id,
                        niche=profile.niche,
                        bio=profile.bio,
                        usp=profile.usp,
                        topics=list(profile.topics),
                        target_industries=list(profile.target_industries),
                        locked_at=profile.locked_at,
                    )
                    log.info("reindex.indexed", profile_id=str(profile.id), org_id=str(org_id))
                    indexed += 1
                except Exception:
                    log.error(
                        "reindex.failed",
                        profile_id=str(profile.id),
                        org_id=str(org_id),
                        exc_info=True,
                    )
                    failures += 1
    finally:
        await store.aclose()
        await engine.dispose()

    if dry_run:
        log.info("reindex.dry_run_complete", would_index=skipped)
    else:
        log.info("reindex.complete", indexed=indexed, failures=failures)

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reindex locked trainer profiles into Qdrant.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be indexed without writing to Qdrant.",
    )
    parser.add_argument(
        "--org-id",
        type=_uuid_mod.UUID,
        default=None,
        metavar="UUID",
        help="Limit reindexing to a single org (omit to process all active orgs).",
    )
    args = parser.parse_args()
    failures = asyncio.run(_run(dry_run=args.dry_run, org_id_filter=args.org_id))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
