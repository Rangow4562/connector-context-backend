"""Tests for TogetherLLM — mock the SDK client, not the network."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from connector_context.adapters.llm.exceptions import LLMProviderExhaustedError, LLMTransientError
from connector_context.adapters.llm.registry import LLMModelSpec, ThinkingConfig
from connector_context.adapters.llm.together import TogetherLLM
from connector_context.adapters.tokenizer.registry import TokenizerEncoding, TokenizerType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec() -> LLMModelSpec:
    return LLMModelSpec(
        api_model_name="test-model",
        context_window=8192,
        max_output_tokens=2048,
        required_tokenizer_type=TokenizerType.TIKTOKEN,
        required_tokenizer_encoding=TokenizerEncoding.O200K_HARMONY,
        thinking_config=ThinkingConfig(param_name="_noop", param_value=True),
    )


class _DummyOutput(BaseModel):
    key: str


def _mock_response(
    content: str | None = '{"key": "value"}',
    tool_calls: list | None = None,
    reasoning: str | None = None,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    total_tokens: int = 150,
) -> MagicMock:
    """Build a mock that mimics the Together SDK ChatCompletion response."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_choice.message.tool_calls = tool_calls
    mock_choice.message.reasoning = reasoning

    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = MagicMock(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    return mock_resp


@pytest.fixture
def together_llm():
    """Instantiate TogetherLLM with a patched settings object."""
    with patch("connector_context.adapters.llm.together.settings") as mock_settings:
        mock_settings.TOGETHER_API_KEY = "test-key"
        llm = TogetherLLM(model_spec=_make_spec(), max_retries=0)
        yield llm


# ═══════════════════════════════════════════════════════════════════════════
# structured_output tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_structured_output_returns_parsed(together_llm: TogetherLLM) -> None:
    """_call_api parses JSON content into the Pydantic model."""
    together_llm._client.chat.completions.create = AsyncMock(
        return_value=_mock_response(content='{"key": "hello"}')
    )

    result = await together_llm.structured_output(
        prompt="test prompt",
        schema=_DummyOutput,
        system_prompt="sys",
    )

    assert isinstance(result, _DummyOutput)
    assert result.key == "hello"


@pytest.mark.asyncio
async def test_empty_response_raises_transient(together_llm: TogetherLLM) -> None:
    """Empty content from the API raises LLMTransientError."""
    together_llm._client.chat.completions.create = AsyncMock(
        return_value=_mock_response(content=None)
    )

    with pytest.raises(LLMProviderExhaustedError, match="empty response"):
        await together_llm.structured_output(
            prompt="test prompt",
            schema=_DummyOutput,
            system_prompt="sys",
        )


# ═══════════════════════════════════════════════════════════════════════════
# chat tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_chat_returns_llm_response(together_llm: TogetherLLM) -> None:
    """chat() returns LLMResponse with tool_calls parsed correctly."""
    mock_tc = MagicMock()
    mock_tc.id = "tc-1"
    mock_tc.function.name = "search"
    mock_tc.function.arguments = '{"query": "hello"}'

    together_llm._client.chat.completions.create = AsyncMock(
        return_value=_mock_response(content="some text", tool_calls=[mock_tc])
    )

    result = await together_llm.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system_prompt="sys",
    )

    assert result.text == "some text"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "search"
    assert result.tool_calls[0].arguments == {"query": "hello"}
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 50


@pytest.mark.asyncio
async def test_chat_with_thinking(together_llm: TogetherLLM) -> None:
    """chat() populates thinking from the message.reasoning field."""
    together_llm._client.chat.completions.create = AsyncMock(
        return_value=_mock_response(
            content="answer",
            reasoning="I thought about this...",
            tool_calls=None,
        )
    )

    result = await together_llm.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system_prompt="sys",
        thinking=True,
    )

    assert result.thinking == "I thought about this..."
    assert result.text == "answer"


@pytest.mark.asyncio
async def test_chat_no_tool_calls_returns_empty_list(together_llm: TogetherLLM) -> None:
    """chat() returns an empty tool_calls list when the model produces none."""
    together_llm._client.chat.completions.create = AsyncMock(
        return_value=_mock_response(content="just text", tool_calls=None)
    )

    result = await together_llm.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system_prompt="sys",
    )

    assert result.tool_calls == []
    assert result.text == "just text"


@pytest.mark.asyncio
async def test_chat_thinking_kwargs(together_llm: TogetherLLM) -> None:
    """chat() passes reasoning={enabled: True} when thinking=True."""
    mock_create = AsyncMock(
        return_value=_mock_response(content=None, tool_calls=None)
    )
    together_llm._client.chat.completions.create = mock_create

    await together_llm.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system_prompt="sys",
        thinking=True,
    )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["reasoning"] == {"enabled": True}
    assert call_kwargs["temperature"] == 1.0  # thinking mode uses temp=1.0
    assert call_kwargs["chat_template_kwargs"] == {"clear_thinking": False}
