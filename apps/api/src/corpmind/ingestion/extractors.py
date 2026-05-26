"""File-type extractors — each converts raw bytes (or a URL) into plain text.

Rules:
- extract_pdf / extract_image / extract_video are the ONLY functions here that
  touch file content. They return plain UTF-8 text ≤ MAX_CHARS.
- extract_image calls EuriHTTPProvider directly (vision endpoint); that's the
  only allowed path per euri-gateway.md.
- extract_video is a Phase 2 stub — Whisper is not yet in deps.
"""

from __future__ import annotations

import io
import uuid

import structlog

from corpmind.core.exceptions import ValidationError

log = structlog.get_logger(__name__)

MAX_PDF_PAGES = 50
MAX_CHARS = 15_000


def extract_pdf(content: bytes) -> str:
    """Extract text from PDF bytes via pypdf.

    Raises ValidationError if the PDF is encrypted or contains no extractable text.
    """
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(content))
    except PdfReadError as exc:
        raise ValidationError(f"Cannot read PDF: {exc}") from exc

    if reader.is_encrypted:
        raise ValidationError("Encrypted PDFs are not supported.")

    pages = reader.pages[:MAX_PDF_PAGES]
    parts: list[str] = []
    for page in pages:
        text = page.extract_text() or ""
        parts.append(text.strip())

    combined = "\n\n".join(p for p in parts if p)
    if not combined:
        raise ValidationError("PDF contains no extractable text (scanned image-only PDF?). "
                              "Re-upload as an image to use vision extraction.")
    return combined[:MAX_CHARS]


async def extract_image(image_url: str) -> str:
    """Describe and OCR an image using Euri's vision endpoint (GPT-4o).

    The image must be a publicly-accessible URL (Cloudinary signed URLs qualify).
    """
    from corpmind.ai.providers.euri_http import EuriHTTPProvider

    provider = EuriHTTPProvider()
    try:
        call_id = str(uuid.uuid4())
        text = await provider.vision_describe(
            image_url,
            instruction=(
                "You are an OCR and content extraction assistant. "
                "Extract ALL visible text from this training brochure or poster. "
                "Preserve structure (headings, bullet points, pricing). "
                "Output plain text only — no commentary."
            ),
            call_id=call_id,
        )
        log.info("ingestion.image_extracted", chars=len(text), call_id=call_id)
        return text[:MAX_CHARS]
    finally:
        await provider.aclose()


async def extract_video(video_url: str) -> str:  # noqa: ARG001
    """Phase 2: transcribe video/audio via Whisper.

    Requires faster-whisper in deps and ffmpeg in the worker container.
    Until then, raise so the task retries and the caller surfaces a clear message.
    """
    raise NotImplementedError(
        "Video transcription is Phase 2 — re-upload as a PDF or image poster for now."
    )
