"""In-memory fake for RerankerProtocol."""

from connector_context.adapters.reranker.types import RerankerResult
from connector_context.core.protocols.reranker import RerankerProtocol


class FakeReranker(RerankerProtocol):
    """In-memory fake for RerankerProtocol.

    Returns pre-seeded reranking results. Supports error injection.
    """

    def __init__(self) -> None:
        self._results: list[RerankerResult] = []
        self._calls: list[tuple] = []
        self._error: Exception | None = None

    def seed_results(self, results: list[RerankerResult]) -> None:
        """Seed results to be returned by rerank."""
        self._results = results

    def seed_error(self, error: Exception) -> None:
        """Inject an error to raise on next rerank call (single-shot)."""
        self._error = error

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankerResult]:
        """Return seeded results, or raise seeded error."""
        self._calls.append(("rerank", query, documents, top_n))
        if self._error:
            err = self._error
            self._error = None
            raise err
        if self._results:
            return self._results

        # Default: return identity ordering with linear scores
        limit = top_n if top_n is not None else len(documents)
        return [
            RerankerResult(index=i, relevance_score=1.0 - (i * 0.1))
            for i in range(min(limit, len(documents)))
        ]
