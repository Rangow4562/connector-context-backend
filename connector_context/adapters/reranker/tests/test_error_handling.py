"""Tests for CohereReranker error handling."""

from unittest.mock import AsyncMock, patch

import pytest

from connector_context.adapters.reranker.cohere import CohereReranker, COHERE_MAX_DOCUMENTS
from connector_context.adapters.reranker.exceptions import RerankerError


@pytest.mark.asyncio
async def test_document_limit_exceeded():
    """Passing more than COHERE_MAX_DOCUMENTS raises RerankerError."""
    reranker = CohereReranker(api_key="test-key")
    documents = [f"doc {i}" for i in range(COHERE_MAX_DOCUMENTS + 1)]

    with pytest.raises(RerankerError, match="exceeds the API limit"):
        await reranker.rerank(query="test query", documents=documents)


@pytest.mark.asyncio
async def test_api_failure_wrapped():
    """Cohere SDK exceptions are wrapped in RerankerError with cause."""
    reranker = CohereReranker(api_key="test-key")
    api_error = RuntimeError("connection refused")

    reranker._client.rerank = AsyncMock(side_effect=api_error)

    with pytest.raises(RerankerError, match="Cohere rerank failed") as exc_info:
        await reranker.rerank(query="test query", documents=["doc1", "doc2"])

    assert exc_info.value.cause is api_error
