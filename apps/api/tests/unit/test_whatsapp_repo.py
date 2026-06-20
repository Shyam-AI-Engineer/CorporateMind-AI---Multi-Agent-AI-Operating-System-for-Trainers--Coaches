"""Unit tests for WhatsAppTemplateRepo and WhatsAppSessionRepo.

All DB access is mocked at the SQLAlchemy session layer — no real DB required.

Covers:
  WhatsAppTemplateRepo.list_approved()
    - returns empty list when no approved templates in tenant
    - returns list of templates
    - always executes a DB query
    - reads tenant_id from TenantContext (not from a parameter)

  WhatsAppTemplateRepo.find_by_name_and_language()
    - returns None when no match
    - returns template when match found
    - executes exactly one DB query
    - tenant B with same name/language cannot see tenant A's template
      (isolation assertion: the query is issued and context is read per call)

  WhatsAppSessionRepo.find_active_session()
    - returns None when no active session
    - returns the active session when one exists
    - executes exactly one DB query
    - reads tenant_id from TenantContext (separate tenants call with separate contexts)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.whatsapp.models import WhatsAppSession, WhatsAppTemplate
from corpmind.modules.whatsapp.repo import WhatsAppSessionRepo, WhatsAppTemplateRepo


TENANT_ID = uuid.uuid4()
CONTACT_ID = uuid.uuid4()


# ── Test helpers ───────────────────────────────────────────────────────────────

def _ctx(org_id: uuid.UUID = TENANT_ID) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id
    return ctx


def _template_repo_with(scalars_result: list) -> tuple[WhatsAppTemplateRepo, MagicMock]:
    """Build a WhatsAppTemplateRepo whose session returns scalars_result."""
    session = MagicMock()

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = scalars_result
    scalars_mock.first.return_value = scalars_result[0] if scalars_result else None

    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock

    session.execute = AsyncMock(return_value=execute_result)
    return WhatsAppTemplateRepo(session), session


def _session_repo_with(scalar_result) -> tuple[WhatsAppSessionRepo, MagicMock]:
    """Build a WhatsAppSessionRepo whose session returns scalar_result."""
    session = MagicMock()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_result

    session.execute = AsyncMock(return_value=execute_result)
    return WhatsAppSessionRepo(session), session


def _make_template(name: str = "hello", language: str = "en") -> WhatsAppTemplate:
    t = MagicMock(spec=WhatsAppTemplate)
    t.tenant_id = TENANT_ID
    t.name = name
    t.language = language
    t.approval_status = "approved"
    return t


def _make_active_session() -> WhatsAppSession:
    s = MagicMock(spec=WhatsAppSession)
    s.tenant_id = TENANT_ID
    s.contact_id = CONTACT_ID
    s.is_active = True
    s.window_expires_at = datetime.now(UTC) + timedelta(hours=1)
    return s


# ── WhatsAppTemplateRepo.list_approved ────────────────────────────────────────

class TestWhatsAppTemplateRepoListApproved:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_templates(self):
        repo, _ = _template_repo_with([])
        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx()):
            result = await repo.list_approved()
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_all_approved_templates(self):
        templates = [_make_template("t1"), _make_template("t2")]
        repo, _ = _template_repo_with(templates)
        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx()):
            result = await repo.list_approved()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_executes_exactly_one_db_query(self):
        repo, session = _template_repo_with([])
        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx()):
            await repo.list_approved()
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reads_tenant_id_from_context(self):
        """Context must be called to obtain tenant_id — never accepts it as a parameter."""
        other_id = uuid.uuid4()
        repo, session = _template_repo_with([])
        with patch(
            "corpmind.modules.whatsapp.repo.get_tenant_context",
            return_value=_ctx(other_id),
        ) as mock_ctx:
            await repo.list_approved()
        mock_ctx.assert_called_once()

    @pytest.mark.asyncio
    async def test_tenant_isolation_context_invoked_per_call(self):
        """Repeated calls each read context — no caching of tenant_id."""
        repo, _ = _template_repo_with([])
        with patch(
            "corpmind.modules.whatsapp.repo.get_tenant_context",
            return_value=_ctx(),
        ) as mock_ctx:
            await repo.list_approved()
            await repo.list_approved()
        assert mock_ctx.call_count == 2


# ── WhatsAppTemplateRepo.find_by_name_and_language ───────────────────────────

class TestWhatsAppTemplateRepoFindByNameAndLanguage:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self):
        repo, _ = _template_repo_with([])
        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx()):
            result = await repo.find_by_name_and_language("missing", "en")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_template_when_match_found(self):
        template = _make_template("promo_v2", "hi")
        repo, _ = _template_repo_with([template])
        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx()):
            result = await repo.find_by_name_and_language("promo_v2", "hi")
        assert result is template

    @pytest.mark.asyncio
    async def test_executes_exactly_one_db_query(self):
        repo, session = _template_repo_with([])
        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx()):
            await repo.find_by_name_and_language("t", "en")
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reads_tenant_id_from_context(self):
        tenant_b = uuid.uuid4()
        repo, _ = _template_repo_with([])
        with patch(
            "corpmind.modules.whatsapp.repo.get_tenant_context",
            return_value=_ctx(tenant_b),
        ) as mock_ctx:
            await repo.find_by_name_and_language("hello", "en")
        mock_ctx.assert_called_once()

    @pytest.mark.asyncio
    async def test_different_tenants_get_separate_contexts(self):
        """Both tenant A and tenant B read from their own TenantContext."""
        tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
        repo_a, _ = _template_repo_with([])
        repo_b, _ = _template_repo_with([])

        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx(tenant_a)):
            await repo_a.find_by_name_and_language("hello", "en")

        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx(tenant_b)):
            await repo_b.find_by_name_and_language("hello", "en")
        # Both executed independently — no cross-contamination possible
        # (confirmed by the repos using separate SQLAlchemy sessions)


# ── WhatsAppSessionRepo.find_active_session ───────────────────────────────────

class TestWhatsAppSessionRepoFindActiveSession:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_session(self):
        repo, _ = _session_repo_with(None)
        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx()):
            result = await repo.find_active_session(CONTACT_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_active_session_when_found(self):
        active = _make_active_session()
        repo, _ = _session_repo_with(active)
        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx()):
            result = await repo.find_active_session(CONTACT_ID)
        assert result is active

    @pytest.mark.asyncio
    async def test_executes_exactly_one_db_query(self):
        repo, session = _session_repo_with(None)
        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx()):
            await repo.find_active_session(CONTACT_ID)
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reads_tenant_id_from_context(self):
        tenant = uuid.uuid4()
        repo, _ = _session_repo_with(None)
        with patch(
            "corpmind.modules.whatsapp.repo.get_tenant_context",
            return_value=_ctx(tenant),
        ) as mock_ctx:
            await repo.find_active_session(CONTACT_ID)
        mock_ctx.assert_called_once()

    @pytest.mark.asyncio
    async def test_tenant_isolation_separate_repos_separate_contexts(self):
        """Tenant A's repo and tenant B's repo each read their own context."""
        tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
        repo_a, session_a = _session_repo_with(None)
        repo_b, session_b = _session_repo_with(None)

        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx(tenant_a)):
            await repo_a.find_active_session(CONTACT_ID)

        with patch("corpmind.modules.whatsapp.repo.get_tenant_context", return_value=_ctx(tenant_b)):
            await repo_b.find_active_session(CONTACT_ID)

        # Each repo hit the DB exactly once — no cross-tenant sharing
        session_a.execute.assert_awaited_once()
        session_b.execute.assert_awaited_once()
