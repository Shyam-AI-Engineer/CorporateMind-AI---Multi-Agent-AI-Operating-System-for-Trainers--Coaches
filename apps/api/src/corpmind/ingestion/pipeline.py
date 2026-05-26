"""IngestPipeline — download, validate, and extract text from an uploaded file URL.

Responsibilities (in order):
  1. Download from Cloudinary-signed URL (max 50 MB, 30s timeout).
  2. Validate MIME type against declared file_type.
  3. Route to the appropriate extractor.
  4. Return extracted plain text (≤ MAX_CHARS).
"""

from __future__ import annotations

import hashlib
from typing import Literal

import httpx
import structlog

from corpmind.core.exceptions import ValidationError
from corpmind.ingestion.extractors import extract_image, extract_pdf, extract_video

log = structlog.get_logger(__name__)

FileType = Literal["pdf", "image", "video"]

_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

_MIME_ALLOW: dict[FileType, frozenset[str]] = {
    "pdf": frozenset({"application/pdf"}),
    "image": frozenset({
        "image/jpeg", "image/png", "image/webp", "image/gif", "image/tiff",
    }),
    "video": frozenset({
        "video/mp4", "video/quicktime", "video/webm", "video/x-msvideo",
        "audio/mpeg", "audio/mp4", "audio/wav",
    }),
}

# Cloudinary CDN domains — only allow URLs from these hosts.
_ALLOWED_HOSTS = frozenset({
    "res.cloudinary.com",
    "cloudinary.com",
})


class IngestPipeline:
    """Download and extract text from an uploaded file URL."""

    async def run(self, url: str, file_type: FileType) -> str:
        """Return extracted plain text from the file at `url`.

        Args:
            url: A signed Cloudinary URL.
            file_type: Caller-declared type; validated against actual MIME.

        Returns:
            Plain text, ≤ MAX_CHARS characters.

        Raises:
            ValidationError: Bad URL host, MIME mismatch, size exceeded, or
                             extractor failure.
        """
        self._validate_url_host(url)

        if file_type == "video":
            # Video doesn't need to be downloaded before extracting —
            # Whisper (Phase 2) will stream the URL directly.
            return await extract_video(url)

        content, detected_mime = await self._download(url)
        self._validate_mime(detected_mime, file_type, url)

        if file_type == "pdf":
            text = extract_pdf(content)
        else:
            text = await extract_image(url)

        sha = hashlib.sha256(content).hexdigest()[:12]
        log.info(
            "ingestion.pipeline.complete",
            file_type=file_type,
            bytes=len(content),
            sha256_prefix=sha,
            extracted_chars=len(text),
        )
        return text

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _validate_url_host(self, url: str) -> None:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in {"https", "http"}:
            raise ValidationError(f"URL must be http(s), got scheme: {parsed.scheme!r}")
        host = parsed.netloc.split(":")[0].lower()
        if not any(host == allowed or host.endswith("." + allowed) for allowed in _ALLOWED_HOSTS):
            raise ValidationError(
                f"URL host {host!r} is not a permitted Cloudinary domain. "
                "Upload files via the Cloudinary upload endpoint."
            )

    async def _download(self, url: str) -> tuple[bytes, str]:
        """Fetch the URL and return (bytes, detected_mime)."""
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                # Guard against oversized files before buffering
                content_length = int(response.headers.get("content-length", 0))
                if content_length > _MAX_DOWNLOAD_BYTES:
                    raise ValidationError(
                        f"File too large: {content_length / 1024 / 1024:.1f} MB "
                        f"(max {_MAX_DOWNLOAD_BYTES // 1024 // 1024} MB)."
                    )

                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > _MAX_DOWNLOAD_BYTES:
                        raise ValidationError(
                            f"File exceeded {_MAX_DOWNLOAD_BYTES // 1024 // 1024} MB limit during download."
                        )
                    chunks.append(chunk)

                content = b"".join(chunks)
                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                return content, content_type

    def _validate_mime(self, detected: str, declared: FileType, url: str) -> None:
        allowed = _MIME_ALLOW[declared]
        if detected not in allowed:
            raise ValidationError(
                f"MIME type {detected!r} does not match declared file_type={declared!r}. "
                f"Allowed for {declared!r}: {sorted(allowed)}"
            )
