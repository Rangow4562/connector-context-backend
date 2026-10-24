"""Tests for CerebrasLLM — mock the SDK client, not the network."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from connector_context.adapters.llm.cerebras import CerebrasLLM
from connector_context.adapters.llm.exceptions import LLMProviderExhaustedError, LLMTransientError
from connector_context.adapters.llm.registry import LLMModelSpec, ThinkingConfig
from connector_context.adapters.tokenizer.registry import TokenizerEncoding, TokenizerType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(
    param_name: str = "reasoning_effort",
    param_value: str | bool = "high",
) -> LLMModelSpec:
    return LLMModelSpec(
        api_model_name="test-model",
        context_window=8192,
        max_output_tokens=2048,
        required_tokenizer_type=TokenizerType.TIKTOKEN,
        required_tokenizer_encoding=TokenizerEncoding.O200K_HARMONY,
        thinking_config=ThinkingConfig(param_name=param_name, param_value=param_value),
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
    """Build a mock mimicking the Cerebras SDK ChatCompletion response."""
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
def cerebras_llm():
    """Instantiate CerebrasLLM with a patched settings object (GPT-OSS config)."""
    with patch("connector_context.adapters.llm.cerebras.settings") as mock_settings:
        mock_settings.CEREBRAS_API_KEY = "test-key"
        llm = CerebrasLLM(model_spec=_make_spec(), max_retries=0)
        yield llm


@pytest.fixture
def cerebras_llm_glm():
    """Instantiate CerebrasLLM with GLM thinking config (disable_reasoning)."""
    with patch("connector_context.adapters.llm.cerebras.settings") as mock_settings:
        mock_settings.CEREBRAS_API_KEY = "test-key"
        llm = CerebrasLLM(
            model_spec=_make_spec(param_name="disable_reasoning", param_value=False),
            max_retries=0,
        )
        yield llm


# ═══════════════════════════════════════════════════════════════════════════
# structured_output tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_structured_output_returns_parsed(cerebras_llm: CerebrasLLM) -> None:
    """_call_api parses JSON content into the Pydantic model."""
    cerebras_llm._client.chat.completions.create = AsyncMock(
        return_value=_mock_response(content='{"key": "hello"}')
    )

    result = await cerebras_llm.structured_output(
        prompt="test prompt",
        schema=_DummyOutput,
        system_prompt="sys",
    )

    assert isinstance(result, _DummyOutput)
    assert result.key == "hello"


@pytest.mark.asyncio
async def test_empty_response_raises_transient(cerebras_llm: CerebrasLLM) -> None:
    """Empty content from the API raises LLMTransientError."""
    cerebras_llm._client.chat.completions.create = AsyncMock(
        return_value=_mock_response(content=None)
    )

    with pytest.raises(LLMProviderExhaustedError, match="empty response"):
        await cerebras_llm.structured_output(
            prompt="test prompt",
            schema=_DummyOutput,
            system_prompt="sys",
        )


# ═══════════════════════════════════════════════════════════════════════════
# chat tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_chat_returns_tool_calls(cerebras_llm: CerebrasLLM) -> None:
    """chat() extracts tool_calls from the response."""
    mock_tc = MagicMock()
    mock_tc.id = "tc-1"
    mock_tc.function.name = "search"
    mock_tc.function.arguments = '{"query": "hello"}'

    cerebras_llm._client.chat.completions.create = AsyncMock(
        return_value=_mock_response(content="text", tool_calls=[mock_tc])
    )

    result = await cerebras_llm.chat(
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


@pytest.mark.asyncio
async def test_chat_gptoss_reasoning_effort(cerebras_llm: CerebrasLLM) -> None:
    """GPT-OSS: thinking=True passes reasoning_effort='high'."""
    mock_create = AsyncMock(
        return_value=_mock_response(content=None, tool_calls=None)
    )
    cerebras_llm._client.chat.completions.create = mock_create

    await cerebras_llm.chat(
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
async def test_chat_glm_disable_reasoning(cerebras_llm_glm: CerebrasLLM) -> None:
    """GLM: thinking=True passes disable_reasoning=False."""
    mock_create = AsyncMock(
        return_value=_mock_response(content=None, tool_calls=None)
    )
    cerebras_llm_glm._client.chat.completions.create = mock_create

    await cerebras_llm_glm.chat(
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
    assert call_kwargs["disable_reasoning"] is False


@pytest.mark.asyncio
async def test_prepare_messages_gptoss(cerebras_llm: CerebrasLLM) -> None:
    """GPT-OSS: thinking is prepended raw (no <think> tags)."""
    messages = [
        {
            "role": "assistant",
            "content": "answer",
            "_thinking": "my reasoning",
        }
    ]
    result = cerebras_llm._prepare_messages_for_api(messages)

    assert result[0]["content"] == "my reasoning\nanswer"
    assert "_thinking" not in result[0]


@pytest.mark.asyncio
async def test_prepare_messages_glm(cerebras_llm_glm: CerebrasLLM) -> None:
    """GLM: thinking is wrapped in <think> tags."""
    messages = [
        {
            "role": "assistant",
            "content": "answer",
            "_thinking": "my reasoning",
        }
    ]
    result = cerebras_llm_glm._prepare_messages_for_api(messages)

    assert result[0]["content"] == "<think>my reasoning</think>\nanswer"
