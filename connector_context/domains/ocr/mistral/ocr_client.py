"""Mistral direct OCR API client.

Encapsulates interactions with Mistral's OCR API using direct (synchronous)
calls instead of the batch API. Each document is processed immediately,
returning results without polling.

All network calls go through :meth:`_api_call` which applies rate-limiting
(via :class:`MistralRateLimiter`) and exponential-backoff retries (via tenacity).
"""

from __future__ import annotations

import asyncio
import base64
import os
from typing import Any, Callable, Optional

import aiofiles
import httpx
from httpx import HTTPStatusError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from connector_context.core.config import settings
from connector_context.core.logging import logger
from connector_context.domains.ocr.mistral.models import (
    FileChunk,
    OcrResult,
)
from connector_context.domains.sync_pipeline.exceptions import SyncFailureError
from connector_context.platform.rate_limiters import MistralRateLimiter

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

MAX_RETRIES = 5
RETRY_MIN_WAIT = 2  # seconds (lower than batch since direct calls are faster)
RETRY_MAX_WAIT = 30  # seconds
RETRY_MULTIPLIER = 2

# Concurrent OCR calls cap (can be higher than batch uploads since OCR is the bottleneck)
DEFAULT_OCR_CONCURRENCY = 10

# Azure Mistral endpoint page limit per request
AZURE_MAX_PAGES = 30


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors worth retrying (5xx, timeouts, rate limits).

    4xx client errors (401 Unauthorized, 403 Forbidden, 404, etc.) are
    permanent and will never succeed on retry — fail fast instead.
    """
    if isinstance(exc, HTTPStatusError):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return True


class MistralOcrClient:
    """Async client for Mistral's direct OCR API."""

    def __init__(self, concurrency: int = DEFAULT_OCR_CONCURRENCY) -> None:
        """Initialize the OCR client.

        Args:
            concurrency: Maximum number of concurrent OCR requests.
        """
        self._client: Any = None
        self._initialized = False
        self._rate_limiter = MistralRateLimiter()
        self._concurrency = concurrency

    # ------------------------------------------------------------------
    # Lazy client initialisation
    # ------------------------------------------------------------------

    def ensure_initialized(self) -> None:
        """Create the Mistral SDK client if not done yet.

        Raises:
            SyncFailureError: If the API key is missing or the SDK is not installed.
        """
        if self._initialized:
            return

        if not getattr(settings, "MISTRAL_API_KEY", None):
            raise SyncFailureError("MISTRAL_API_KEY required for document conversion")

        try:
            from mistralai import Mistral

            self._client = Mistral(
                api_key=settings.MISTRAL_API_KEY,
                timeout_ms=120_000,  # 2 minutes per OCR call
            )
            self._initialized = True
            logger.debug("Mistral OCR client initialized")
        except ImportError:
            raise SyncFailureError("mistralai package required but not installed")

    # ------------------------------------------------------------------
    # Rate-limited + retried API call wrapper
    # ------------------------------------------------------------------

    async def _api_call(self, coro_fn: Callable[[], Any], operation_name: str = "ocr") -> Any:
        """Execute an async SDK call with rate-limiting and retry.

        Args:
            coro_fn: A zero-argument callable that returns a fresh coroutine
                     on each invocation. This ensures retries create a new
                     coroutine instead of re-awaiting a consumed one.
            operation_name: Label used in log messages.
        """

        @retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(MAX_RETRIES),
            wait=wait_exponential(
                multiplier=RETRY_MULTIPLIER, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT
            ),
            reraise=True,
        )
        async def _inner() -> Any:
            await self._rate_limiter.acquire()
            return await coro_fn()

        try:
            return await _inner()
        except Exception as exc:
            logger.warning(f"[MISTRAL_OCR] {operation_name} failed after retries: {exc}")
            raise

    # ------------------------------------------------------------------
    # Single file OCR
    # ------------------------------------------------------------------

    async def ocr_chunk(self, chunk: FileChunk) -> OcrResult:
        """Perform OCR on a single file chunk.

        Args:
            chunk: The chunk to process.

        Returns:
            An :class:`OcrResult` with the markdown content.

        Raises:
            Exception: If OCR fails after retries (propagates the underlying error).
        """
        file_name = os.path.basename(chunk.chunk_path)

        try:
            async with aiofiles.open(chunk.chunk_path, "rb") as fh:
                content = await fh.read()

            azure_endpoint = getattr(settings, "MISTRAL_ENDPOINT", None)
            if azure_endpoint:
                markdown = await self._ocr_azure(content, file_name, azure_endpoint)
            else:
                markdown = await self._ocr_sdk(content, file_name)

            logger.debug(f"OCR completed for {file_name}")
            return OcrResult(chunk=chunk, markdown=markdown)

        except Exception as exc:
            logger.error(f"OCR failed for {file_name}: {exc}")
            raise

    async def _ocr_azure(self, content: bytes, file_name: str, endpoint: str) -> Optional[str]:
        """OCR via Azure-hosted Mistral endpoint (direct base64 POST, no file upload).

        PDFs exceeding AZURE_MAX_PAGES are split into page-range chunks automatically.
        """
        api_key = getattr(settings, "MISTRAL_API_KEY", None)
        if not api_key:
            raise SyncFailureError("MISTRAL_API_KEY required for Azure Mistral OCR")

        ext = os.path.splitext(file_name)[1].lower()

        # Split large PDFs into 30-page chunks before sending
        if ext == ".pdf":
            page_chunks = await self._split_pdf_pages(content, AZURE_MAX_PAGES)
            if len(page_chunks) > 1:
                logger.debug(
                    f"Azure OCR: splitting {file_name} into {len(page_chunks)} "
                    f"chunks of ≤{AZURE_MAX_PAGES} pages"
                )
                parts: list[str] = []
                for i, chunk_bytes in enumerate(page_chunks):
                    chunk_name = f"{file_name}[pages-chunk-{i + 1}]"
                    result = await self._ocr_azure_request(
                        chunk_bytes, chunk_name, endpoint, api_key, "application/pdf"
                    )
                    if result:
                        parts.append(result)
                return "\n\n---\n\n".join(parts) if parts else None

        mime = "application/pdf" if ext == ".pdf" else "image/png"
        return await self._ocr_azure_request(content, file_name, endpoint, api_key, mime)

    async def _ocr_azure_request(
        self,
        content: bytes,
        file_name: str,
        endpoint: str,
        api_key: str,
        mime: str,
    ) -> Optional[str]:
        """Send a single base64-encoded document to the Azure OCR endpoint."""
        model = getattr(settings, "MISTRAL_OCR_MODEL", "mistral-document-ai-2512")
        b64 = base64.b64encode(content).decode()
        payload = {
            "model": model,
            "document": {
                "type": "document_url",
                "document_url": f"data:{mime};base64,{b64}",
            },
        }

        @retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(MAX_RETRIES),
            wait=wait_exponential(
                multiplier=RETRY_MULTIPLIER, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT
            ),
            reraise=True,
        )
        async def _retried() -> Any:
            await self._rate_limiter.acquire()
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    endpoint,
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                return resp.json()

        data = await _retried()
        return self._extract_markdown_from_dict(data, file_name)

    @staticmethod
    async def _split_pdf_pages(content: bytes, max_pages: int) -> list[bytes]:
        """Split PDF bytes into chunks of at most *max_pages* pages each."""
        import io
        import tempfile

        try:
            import PyPDF2
        except ImportError:
            logger.warning("PyPDF2 not installed — sending PDF as-is (may exceed Azure page limit)")
            return [content]

        def _split() -> list[bytes]:
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            total = len(reader.pages)
            if total <= max_pages:
                return [content]

            chunks: list[bytes] = []
            for start in range(0, total, max_pages):
                end = min(start + max_pages, total)
                writer = PyPDF2.PdfWriter()
                for i in range(start, end):
                    writer.add_page(reader.pages[i])
                buf = io.BytesIO()
                writer.write(buf)
                chunks.append(buf.getvalue())
            return chunks

        return await asyncio.to_thread(_split)

    async def _ocr_sdk(self, content: bytes, file_name: str) -> Optional[str]:
        """OCR via standard Mistral SDK (upload → OCR → delete)."""
        self.ensure_initialized()

        model = getattr(settings, "MISTRAL_OCR_MODEL", "mistral-ocr-latest")

        file_resp = await self._api_call(
            lambda: self._client.files.upload_async(
                file={"file_name": file_name, "content": content},
                purpose="ocr",
            ),
            operation_name=f"upload_{file_name}",
        )

        from mistralai.models import FileChunk as MistralFileChunk

        ocr_resp = await self._api_call(
            lambda: self._client.ocr.process_async(
                model=model,
                document=MistralFileChunk(file_id=file_resp.id),
            ),
            operation_name=f"ocr_{file_name}",
        )

        markdown = self._extract_markdown(ocr_resp, file_name)
        await self._delete_file(file_resp.id)
        return markdown

    # ------------------------------------------------------------------
    # Batch OCR with bounded concurrency
    # ------------------------------------------------------------------

    async def ocr_chunks(self, chunks: list[FileChunk]) -> list[OcrResult]:
        """Process multiple chunks with bounded concurrency.

        Args:
            chunks: List of chunks to OCR.

        Returns:
            List of :class:`OcrResult` objects (in same order as input).
        """
        if not chunks:
            return []

        semaphore = asyncio.Semaphore(self._concurrency)
        results: list[OcrResult | Exception] = [None] * len(chunks)  # type: ignore[assignment]

        async def _process_one(idx: int, chunk: FileChunk) -> None:
            async with semaphore:
                try:
                    results[idx] = await self.ocr_chunk(chunk)
                except Exception as exc:
                    results[idx] = exc

        await asyncio.gather(
            *[_process_one(i, c) for i, c in enumerate(chunks)],
        )

        # Separate successes from failures — failed chunks get OcrResult with error
        final_results: list[OcrResult] = []
        failed_count = 0

        for i, r in enumerate(results):
            file_name = os.path.basename(chunks[i].chunk_path)
            if isinstance(r, Exception):
                logger.error(f"OCR failed for {file_name}: {r}")
                final_results.append(OcrResult(chunk=chunks[i], markdown=None, error=str(r)))
                failed_count += 1
            elif r is None:
                logger.error(f"OCR failed for {file_name}: task did not complete")
                final_results.append(
                    OcrResult(chunk=chunks[i], markdown=None, error="task did not complete")
                )
                failed_count += 1
            else:
                final_results.append(r)

        if failed_count:
            logger.warning(
                f"OCR batch: {failed_count}/{len(chunks)} chunks failed "
                f"(continuing with {len(chunks) - failed_count} successful)"
            )

        logger.debug(
            f"OCR batch complete: {len(final_results) - failed_count}/{len(chunks)} succeeded"
        )
        return final_results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_markdown_from_dict(data: dict, file_name: str) -> Optional[str]:
        """Extract markdown from Azure OCR JSON response dict."""
        pages = data.get("pages") or []
        if not pages:
            logger.warning(f"No pages in Azure OCR response for {file_name}")
            return None
        parts = [p.get("markdown", "") or "" for p in pages if p.get("markdown")]
        if not parts:
            logger.warning(f"Azure OCR returned empty markdown for {file_name}")
            return ""
        return "\n\n".join(parts)

    @staticmethod
    def _extract_markdown(ocr_resp: Any, file_name: str) -> Optional[str]:
        """Extract markdown text from OCR response."""
        pages = getattr(ocr_resp, "pages", None) or []

        if not pages:
            logger.warning(f"No pages in OCR response for {file_name}")
            return None

        markdown_parts = []
        for page in pages:
            md = getattr(page, "markdown", "") or ""
            if md:
                markdown_parts.append(md)

        if not markdown_parts:
            logger.warning(f"OCR returned empty markdown for {file_name}")
            return ""

        return "\n\n".join(markdown_parts)

    async def _delete_file(self, file_id: str) -> None:
        """Best-effort deletion of uploaded file from Mistral."""
        try:
            await self._api_call(
                lambda: self._client.files.delete_async(file_id=file_id),
                operation_name=f"delete_{file_id[:8]}",
            )
        except Exception:
            pass  # Best effort
