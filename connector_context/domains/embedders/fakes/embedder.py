"""Fake embedder implementations for testing."""

from connector_context.domains.embedders.types import DenseEmbedding, SparseEmbedding


class FakeDenseEmbedder:
    """Test implementation of DenseEmbedderProtocol.

    Returns zero-vectors of a fixed dimension. Supports error injection.

    Usage:
        fake = FakeDenseEmbedder(dimensions=3072)
        result = await fake.embed("hello")
        assert len(result.vector) == 3072
    """

    def __init__(self, dimensions: int = 3072) -> None:
        """Initialize with a fixed dimension size."""
        self._dimensions = dimensions
        self._error: Exception | None = None

    @property
    def model_name(self) -> str:
        """The model identifier."""
        return "fake-dense"

    @property
    def dimensions(self) -> int:
        """The output vector dimensionality."""
        return self._dimensions

    def seed_error(self, error: Exception) -> None:
        """Inject an error to raise on next embed/embed_many call (single-shot)."""
        self._error = error

    def _check_error(self) -> None:
        if self._error:
            err = self._error
            self._error = None
            raise err

    async def embed(self, text: str) -> DenseEmbedding:
        """Return a zero-vector of the configured dimensions."""
        self._check_error()
        return DenseEmbedding(vector=[0.0] * self._dimensions)

    async def embed_many(self, texts: list[str]) -> list[DenseEmbedding]:
        """Return zero-vectors for each text."""
        self._check_error()
        return [DenseEmbedding(vector=[0.0] * self._dimensions) for _ in texts]

    async def close(self) -> None:
        """No-op."""


class FakeSparseEmbedder:
    """Test implementation of SparseEmbedderProtocol.

    Returns empty sparse vectors. Supports error injection.

    Usage:
        fake = FakeSparseEmbedder()
        result = await fake.embed("hello")
        assert result.indices == []
    """

    def __init__(self) -> None:
        self._error: Exception | None = None

    @property
    def model_name(self) -> str:
        """The model identifier."""
        return "fake-sparse"

    def seed_error(self, error: Exception) -> None:
        """Inject an error to raise on next embed/embed_many call (single-shot)."""
        self._error = error

    def _check_error(self) -> None:
        if self._error:
            err = self._error
            self._error = None
            raise err

    async def embed(self, text: str) -> SparseEmbedding:
        """Return an empty sparse embedding."""
        self._check_error()
        return SparseEmbedding(indices=[], values=[])

    async def embed_many(self, texts: list[str]) -> list[SparseEmbedding]:
        """Return empty sparse embeddings for each text."""
        self._check_error()
        return [SparseEmbedding(indices=[], values=[]) for _ in texts]

    async def close(self) -> None:
        """No-op."""
