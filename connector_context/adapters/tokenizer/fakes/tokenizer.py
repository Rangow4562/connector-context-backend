"""In-memory fake for TokenizerProtocol."""

from connector_context.adapters.tokenizer.registry import TokenizerModelSpec


class FakeTokenizer:
    """In-memory fake for TokenizerProtocol.

    Returns a configurable tokens-per-character ratio (default: 1 token per 4 chars).
    Supports error injection.
    """

    def __init__(
        self,
        model_spec: TokenizerModelSpec | None = None,
        chars_per_token: int = 4,
    ) -> None:
        self._model_spec = model_spec or TokenizerModelSpec(encoding_name="fake")
        self._chars_per_token = chars_per_token
        self._calls: list[tuple] = []
        self._error: Exception | None = None

    @property
    def model_spec(self) -> TokenizerModelSpec:
        """Get the model specification."""
        return self._model_spec

    def seed_error(self, error: Exception) -> None:
        """Inject an error to raise on next count_tokens call (single-shot)."""
        self._error = error

    def count_tokens(self, text: str) -> int:
        """Count tokens using approximate chars-per-token ratio, or raise seeded error."""
        self._calls.append(("count_tokens", text))
        if self._error:
            err = self._error
            self._error = None
            raise err
        if not text:
            return 0
        return max(1, len(text) // self._chars_per_token)
