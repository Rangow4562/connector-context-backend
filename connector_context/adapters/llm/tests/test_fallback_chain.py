"""Tests for FallbackChainLLM."""

import pytest

from connector_context.adapters.circuit_breaker import InMemoryCircuitBreaker
from connector_context.adapters.llm.exceptions import (
    LLMAllProvidersFailedError,
    LLMProviderExhaustedError,
)
from connector_context.adapters.llm.fakes.llm import FakeLLM
from connector_context.adapters.llm.fallback import FallbackChainLLM
from connector_context.adapters.llm.registry import LLMModelSpec, ThinkingConfig
from connector_context.adapters.llm.tool_response import LLMResponse
from connector_context.adapters.tokenizer.registry import TokenizerEncoding, TokenizerType


def _make_spec(name: str = "test") -> LLMModelSpec:
    return LLMModelSpec(
        api_model_name=name,
        context_window=8192,
        max_output_tokens=2048,
        required_tokenizer_type=TokenizerType.TIKTOKEN,
        required_tokenizer_encoding=TokenizerEncoding.O200K_HARMONY,
        thinking_config=ThinkingConfig(param_name="_noop", param_value=True),
    )


def _make_response(text: str = "ok") -> LLMResponse:
    return LLMResponse(text=text, thinking=None, tool_calls=[])


@pytest.mark.asyncio
async def test_primary_succeeds_no_fallback():
    """Primary provider returns a response; secondary is never called."""
    primary = FakeLLM(_make_spec("primary"))
    secondary = FakeLLM(_make_spec("secondary"))
    cb = InMemoryCircuitBreaker(cooldown_seconds=60)

    chain = FallbackChainLLM([primary, secondary], cb)

    expected = _make_response("from primary")
    primary.seed_tool_response(expected)

    result = await chain.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system_prompt="sys",
    )

    assert result is expected
    # Secondary should have no calls recorded
    assert len(secondary._calls) == 0


@pytest.mark.asyncio
async def test_primary_fails_secondary_succeeds():
    """Primary raises LLMProviderExhaustedError; secondary provides the response."""
    primary = FakeLLM(_make_spec("primary"))
    secondary = FakeLLM(_make_spec("secondary"))
    cb = InMemoryCircuitBreaker(cooldown_seconds=60)

    chain = FallbackChainLLM([primary, secondary], cb)

    primary.seed_error(
        LLMProviderExhaustedError("exhausted", provider="primary"),
        target="chat",
    )
    expected = _make_response("from secondary")
    secondary.seed_tool_response(expected)

    result = await chain.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system_prompt="sys",
    )

    assert result is expected


@pytest.mark.asyncio
async def test_all_fail_raises_all_providers_failed():
    """Both providers fail — LLMAllProvidersFailedError is raised."""
    primary = FakeLLM(_make_spec("primary"))
    secondary = FakeLLM(_make_spec("secondary"))
    cb = InMemoryCircuitBreaker(cooldown_seconds=60)

    chain = FallbackChainLLM([primary, secondary], cb)

    primary.seed_error(
        LLMProviderExhaustedError("exhausted", provider="primary"),
        target="chat",
    )
    secondary.seed_error(
        LLMProviderExhaustedError("exhausted", provider="secondary"),
        target="chat",
    )

    with pytest.raises(LLMAllProvidersFailedError) as exc_info:
        await chain.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            system_prompt="sys",
        )

    assert len(exc_info.value.provider_errors) == 2


@pytest.mark.asyncio
async def test_circuit_breaker_skips_tripped_provider():
    """A tripped provider is skipped; the secondary is called first."""
    primary = FakeLLM(_make_spec("primary"))
    secondary = FakeLLM(_make_spec("secondary"))
    cb = InMemoryCircuitBreaker(cooldown_seconds=300)

    # Trip primary's circuit breaker before building the chain
    await cb.record_failure("primary")

    chain = FallbackChainLLM([primary, secondary], cb)

    expected = _make_response("from secondary")
    secondary.seed_tool_response(expected)

    result = await chain.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system_prompt="sys",
    )

    assert result is expected
    # Primary should have no calls — it was skipped
    assert len(primary._calls) == 0
