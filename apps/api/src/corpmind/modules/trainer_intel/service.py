"""Trainer intelligence service.

Phase 1 surface:
- extract_from_text(): given raw text, calls EuriClient with task="trainer_extraction",
  parses the JSON response, persists/updates the workspace's TrainerProfile.
- get_profile(), update_profile(), lock_profile(): CRUD against the locked-or-draft profile.

Upload + OCR/transcription paths arrive in Phase 2 via the ingestion module — at which
point they will produce text and call extract_from_text() under the hood.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import structlog
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.ai.euri_client import EuriClient
from corpmind.ai.trainer_vector_store import TrainerVectorStore
from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.trainer_intel.repo import TrainerProfileRepo
from corpmind.modules.trainer_intel.schemas import (
    TrainerProfileExtraction,
    TrainerProfileOut,
    TrainerProfileUpdate,
)

log = structlog.get_logger(__name__)


class TrainerIntelService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TrainerProfileRepo(session)
        self._llm = EuriClient(session=session)

    async def extract_from_text(self, content: str) -> TrainerProfileOut:
        ctx = get_tenant_context()
        existing = await self._repo.find_for_workspace(ctx.workspace_id)
        if existing and existing.is_locked:
            raise ConflictError("Trainer profile is locked; unlock before re-extracting.")

        result = await self._llm.chat(
            task="trainer_extraction",
            prompt_name="trainer.extraction",
            prompt_inputs={"content": content},
            tenant_id=ctx.org_id,
            request_id=ctx.request_id,
            agent="trainer_intel_service",
        )

        extraction = self._parse_extraction(result["content"])
        profile = await self._repo.upsert_extraction(
            workspace_id=ctx.workspace_id,
            fields=extraction.model_dump(),
            extraction_metadata={
                "source": "pasted_text",
                "extracted_at": datetime.now(UTC).isoformat(),
                "request_id": ctx.request_id,
            },
        )
        await self._session.commit()
        log.info(
            "trainer_intel.extracted",
            profile_id=str(profile.id),
            workspace_id=str(ctx.workspace_id),
        )
        return TrainerProfileOut.model_validate(profile)

    async def get_profile(self) -> TrainerProfileOut:
        ctx = get_tenant_context()
        profile = await self._repo.find_for_workspace(ctx.workspace_id)
        if profile is None:
            raise NotFoundError("No trainer profile for this workspace.")
        return TrainerProfileOut.model_validate(profile)

    async def update_profile(self, update: TrainerProfileUpdate) -> TrainerProfileOut:
        ctx = get_tenant_context()
        profile = await self._repo.find_for_workspace(ctx.workspace_id)
        if profile is None:
            raise NotFoundError("No trainer profile to update.")
        if profile.is_locked:
            raise ConflictError("Profile is locked; unlock before editing.")

        for key, value in update.model_dump(exclude_unset=True).items():
            setattr(profile, key, value)
        await self._session.commit()
        return TrainerProfileOut.model_validate(profile)

    async def lock_profile(self) -> TrainerProfileOut:
        ctx = get_tenant_context()
        profile = await self._repo.find_for_workspace(ctx.workspace_id)
        if profile is None:
            raise NotFoundError("No trainer profile to lock.")
        if profile.is_locked:
            raise ConflictError("Profile is already locked.")
        missing: list[str] = []
        if not profile.niche:
            missing.append("niche")
        if not profile.bio:
            missing.append("bio")
        if not profile.topics:
            missing.append("topics")
        if missing:
            raise ValidationError(
                f"Profile is missing required fields: {', '.join(missing)}. "
                "Please fill them in before locking."
            )
        profile.is_locked = True
        profile.locked_at = datetime.now(UTC)
        await self._session.commit()
        log.info("trainer_intel.locked", profile_id=str(profile.id))

        # Index into Qdrant for outreach personalization.
        # Runs after commit so the DB lock is durable regardless of Qdrant state.
        try:
            store = TrainerVectorStore()
            await store.upsert_profile(
                profile_id=profile.id,
                org_id=ctx.org_id,
                workspace_id=profile.workspace_id,
                niche=profile.niche,
                bio=profile.bio,
                usp=profile.usp,
                topics=list(profile.topics),
                target_industries=list(profile.target_industries),
                locked_at=profile.locked_at,
            )
            await store.aclose()
        except Exception:
            log.warning(
                "trainer_intel.vector_index_failed",
                profile_id=str(profile.id),
                exc_info=True,
            )

        return TrainerProfileOut.model_validate(profile)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _parse_extraction(self, raw: str) -> TrainerProfileExtraction:
        """Parse a model JSON response.

        Models sometimes wrap JSON in ```json fences despite explicit prompt rules;
        strip them defensively before parsing.
        """
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].lstrip()
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Trainer extraction returned non-JSON: {exc}") from exc
        try:
            return TrainerProfileExtraction.model_validate(payload)
        except PydanticValidationError as exc:
            raise ValidationError(f"Trainer extraction failed schema: {exc}") from exc
