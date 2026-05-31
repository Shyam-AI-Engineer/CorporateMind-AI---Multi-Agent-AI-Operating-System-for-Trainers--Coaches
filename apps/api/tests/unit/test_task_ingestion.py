"""Unit tests for workers/tasks/ingestion.py — ingest_trainer_upload + helpers."""

from __future__ import annotations

import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery.exceptions import Retry, SoftTimeLimitExceeded

from corpmind.workers.tasks.ingestion import (
    _make_task_key,
    _run_ingestion,
    ingest_trainer_upload,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ids(*, file_url: str = "https://cdn.example.com/poster.pdf", file_type: str = "pdf"):
    return {
        "file_url": file_url,
        "file_type": file_type,
        "workspace_id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "request_id": "req-ing-test",
    }


def _redis_mock(*, already_done: bool = False):
    r = MagicMock()
    r.get.return_value = "1" if already_done else None
    r.setex = MagicMock()
    r.close = MagicMock()
    return r


def _db_mocks():
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)
    mock_engine = AsyncMock()
    mock_engine.dispose = AsyncMock()
    return mock_engine, mock_factory, mock_session


# ── _make_task_key ─────────────────────────────────────────────────────────────

class TestMakeTaskKey:
    def test_deterministic_output(self):
        ws = str(uuid.uuid4())
        url = "https://cdn.example.com/file.pdf"
        key1 = _make_task_key(ws, url)
        key2 = _make_task_key(ws, url)
        assert key1 == key2

    def test_starts_with_workspace_id(self):
        ws = str(uuid.uuid4())
        key = _make_task_key(ws, "https://cdn.example.com/f.pdf")
        assert key.startswith(f"{ws}:")

    def test_different_urls_produce_different_keys(self):
        ws = str(uuid.uuid4())
        k1 = _make_task_key(ws, "https://cdn.example.com/a.pdf")
        k2 = _make_task_key(ws, "https://cdn.example.com/b.pdf")
        assert k1 != k2

    def test_digest_is_16_hex_chars(self):
        ws = str(uuid.uuid4())
        key = _make_task_key(ws, "https://cdn.example.com/x.pdf")
        digest_part = key.split(":")[1]
        assert len(digest_part) == 16
        int(digest_part, 16)  # should not raise

    def test_expected_hash_value(self):
        ws = "abc"
        url = "https://example.com/file.pdf"
        expected_digest = hashlib.sha256(f"{ws}:{url}".encode()).hexdigest()[:16]
        assert _make_task_key(ws, url) == f"{ws}:{expected_digest}"


# ── Sync wrapper: ingest_trainer_upload ────────────────────────────────────────
# For bind=True tasks .run() passes the task instance as self automatically.
# Use patch.object on the task to intercept retry calls.

class TestIngestTrainerUploadSyncWrapper:
    def test_duplicate_key_returns_early(self):
        r = _redis_mock(already_done=True)
        with patch("redis.from_url", return_value=r):
            result = ingest_trainer_upload.run(**_ids())
        assert result["status"] == "duplicate"
        r.close.assert_called_once()

    def test_soft_timeout_retries_with_countdown(self):
        r = _redis_mock()
        with patch.object(ingest_trainer_upload, "retry", side_effect=Retry()) as mock_retry:
            with patch("redis.from_url", return_value=r):
                with patch("asyncio.run", side_effect=SoftTimeLimitExceeded()):
                    with pytest.raises(Retry):
                        ingest_trainer_upload.run(**_ids())
        mock_retry.assert_called_once_with(countdown=30)

    def test_not_implemented_returns_unsupported_without_retry(self):
        r = _redis_mock()
        with patch.object(ingest_trainer_upload, "retry") as mock_retry:
            with patch("redis.from_url", return_value=r):
                with patch("asyncio.run", side_effect=NotImplementedError("video not yet supported")):
                    result = ingest_trainer_upload.run(**_ids(file_type="video"))
        assert result["status"] == "unsupported"
        mock_retry.assert_not_called()

    def test_generic_exception_retries(self):
        r = _redis_mock()
        err = RuntimeError("S3 timeout")
        with patch.object(ingest_trainer_upload, "retry", side_effect=Retry()) as mock_retry:
            with patch("redis.from_url", return_value=r):
                with patch("asyncio.run", side_effect=err):
                    with pytest.raises(Retry):
                        ingest_trainer_upload.run(**_ids())
        mock_retry.assert_called_once_with(exc=err)

    def test_success_sets_done_key_in_redis(self):
        r1 = _redis_mock()  # first call — idempotency check
        r2 = _redis_mock()  # second call — mark done
        success_result = {"status": "complete", "profile_id": str(uuid.uuid4()),
                          "workspace_id": str(uuid.uuid4()), "extracted_chars": 1234}
        redis_calls = iter([r1, r2])
        with patch("redis.from_url", side_effect=lambda *a, **kw: next(redis_calls)):
            with patch("asyncio.run", return_value=success_result):
                result = ingest_trainer_upload.run(**_ids())
        assert result["status"] == "complete"
        r2.setex.assert_called_once()
        args = r2.setex.call_args[0]
        assert args[1] == 86400


# ── Async body: _run_ingestion ─────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRunIngestion:
    async def test_success_returns_complete_with_profile_id(self):
        mock_engine, mock_factory, mock_session = _db_mocks()

        profile_out = MagicMock()
        profile_out.id = uuid.uuid4()

        mock_pipeline = AsyncMock()
        mock_pipeline.run.return_value = "extracted trainer text"

        mock_svc = AsyncMock()
        mock_svc.extract_from_text.return_value = profile_out

        ids = _ids()
        ws_id = uuid.UUID(ids["workspace_id"])
        t_id = uuid.UUID(ids["tenant_id"])
        u_id = uuid.UUID(ids["user_id"])

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.ingestion.pipeline.IngestPipeline", return_value=mock_pipeline),
            patch("corpmind.modules.trainer_intel.service.TrainerIntelService", return_value=mock_svc),
        ):
            result = await _run_ingestion(
                file_url=ids["file_url"],
                file_type=ids["file_type"],
                workspace_id=ws_id,
                tenant_id=t_id,
                user_id=u_id,
                request_id=ids["request_id"],
            )

        assert result["status"] == "complete"
        assert result["profile_id"] == str(profile_out.id)
        assert result["extracted_chars"] == len("extracted trainer text")

    async def test_tenant_context_cleared_on_exception(self):
        mock_engine, mock_factory, _ = _db_mocks()

        mock_pipeline = AsyncMock()
        mock_pipeline.run.side_effect = RuntimeError("OCR failed")

        ids = _ids()
        ws_id = uuid.UUID(ids["workspace_id"])
        t_id = uuid.UUID(ids["tenant_id"])
        u_id = uuid.UUID(ids["user_id"])

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="mytoken"),
            patch("corpmind.core.tenancy.clear_tenant_context") as mock_clear,
            patch("corpmind.ingestion.pipeline.IngestPipeline", return_value=mock_pipeline),
        ):
            with pytest.raises(RuntimeError):
                await _run_ingestion(
                    file_url=ids["file_url"],
                    file_type=ids["file_type"],
                    workspace_id=ws_id,
                    tenant_id=t_id,
                    user_id=u_id,
                    request_id=ids["request_id"],
                )

        mock_clear.assert_called_once_with("mytoken")
