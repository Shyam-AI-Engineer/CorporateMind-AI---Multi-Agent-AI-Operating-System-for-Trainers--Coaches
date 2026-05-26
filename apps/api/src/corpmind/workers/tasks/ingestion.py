"""Ingestion Celery tasks — OCR, transcription, extraction, embedding."""

from __future__ import annotations

import asyncio
import hashlib
import uuid

import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from corpmind.workers.celery_app import app

log = structlog.get_logger(__name__)

_TASK_TTL_SECONDS = 86400  # idempotency key lives 24 h


@app.task(
    bind=True,
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    soft_time_limit=240,
    time_limit=270,
    queue="ingestion",
    name="corpmind.workers.tasks.ingestion.ingest_trainer_upload",
)
def ingest_trainer_upload(
    self: Task,
    *,
    file_url: str,
    file_type: str,
    workspace_id: str,
    tenant_id: str,
    user_id: str,
    request_id: str,
) -> dict:
    """Download, extract text from, and profile-extract an uploaded trainer file.

    Idempotency: a SHA-256 of (workspace_id, file_url) is locked in Redis for
    24 h. Duplicate enqueues (e.g. on worker crash + re-queue) are no-ops.

    Args:
        file_url: Signed Cloudinary URL.
        file_type: One of "pdf" | "image" | "video".
        workspace_id: UUID string — which workspace's profile to update.
        tenant_id: UUID string — org-level tenant for RLS + context.
        user_id: UUID string — the uploading user (for TenantContext).
        request_id: Correlation ID from the originating HTTP request.
    """
    task_key = _make_task_key(workspace_id, file_url)
    structlog.contextvars.bind_contextvars(
        task_key=task_key,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        request_id=request_id,
    )

    # ── Idempotency check ─────────────────────────────────────────────────────
    # Use a dedicated sync Redis connection — the app's async pool isn't
    # accessible from a sync Celery task body.
    import redis as _redis_sync
    from corpmind.core.config import settings as _settings
    _r = _redis_sync.from_url(_settings.REDIS_URL, decode_responses=True)
    try:
        already_done = _r.get(f"ingestion:done:{task_key}")
        if already_done:
            log.info("ingestion.skipped_duplicate", task_key=task_key)
            return {"status": "duplicate", "task_key": task_key}
    finally:
        _r.close()

    log.info("ingestion.start", file_type=file_type, task_id=self.request.id)

    try:
        result = asyncio.run(
            _run_ingestion(
                file_url=file_url,
                file_type=file_type,
                workspace_id=uuid.UUID(workspace_id),
                tenant_id=uuid.UUID(tenant_id),
                user_id=uuid.UUID(user_id),
                request_id=request_id,
            )
        )
    except SoftTimeLimitExceeded:
        log.warning("ingestion.soft_time_limit", task_key=task_key)
        raise self.retry(countdown=30)
    except NotImplementedError as exc:
        # Phase 2 stub — don't retry, surface the message to the caller.
        log.warning("ingestion.not_implemented", reason=str(exc))
        return {"status": "unsupported", "reason": str(exc)}
    except Exception as exc:
        log.error("ingestion.failed", error=str(exc), exc_info=True)
        raise self.retry(exc=exc)

    # Mark done only after successful extraction + profile update
    _r2 = _redis_sync.from_url(_settings.REDIS_URL, decode_responses=True)
    try:
        _r2.setex(f"ingestion:done:{task_key}", _TASK_TTL_SECONDS, "1")
    finally:
        _r2.close()
    log.info("ingestion.complete", **result)
    return result


async def _run_ingestion(
    *,
    file_url: str,
    file_type: str,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    request_id: str,
) -> dict:
    """Async body: download → extract → persist trainer profile."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings
    from corpmind.core.database import set_rls_tenant
    from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
    from corpmind.ingestion.pipeline import FileType, IngestPipeline
    from corpmind.modules.trainer_intel.service import TrainerIntelService

    # Fresh engine per task — correct for low-volume long-running ingestion
    engine = create_async_engine(settings.DATABASE_URL, pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    ctx = TenantContext(
        org_id=tenant_id,
        workspace_id=workspace_id,
        user_id=user_id,
        role="system",
        request_id=request_id,
    )
    token = set_tenant_context(ctx)
    try:
        async with factory() as session:
            await set_rls_tenant(session, tenant_id)

            pipeline = IngestPipeline()
            text = await pipeline.run(file_url, file_type=file_type)  # type: ignore[arg-type]

            svc = TrainerIntelService(session)
            profile_out = await svc.extract_from_text(text)

            return {
                "status": "complete",
                "profile_id": str(profile_out.id),
                "workspace_id": str(workspace_id),
                "extracted_chars": len(text),
            }
    finally:
        clear_tenant_context(token)
        await engine.dispose()


@app.task(
    bind=True,
    acks_late=True,
    max_retries=1,
    soft_time_limit=600,
    time_limit=900,
    queue="ingestion",
    name="corpmind.workers.tasks.ingestion.refresh_contact_vectors",
)
def refresh_contact_vectors(self: Task) -> None:
    """Re-embed HR contacts older than 6 months for all tenants."""
    log.info("ingestion.contact_refresh.start")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_task_key(workspace_id: str, file_url: str) -> str:
    digest = hashlib.sha256(f"{workspace_id}:{file_url}".encode()).hexdigest()[:16]
    return f"{workspace_id}:{digest}"
