"""Unit tests for IngestPipeline and individual extractors.

No real HTTP calls (respx mocks httpx), no real PDFs (PdfReader mocked),
no real vision API (EuriHTTPProvider mocked).

Coverage targets:
  IngestPipeline._validate_url_host  — scheme + host allow-list
  IngestPipeline._validate_mime      — MIME allow-list per file_type
  IngestPipeline._download           — content-length guard, chunked size
                                       guard, HTTP error propagation
  IngestPipeline.run                 — routes pdf/image/video correctly
  extract_pdf                        — happy path, encrypted, empty, truncation
  extract_image                      — delegates to vision, truncates
  extract_video                      — raises NotImplementedError (Phase 2 stub)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from corpmind.core.exceptions import ValidationError
from corpmind.ingestion.extractors import (
    MAX_CHARS,
    extract_image,
    extract_pdf,
    extract_video,
)
from corpmind.ingestion.pipeline import IngestPipeline


# ── _validate_url_host ────────────────────────────────────────────────────────

class TestValidateUrlHost:
    def test_rejects_ftp_scheme(self) -> None:
        with pytest.raises(ValidationError, match="http"):
            IngestPipeline()._validate_url_host("ftp://res.cloudinary.com/file.pdf")

    def test_rejects_non_cloudinary_host(self) -> None:
        with pytest.raises(ValidationError, match="not a permitted"):
            IngestPipeline()._validate_url_host("https://s3.amazonaws.com/bucket/file.pdf")

    def test_rejects_arbitrary_domain(self) -> None:
        with pytest.raises(ValidationError, match="not a permitted"):
            IngestPipeline()._validate_url_host("https://evil.example.com/file.pdf")

    def test_accepts_res_cloudinary_com(self) -> None:
        IngestPipeline()._validate_url_host("https://res.cloudinary.com/demo/image/upload/sample.jpg")

    def test_accepts_cloudinary_com(self) -> None:
        IngestPipeline()._validate_url_host("https://cloudinary.com/demo/file.pdf")

    def test_accepts_subdomain_of_res_cloudinary_com(self) -> None:
        IngestPipeline()._validate_url_host("https://foo.res.cloudinary.com/file.pdf")

    def test_accepts_http_scheme(self) -> None:
        # http is explicitly allowed (though prod URLs are https)
        IngestPipeline()._validate_url_host("http://res.cloudinary.com/file.pdf")


# ── _validate_mime ────────────────────────────────────────────────────────────

class TestValidateMime:
    def test_pdf_accepts_application_pdf(self) -> None:
        IngestPipeline()._validate_mime("application/pdf", "pdf", "url")

    def test_pdf_rejects_image_jpeg(self) -> None:
        with pytest.raises(ValidationError, match="MIME"):
            IngestPipeline()._validate_mime("image/jpeg", "pdf", "url")

    def test_image_accepts_jpeg(self) -> None:
        IngestPipeline()._validate_mime("image/jpeg", "image", "url")

    def test_image_accepts_png(self) -> None:
        IngestPipeline()._validate_mime("image/png", "image", "url")

    def test_image_rejects_pdf(self) -> None:
        with pytest.raises(ValidationError, match="MIME"):
            IngestPipeline()._validate_mime("application/pdf", "image", "url")

    def test_video_accepts_mp4(self) -> None:
        IngestPipeline()._validate_mime("video/mp4", "video", "url")

    def test_video_accepts_audio_mpeg(self) -> None:
        IngestPipeline()._validate_mime("audio/mpeg", "video", "url")


# ── _download ─────────────────────────────────────────────────────────────────

class TestDownload:
    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_when_content_length_exceeds_limit(self) -> None:
        url = "https://res.cloudinary.com/demo/file.pdf"
        # 51 MB declared in Content-Length header
        respx.get(url).mock(return_value=httpx.Response(
            200,
            content=b"x",
            headers={"content-type": "application/pdf", "content-length": str(51 * 1024 * 1024)},
        ))
        with pytest.raises(ValidationError, match="too large"):
            await IngestPipeline()._download(url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_when_streamed_bytes_exceed_limit(self) -> None:
        url = "https://res.cloudinary.com/demo/file.pdf"
        # No content-length header; body exceeds limit during streaming
        big_body = b"x" * (51 * 1024 * 1024)
        # Set content-length to "0" so the header guard is bypassed and
        # the streaming accumulation guard ("limit during download") fires.
        respx.get(url).mock(return_value=httpx.Response(
            200,
            content=big_body,
            headers={"content-type": "application/pdf", "content-length": "0"},
        ))
        with pytest.raises(ValidationError, match="limit during download"):
            await IngestPipeline()._download(url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_on_http_4xx(self) -> None:
        url = "https://res.cloudinary.com/demo/missing.pdf"
        respx.get(url).mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            await IngestPipeline()._download(url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_content_and_mime_on_success(self) -> None:
        url = "https://res.cloudinary.com/demo/file.pdf"
        respx.get(url).mock(return_value=httpx.Response(
            200,
            content=b"PDF bytes",
            headers={"content-type": "application/pdf; charset=utf-8"},
        ))
        content, mime = await IngestPipeline()._download(url)
        assert content == b"PDF bytes"
        assert mime == "application/pdf"  # charset stripped


# ── extract_pdf ───────────────────────────────────────────────────────────────

class TestExtractPdf:
    def _mock_reader(self, *, pages: list[str], encrypted: bool = False) -> MagicMock:
        mock_pages = []
        for text in pages:
            page = MagicMock()
            page.extract_text.return_value = text
            mock_pages.append(page)
        reader = MagicMock()
        reader.is_encrypted = encrypted
        reader.pages = mock_pages
        return reader

    def test_happy_path_returns_page_text(self) -> None:
        reader = self._mock_reader(pages=["Hello from page 1", "Hello from page 2"])
        with patch("pypdf.PdfReader", return_value=reader):
            result = extract_pdf(b"fake-pdf")
        assert "Hello from page 1" in result
        assert "Hello from page 2" in result

    def test_raises_for_encrypted_pdf(self) -> None:
        reader = self._mock_reader(pages=[], encrypted=True)
        with patch("pypdf.PdfReader", return_value=reader):
            with pytest.raises(ValidationError, match="Encrypted"):
                extract_pdf(b"fake-pdf")

    def test_raises_when_no_extractable_text(self) -> None:
        reader = self._mock_reader(pages=["", "   ", ""])
        with patch("pypdf.PdfReader", return_value=reader):
            with pytest.raises(ValidationError, match="no extractable text"):
                extract_pdf(b"fake-pdf")

    def test_truncates_at_max_chars(self) -> None:
        long_text = "A" * (MAX_CHARS + 500)
        reader = self._mock_reader(pages=[long_text])
        with patch("pypdf.PdfReader", return_value=reader):
            result = extract_pdf(b"fake-pdf")
        assert len(result) == MAX_CHARS

    def test_raises_on_corrupt_pdf(self) -> None:
        from pypdf.errors import PdfReadError
        with patch(
            "pypdf.PdfReader",
            side_effect=PdfReadError("corrupt"),
        ):
            with pytest.raises(ValidationError, match="Cannot read PDF"):
                extract_pdf(b"not-a-pdf")

    def test_pages_capped_at_max_pdf_pages(self) -> None:
        # 60 pages; only first 50 should be read
        pages = [f"Page {i}" for i in range(60)]
        reader = self._mock_reader(pages=pages)
        with patch("pypdf.PdfReader", return_value=reader):
            result = extract_pdf(b"fake-pdf")
        # "Page 50" should not appear (only pages 0-49)
        assert "Page 50" not in result
        assert "Page 49" in result


# ── extract_image ─────────────────────────────────────────────────────────────

class TestExtractImage:
    @pytest.mark.asyncio
    async def test_delegates_to_vision_describe(self) -> None:
        mock_provider = AsyncMock()
        mock_provider.vision_describe = AsyncMock(return_value="Extracted OCR text from image")
        mock_provider.aclose = AsyncMock()

        with patch("corpmind.ai.providers.euri_http.EuriHTTPProvider", return_value=mock_provider):
            result = await extract_image("https://res.cloudinary.com/demo/image.jpg")

        mock_provider.vision_describe.assert_awaited_once()
        call_args = mock_provider.vision_describe.await_args
        assert call_args.args[0] == "https://res.cloudinary.com/demo/image.jpg"
        assert "OCR" in call_args.kwargs.get("instruction", "")
        assert result == "Extracted OCR text from image"

    @pytest.mark.asyncio
    async def test_truncates_at_max_chars(self) -> None:
        long_text = "Z" * (MAX_CHARS + 1_000)
        mock_provider = AsyncMock()
        mock_provider.vision_describe = AsyncMock(return_value=long_text)
        mock_provider.aclose = AsyncMock()

        with patch("corpmind.ai.providers.euri_http.EuriHTTPProvider", return_value=mock_provider):
            result = await extract_image("https://res.cloudinary.com/demo/image.png")

        assert len(result) == MAX_CHARS

    @pytest.mark.asyncio
    async def test_closes_provider_even_on_exception(self) -> None:
        mock_provider = AsyncMock()
        mock_provider.vision_describe = AsyncMock(side_effect=RuntimeError("API down"))
        mock_provider.aclose = AsyncMock()

        with patch("corpmind.ai.providers.euri_http.EuriHTTPProvider", return_value=mock_provider):
            with pytest.raises(RuntimeError):
                await extract_image("https://res.cloudinary.com/demo/image.jpg")

        mock_provider.aclose.assert_awaited_once()


# ── extract_video ─────────────────────────────────────────────────────────────

class TestExtractVideo:
    @pytest.mark.asyncio
    async def test_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="Phase 2"):
            await extract_video("https://res.cloudinary.com/demo/video.mp4")


# ── IngestPipeline.run (end-to-end routing) ───────────────────────────────────

class TestIngestPipelineRun:
    @pytest.mark.asyncio
    @respx.mock
    async def test_pdf_route_downloads_then_extracts(self) -> None:
        url = "https://res.cloudinary.com/demo/brochure.pdf"
        respx.get(url).mock(return_value=httpx.Response(
            200,
            content=b"fake-pdf-bytes",
            headers={"content-type": "application/pdf"},
        ))
        reader = MagicMock()
        reader.is_encrypted = False
        page = MagicMock()
        page.extract_text.return_value = "Trainer brochure content"
        reader.pages = [page]

        with patch("pypdf.PdfReader", return_value=reader):
            result = await IngestPipeline().run(url, "pdf")

        assert "Trainer brochure content" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_image_route_downloads_then_calls_vision(self) -> None:
        url = "https://res.cloudinary.com/demo/poster.jpg"
        respx.get(url).mock(return_value=httpx.Response(
            200,
            content=b"fake-image-bytes",
            headers={"content-type": "image/jpeg"},
        ))
        mock_provider = AsyncMock()
        mock_provider.vision_describe = AsyncMock(return_value="Poster OCR text")
        mock_provider.aclose = AsyncMock()

        with patch("corpmind.ai.providers.euri_http.EuriHTTPProvider", return_value=mock_provider):
            result = await IngestPipeline().run(url, "image")

        assert result == "Poster OCR text"

    @pytest.mark.asyncio
    async def test_video_route_raises_not_implemented_without_downloading(self) -> None:
        # Video should NOT attempt a download — it should go straight to extract_video
        url = "https://res.cloudinary.com/demo/video.mp4"
        with pytest.raises(NotImplementedError):
            await IngestPipeline().run(url, "video")

    @pytest.mark.asyncio
    async def test_rejects_non_cloudinary_url(self) -> None:
        with pytest.raises(ValidationError, match="not a permitted"):
            await IngestPipeline().run("https://evil.example.com/file.pdf", "pdf")

    @pytest.mark.asyncio
    @respx.mock
    async def test_rejects_mime_mismatch(self) -> None:
        url = "https://res.cloudinary.com/demo/file.pdf"
        respx.get(url).mock(return_value=httpx.Response(
            200,
            content=b"HTML page",
            headers={"content-type": "text/html"},
        ))
        with pytest.raises(ValidationError, match="MIME"):
            await IngestPipeline().run(url, "pdf")
