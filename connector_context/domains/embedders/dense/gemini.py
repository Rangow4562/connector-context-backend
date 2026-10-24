"""Google Gemini dense embedder satisfying DenseEmbedderProtocol.

Uses Google's OpenAI-compatible embeddings endpoint — no extra SDK needed.
"""

import asyncio

from openai import AsyncOpenAI

from connector_context.domains.embedders.exceptions import (
    EmbedderAuthError,
    EmbedderConnectionError,
    EmbedderDimensionError,
    EmbedderInputError,
    EmbedderProviderError,
    EmbedderRateLimitError,
    EmbedderResponseError,
    EmbedderTimeoutError,
)
from connector_context.domains.embedders.protocols import DenseEmbedderProtocol
from connector_context.domains.embedders.types import DenseEmbedding

_PROVIDER = "gemini"
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_MAX_TEXTS_PER_BATCH = 100
_MAX_CONCURRENT_REQUESTS = 5
_CLIENT_TIMEOUT = 120.0


class GeminiDenseEmbedder(DenseEmbedderProtocol):
    """Google Gemini dense embedder via OpenAI-compatible endpoint."""

    def __init__(self, *, api_key: str, model: str, dimensions: int) -> None:
        self._model = model
        self._dimensions = dimensions
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=_GEMINI_BASE_URL,
            timeout=_CLIENT_TIMEOUT,
        )
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> DenseEmbedding:
        results = await self.embed_many([text])
        return results[0]

    async def embed_many(self, texts: list[str]) -> list[DenseEmbedding]:
        if not texts:
            return []

        self._validate_inputs(texts)

        batches = [
            texts[i : i + _MAX_TEXTS_PER_BATCH]
            for i in range(0, len(texts), _MAX_TEXTS_PER_BATCH)
        ]
        nested = await asyncio.gather(*[self._embed_batch(b) for b in batches])
        return [emb for batch_result in nested for emb in batch_result]

    async def close(self) -> None:
        await self._client.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_inputs(texts: list[str]) -> None:
        for i, text in enumerate(texts):
            if not text or not text.strip():
                raise EmbedderInputError(f"Text at index {i} is empty or blank")

    async def _embed_batch(self, batch: list[str]) -> list[DenseEmbedding]:
        async with self._semaphore:
            return await self._call_api(batch)

    async def _call_api(self, batch: list[str]) -> list[DenseEmbedding]:
        import openai

        try:
            response = await self._client.embeddings.create(
                input=batch,
                model=self._model,
                encoding_format="float",
            )
        except openai.AuthenticationError as e:
            raise EmbedderAuthError(
                f"Gemini embedding authentication failed: {e}", provider=_PROVIDER
            ) from e
        except openai.RateLimitError as e:
            retry_after: float | None = None
            if hasattr(e, "response") and e.response is not None:
                try:
                    retry_after = float(e.response.headers.get("retry-after", ""))
                except (ValueError, TypeError):
                    pass
            raise EmbedderRateLimitError(
                f"Gemini embedding rate limit exceeded: {e}",
                provider=_PROVIDER,
                retry_after=retry_after,
            ) from e
        except openai.APITimeoutError as e:
            raise EmbedderTimeoutError(
                f"Gemini embedding request timed out: {e}", provider=_PROVIDER
            ) from e
        except openai.APIConnectionError as e:
            raise EmbedderConnectionError(
                f"Gemini embedding connection failed: {e}", provider=_PROVIDER
            ) from e
        except openai.APIStatusError as e:
            raise EmbedderProviderError(
                f"Gemini embedding API error (status {e.status_code}): {e}",
                provider=_PROVIDER,
                retryable=e.status_code >= 500,
            ) from e

        embeddings = response.data
        if len(embeddings) != len(batch):
            raise EmbedderResponseError(
                f"Expected {len(batch)} embeddings, got {len(embeddings)}"
            )

        results: list[DenseEmbedding] = []
        for emb in embeddings:
            if len(emb.embedding) != self._dimensions:
                raise EmbedderDimensionError(
                    expected=self._dimensions,
                    actual=len(emb.embedding),
                )
            results.append(DenseEmbedding(vector=emb.embedding))

        return results
