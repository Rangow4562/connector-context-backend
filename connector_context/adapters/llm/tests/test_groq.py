"""Tests for GroqLLM — mock the SDK client, not the network."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from connector_context.adapters.llm.exceptions import LLMProviderExhaustedError, LLMTransientError
from connector_context.adapters.llm.groq import GroqLLM
from connector_context.adapters.llm.registry import LLMModelSpec, ThinkingConfig
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
        thinking_config=ThinkingConfig(
            param_name="reasoning_effort",
            param_value="high",
        ),
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
    """Build a mock mimicking the Groq SDK ChatCompletion response."""
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
def groq_llm():
    """Instantiate GroqLLM with a patched settings object."""
    with patch("connector_context.adapters.llm.groq.settings") as mock_settings:
        mock_settings.GROQ_API_KEY = "test-key"
        llm = GroqLLM(model_spec=_make_spec(), max_retries=0)
        yield llm


# ═══════════════════════════════════════════════════════════════════════════
# structured_output tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_structured_output_returns_parsed(groq_llm: GroqLLM) -> None:
    """_call_api parses JSON content into the Pydantic model."""
    groq_llm._client.chat.completions.create = AsyncMock(
        return_value=_mock_response(content='{"key": "hello"}')
    )

    result = await groq_llm.structured_output(
        prompt="test prompt",
        schema=_DummyOutput,
        system_prompt="sys",
    )

    assert isinstance(result, _DummyOutput)
    assert result.key == "hello"


@pytest.mark.asyncio
async def test_empty_response_raises_transient(groq_llm: GroqLLM) -> None:
    """Empty content from the API raises LLMTransientError."""
    groq_llm._client.chat.completions.create = AsyncMock(
        return_value=_mock_response(content=None)
    )

    with pytest.raises(LLMProviderExhaustedError, match="empty response"):
        await groq_llm.structured_output(
            prompt="test prompt",
            schema=_DummyOutput,
            system_prompt="sys",
        )


# ═══════════════════════════════════════════════════════════════════════════
# chat tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_chat_returns_tool_calls(groq_llm: GroqLLM) -> None:
    """chat() extracts tool_calls from the response."""
    mock_tc = MagicMock()
    mock_tc.id = "tc-1"
    mock_tc.function.name = "search"
    mock_tc.function.arguments = '{"query": "hello"}'

    groq_llm._client.chat.completions.create = AsyncMock(
        return_value=_mock_response(content="text", tool_calls=[mock_tc])
    )

    result = await groq_llm.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        system_prompt="sys",
    )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "search"
    assert result.tool_calls[0].arguments == {"query": "hello"}
    assert result.prompt_tokens == 100


@pytest.mark.asyncio
async def test_chat_reasoning_effort_high(groq_llm: GroqLLM) -> None:
    """chat(thinking=True) passes reasoning_effort='high'."""
    mock_create = AsyncMock(
        return_value=_mock_response(content=None, tool_calls=None)
    )
    groq_llm._client.chat.completions.create = mock_create

    await groq_llm.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "noop",
                    "description": "",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        system_prompt="sys",
        thinking=True,
    )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_chat_reasoning_effort_low(groq_llm: GroqLLM) -> None:
    """chat(thinking=False) passes reasoning_effort='low'."""
    mock_create = AsyncMock(
        return_value=_mock_response(content=None, tool_calls=None)
    )
    groq_llm._client.chat.completions.create = mock_create

    await groq_llm.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "noop",
                    "description": "",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        system_prompt="sys",
        thinking=False,
    )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["reasoning_effort"] == "low"
