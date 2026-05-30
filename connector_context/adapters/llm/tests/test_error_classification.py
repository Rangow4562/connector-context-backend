"""Tests for BaseLLM error classification and retry logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from connector_context.adapters.llm.base import BaseLLM
from connector_context.adapters.llm.exceptions import (
    LLMFatalError,
    LLMProviderExhaustedError,
    LLMTransientError,
)
from connector_context.adapters.llm.registry import LLMModelSpec, ThinkingConfig
from connector_context.adapters.tokenizer.registry import TokenizerEncoding, TokenizerType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_SPEC = LLMModelSpec(
    api_model_name="test-model",
    context_window=8192,
    max_output_tokens=2048,
    required_tokenizer_type=TokenizerType.TIKTOKEN,
    required_tokenizer_encoding=TokenizerEncoding.O200K_HARMONY,
    thinking_config=ThinkingConfig(param_name="_noop", param_value=True),
)


class _StatusCodeError(Exception):
    """Exception that carries an HTTP status_code, mimicking SDK exceptions."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class _ControllableLLM(BaseLLM):
    """Minimal BaseLLM subclass whose API calls are driven by a result list.

    Pop results from a list on each call; if the item is an exception, raise it,
    otherwise return it.
    """

    def __init__(
        self,
        results: list | None = None,
        max_retries: int = 3,
    ) -> None:
        super().__init__(model_spec=_TEST_SPEC, max_retries=max_retries)
        self._results: list = list(results or [])
        self.call_count = 0

    async def _call_api(self, *args, **kwargs):  # noqa: ANN002,ANN003
        self.call_count += 1
        item = self._results.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def _call_api_chat(self, *args, **kwargs):  # noqa: ANN002,ANN003
        return await self._call_api(*args, **kwargs)

    async def close(self) -> None:
        pass


def _make_llm(max_retries: int = 3) -> _ControllableLLM:
    return _ControllableLLM(max_retries=max_retries)


# ═══════════════════════════════════════════════════════════════════════════
# _classify_error tests
# ═══════════════════════════════════════════════════════════════════════════


class TestClassifyError:
    """Direct tests for BaseLLM._classify_error."""

    def test_classify_status_400_is_fatal(self) -> None:
        llm = _make_llm()
        err = _StatusCodeError("bad request", status_code=400)
        result = llm._classify_error(err, "test")
        assert isinstance(result, LLMFatalError)

    def test_classify_status_401_is_fatal(self) -> None:
        llm = _make_llm()
        err = _StatusCodeError("unauthorized", status_code=401)
        result = llm._classify_error(err, "test")
        assert isinstance(result, LLMFatalError)

    def test_classify_status_429_is_transient(self) -> None:
        llm = _make_llm()
        err = _StatusCodeError("rate limited", status_code=429)
        result = llm._classify_error(err, "test")
        assert isinstance(result, LLMTransientError)

    def test_classify_status_500_is_transient(self) -> None:
        llm = _make_llm()
        err = _StatusCodeError("internal server error", status_code=500)
        result = llm._classify_error(err, "test")
        assert isinstance(result, LLMTransientError)

    def test_classify_authentication_string_is_fatal(self) -> None:
        llm = _make_llm()
        err = Exception("authentication failed")
        result = llm._classify_error(err, "test")
        assert isinstance(result, LLMFatalError)

    def test_classify_timeout_string_is_transient(self) -> None:
        llm = _make_llm()
        err = Exception("connection timeout")
        result = llm._classify_error(err, "test")
        assert isinstance(result, LLMTransientError)

    def test_classify_unknown_defaults_to_transient(self) -> None:
        llm = _make_llm()
        err = Exception("something weird")
        result = llm._classify_error(err, "test")
        assert isinstance(result, LLMTransientError)


# ═══════════════════════════════════════════════════════════════════════════
# _with_retry tests
# ═══════════════════════════════════════════════════════════════════════════


class _RetryResult:
    """Lightweight stand-in for an LLMResponse with a retries attribute."""

    def __init__(self) -> None:
        self.retries = 0


class TestWithRetry:
    """Tests for BaseLLM._with_retry retry loop."""

    @pytest.mark.asyncio
    async def test_retry_transient_succeeds_on_second_attempt(self) -> None:
        """First call raises a transient error, second succeeds.

        The retry loop should set retries=1 on the returned result.
        """
        success = _RetryResult()
        call_count = 0

        async def fn() -> _RetryResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMTransientError("temporary", provider="test")
            return success

        llm = _make_llm(max_retries=3)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await llm._with_retry("test", fn)

        assert result is success
        assert result.retries == 1
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_fatal_not_retried(self) -> None:
        """A fatal error on the first call is raised immediately.

        The function must only be called once.
        """
        call_count = 0

        async def fn() -> None:
            nonlocal call_count
            call_count += 1
            raise LLMFatalError("permanent", provider="test")

        llm = _make_llm(max_retries=3)
        with pytest.raises(LLMFatalError):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await llm._with_retry("test", fn)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_exhaustion_raises_provider_exhausted(self) -> None:
        """When all attempts produce transient errors, LLMProviderExhaustedError is raised.

        With max_retries=3, the function should be called 4 times (initial + 3 retries).
        """
        call_count = 0

        async def fn() -> None:
            nonlocal call_count
            call_count += 1
            raise LLMTransientError("still failing", provider="test")

        llm = _make_llm(max_retries=3)
        with pytest.raises(LLMProviderExhaustedError):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await llm._with_retry("test", fn)

        assert call_count == 4  # initial + 3 retries
