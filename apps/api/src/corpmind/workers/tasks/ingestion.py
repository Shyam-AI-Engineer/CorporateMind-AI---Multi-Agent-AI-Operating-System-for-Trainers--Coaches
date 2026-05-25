"""Ingestion Celery tasks — OCR, transcription, embedding."""

from __future__ import annotations

import structlog
from celery import Task

from corpmind.workers.celery_app import app

log = structlog.get_logger(__name__)


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    retry_backoff=True,
    soft_time_limit=270,
    time_limit=300,
    queue="ingestion",
    name="corpmind.workers.tasks.ingestion.ingest_uploaded_file",
)
def ingest_uploaded_file(
    self: Task,
    *,
    file_url: str,
    file_type: str,
    workspace_id: str,
    tenant_id: str,
) -> dict:
    """OCR/transcribe/parse an uploaded file and embed into Qdrant."""
    task_key = f"ingestion:{workspace_id}:{file_url}"
    log.info("ingestion.start", task_key=task_key, file_type=file_type)
    # TODO(Phase 1): route to OCR / Whisper / PDF parser based on file_type
    return {"status": "complete"}


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
