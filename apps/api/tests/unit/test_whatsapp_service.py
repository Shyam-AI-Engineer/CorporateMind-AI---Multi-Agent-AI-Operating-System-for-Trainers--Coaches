"""Unit tests for WhatsAppService.

Covers:
  check_24h_window()
    - returns active WhatsAppSession when repo finds one
    - returns None when no active session exists
    - logs 'has_active_session=True' when session found
    - logs 'has_active_session=False' when no session
  get_approved_template()
    - returns WhatsAppTemplate when repo finds a match
    - returns None when template does not exist
    - forwards (name, language) to repo unchanged
    - default language is 'en'
  list_approved_templates()
    - returns empty list when no approved templates
    - returns all templates from repo
    - delegates once to repo.list_approved()
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.whatsapp.models import WhatsAppSession, WhatsAppTemplate
from corpmind.modules.whatsapp.service import WhatsAppService


TENANT_ID = uuid.uuid4()
CONTACT_ID = uuid.uuid4()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_service() -> WhatsAppService:
    return WhatsAppService(MagicMock())


def _mock_wa_session() -> WhatsAppSession:
    s = MagicMock(spec=WhatsAppSession)
    s.contact_id = CONTACT_ID
    s.is_active = True
    return s


def _mock_template(name: str = "hello_world", language: str = "en") -> WhatsAppTemplate:
    t = MagicMock(spec=WhatsAppTemplate)
    t.name = name
    t.language = language
    t.approval_status = "approved"
    return t


# ── check_24h_window ──────────────────────────────────────────────────────────

class TestCheck24hWindow:
    @pytest.mark.asyncio
    async def test_returns_active_session_when_found(self):
        svc = _make_service()
        active = _mock_wa_session()
        with patch.object(svc._session_repo, "find_active_session", AsyncMock(return_value=active)):
            result = await svc.check_24h_window(CONTACT_ID)
        assert result is active

    @pytest.mark.asyncio
    async def test_returns_none_when_no_active_session(self):
        svc = _make_service()
        with patch.object(svc._session_repo, "find_active_session", AsyncMock(return_value=None)):
            result = await svc.check_24h_window(CONTACT_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_logs_true_when_session_found(self):
        svc = _make_service()
        active = _mock_wa_session()
        with (
            patch.object(svc._session_repo, "find_active_session", AsyncMock(return_value=active)),
            patch("corpmind.modules.whatsapp.service.log") as mock_log,
        ):
            await svc.check_24h_window(CONTACT_ID)
        mock_log.info.assert_called_once()
        assert mock_log.info.call_args[1]["has_active_session"] is True

    @pytest.mark.asyncio
    async def test_logs_false_when_no_session(self):
        svc = _make_service()
        with (
            patch.object(svc._session_repo, "find_active_session", AsyncMock(return_value=None)),
            patch("corpmind.modules.whatsapp.service.log") as mock_log,
        ):
            await svc.check_24h_window(CONTACT_ID)
        assert mock_log.info.call_args[1]["has_active_session"] is False

    @pytest.mark.asyncio
    async def test_contact_id_passed_to_repo(self):
        svc = _make_service()
        mock_find = AsyncMock(return_value=None)
        with patch.object(svc._session_repo, "find_active_session", mock_find):
            await svc.check_24h_window(CONTACT_ID)
        mock_find.assert_called_once_with(CONTACT_ID)


# ── get_approved_template ─────────────────────────────────────────────────────

class TestGetApprovedTemplate:
    @pytest.mark.asyncio
    async def test_returns_template_when_found(self):
        svc = _make_service()
        template = _mock_template()
        with patch.object(svc._template_repo, "find_by_name_and_language", AsyncMock(return_value=template)):
            result = await svc.get_approved_template("hello_world", "en")
        assert result is template

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        svc = _make_service()
        with patch.object(svc._template_repo, "find_by_name_and_language", AsyncMock(return_value=None)):
            result = await svc.get_approved_template("nonexistent", "en")
        assert result is None

    @pytest.mark.asyncio
    async def test_forwards_name_and_language_to_repo(self):
        svc = _make_service()
        mock_find = AsyncMock(return_value=None)
        with patch.object(svc._template_repo, "find_by_name_and_language", mock_find):
            await svc.get_approved_template("promo_v2", "hi")
        mock_find.assert_called_once_with("promo_v2", "hi")

    @pytest.mark.asyncio
    async def test_default_language_is_en(self):
        svc = _make_service()
        mock_find = AsyncMock(return_value=None)
        with patch.object(svc._template_repo, "find_by_name_and_language", mock_find):
            await svc.get_approved_template("welcome")
        mock_find.assert_called_once_with("welcome", "en")


# ── list_approved_templates ───────────────────────────────────────────────────

class TestListApprovedTemplates:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none(self):
        svc = _make_service()
        with patch.object(svc._template_repo, "list_approved", AsyncMock(return_value=[])):
            result = await svc.list_approved_templates()
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_all_templates_from_repo(self):
        svc = _make_service()
        templates = [_mock_template("t1"), _mock_template("t2"), _mock_template("t3")]
        with patch.object(svc._template_repo, "list_approved", AsyncMock(return_value=templates)):
            result = await svc.list_approved_templates()
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_delegates_exactly_once_to_repo(self):
        svc = _make_service()
        mock_list = AsyncMock(return_value=[])
        with patch.object(svc._template_repo, "list_approved", mock_list):
            await svc.list_approved_templates()
        mock_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_result_identity_preserved(self):
        """Service must return exactly what repo returns — no wrapping."""
        svc = _make_service()
        templates = [_mock_template()]
        with patch.object(svc._template_repo, "list_approved", AsyncMock(return_value=templates)):
            result = await svc.list_approved_templates()
        assert result is templates
