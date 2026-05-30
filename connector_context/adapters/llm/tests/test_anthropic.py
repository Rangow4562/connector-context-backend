"""Tests for AnthropicLLM — mock the SDK client, not the network."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from connector_context.adapters.llm.anthropic import AnthropicLLM
from connector_context.adapters.llm.exceptions import LLMProviderExhaustedError, LLMTransientError
from connector_context.adapters.llm.registry import LLMModelSpec, ThinkingConfig
from connector_context.adapters.tokenizer.registry import TokenizerEncoding, TokenizerType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(effort: str | None = "high") -> LLMModelSpec:
    return LLMModelSpec(
        api_model_name="test-model",
        context_window=8192,
        max_output_tokens=2048,
        required_tokenizer_type=TokenizerType.TIKTOKEN,
        required_tokenizer_encoding=TokenizerEncoding.O200K_HARMONY,
        thinking_config=ThinkingConfig(
            param_name="adaptive_thinking",
            param_value=True,
            effort=effort,
        ),
    )


class _DummyOutput(BaseModel):
    key: str


def _make_block(block_type: str, **kwargs) -> MagicMock:
    """Create a mock Anthropic content block."""
    block = MagicMock()
    block.type = block_type
    for k, v in kwargs.items():
        setattr(block, k, v)
    return block


def _mock_response(
    content_blocks: list[MagicMock],
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_creation: int = 0,
    cache_read: int = 0,
) -> MagicMock:
    """Build a mock that mimics the Anthropic Messages response."""
    mock_resp = MagicMock()
    mock_resp.content = content_blocks
    mock_resp.usage = MagicMock(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
    )
    return mock_resp


@pytest.fixture
def anthropic_llm():
    """Instantiate AnthropicLLM with a patched settings object."""
    with patch("connector_context.adapters.llm.anthropic.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        llm = AnthropicLLM(model_spec=_make_spec(), max_retries=0)
        yield llm


# ═══════════════════════════════════════════════════════════════════════════
# structured_output tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_structured_output_returns_parsed(anthropic_llm: AnthropicLLM) -> None:
    """tool_use content block with valid input is parsed into the Pydantic model."""
    tool_block = _make_block(
        "tool_use",
        name="generate__dummyoutput",
        input={"key": "value"},
        id="tc-1",
    )
    anthropic_llm._client.messages.create = AsyncMock(
        return_value=_mock_response([tool_block])
    )

    result = await anthropic_llm.structured_output(
        prompt="test prompt",
        schema=_DummyOutput,
        system_prompt="sys",
    )

    assert isinstance(result, _DummyOutput)
    assert result.key == "value"


@pytest.mark.asyncio
async def test_structured_output_no_tool_block_raises(anthropic_llm: AnthropicLLM) -> None:
    """If no tool_use block is returned, raises LLMTransientError."""
    text_block = _make_block("text", text="hello")
    anthropic_llm._client.messages.create = AsyncMock(
        return_value=_mock_response([text_block])
    )

    with pytest.raises(LLMProviderExhaustedError, match="did not return a tool_use"):
        await anthropic_llm.structured_output(
            prompt="test prompt",
            schema=_DummyOutput,
            system_prompt="sys",
        )


# ═══════════════════════════════════════════════════════════════════════════
# chat tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_chat_returns_tool_calls(anthropic_llm: AnthropicLLM) -> None:
    """chat() extracts tool_use blocks into LLMResponse.tool_calls."""
    tool_block = _make_block(
        "tool_use",
        name="search",
        input={"query": "hello"},
        id="tc-1",
    )
    anthropic_llm._client.messages.create = AsyncMock(
        return_value=_mock_response([tool_block])
    )

    result = await anthropic_llm.chat(
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
    assert result.completion_tokens == 50


@pytest.mark.asyncio
async def test_chat_thinking_disabled(anthropic_llm: AnthropicLLM) -> None:
    """When thinking=False, kwargs include thinking: {type: disabled}."""
    mock_create = AsyncMock(
        return_value=_mock_response([_make_block("text", text="hi")])
    )
    anthropic_llm._client.messages.create = mock_create

    await anthropic_llm.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system_prompt="sys",
        thinking=False,
    )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["thinking"] == {"type": "disabled"}
    assert "output_config" not in call_kwargs


@pytest.mark.asyncio
async def test_chat_thinking_enabled(anthropic_llm: AnthropicLLM) -> None:
    """When thinking=True, kwargs include thinking: {type: adaptive} and effort."""
    mock_create = AsyncMock(
        return_value=_mock_response([_make_block("text", text="hi")])
    )
    anthropic_llm._client.messages.create = mock_create

    await anthropic_llm.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system_prompt="sys",
        thinking=True,
    )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["thinking"] == {"type": "adaptive"}
    assert call_kwargs["output_config"] == {"effort": "high"}


@pytest.mark.asyncio
async def test_chat_with_thinking_blocks(anthropic_llm: AnthropicLLM) -> None:
    """chat() populates LLMResponse.thinking from thinking content blocks."""
    thinking_block = _make_block("thinking", thinking="Let me reason about this...")
    tool_block = _make_block(
        "tool_use",
        name="search",
        input={"query": "test"},
        id="tc-1",
    )
    anthropic_llm._client.messages.create = AsyncMock(
        return_value=_mock_response([thinking_block, tool_block])
    )

    result = await anthropic_llm.chat(
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
        thinking=True,
    )

    assert result.thinking == "Let me reason about this..."
    assert len(result.tool_calls) == 1


@pytest.mark.asyncio
async def test_chat_cache_tokens(anthropic_llm: AnthropicLLM) -> None:
    """chat() reports cache_creation and cache_read tokens from usage."""
    anthropic_llm._client.messages.create = AsyncMock(
        return_value=_mock_response(
            [_make_block("text", text="ok")],
            cache_creation=500,
            cache_read=1200,
        )
    )

    result = await anthropic_llm.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system_prompt="sys",
    )

    assert result.cache_creation_input_tokens == 500
    assert result.cache_read_input_tokens == 1200


@pytest.mark.asyncio
async def test_convert_tool_defs(anthropic_llm: AnthropicLLM) -> None:
    """_convert_tool_defs transforms OpenAI-format tools to Anthropic format."""
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "my_tool",
                "description": "Does stuff",
                "parameters": {
                    "type": "object",
                    "title": "MyTool",
                    "properties": {"x": {"type": "string", "title": "X"}},
                },
            },
        }
    ]

    result = anthropic_llm._convert_tool_defs(openai_tools)

    assert len(result) == 1
    assert result[0]["name"] == "my_tool"
    assert result[0]["description"] == "Does stuff"
    # title should be stripped by _clean_schema_basic
    assert "title" not in result[0]["input_schema"]
    assert "title" not in result[0]["input_schema"]["properties"]["x"]


# ---------------------------------------------------------------------------
# _parse_response_blocks
# ---------------------------------------------------------------------------


def _block(**kwargs):
    """Create a mock content block with explicit attributes (not MagicMock auto-attrs)."""
    b = MagicMock()
    for k, v in kwargs.items():
        # Use property to avoid MagicMock wrapping string values
        type(b).__dict__  # force init
        object.__setattr__(b, k, v)
    return b


def test_parse_response_blocks_text_and_tool_use():
    """Mixed response with text + tool_use blocks parsed correctly."""
    from connector_context.adapters.llm.anthropic import _parse_response_blocks

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I'll search for that."

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tc-1"
    tool_block.name = "search"
    tool_block.input = {"query": "test"}

    thinking_parts, text_parts, tool_calls, sig = _parse_response_blocks(
        [text_block, tool_block]
    )

    assert thinking_parts == []
    assert text_parts == ["I'll search for that."]
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "search"
    assert tool_calls[0].arguments == {"query": "test"}
    assert sig is None


def test_parse_response_blocks_thinking_and_tool_use():
    """Response with thinking + tool_use blocks (no text)."""
    from connector_context.adapters.llm.anthropic import _parse_response_blocks

    think_block = MagicMock(spec=["type", "thinking"])
    think_block.type = "thinking"
    think_block.thinking = "Let me reason about this..."

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tc-1"
    tool_block.name = "read"
    tool_block.input = {"entity_ids": ["e1"]}

    thinking_parts, text_parts, tool_calls, sig = _parse_response_blocks(
        [think_block, tool_block]
    )

    assert thinking_parts == ["Let me reason about this..."]
    assert text_parts == []
    assert len(tool_calls) == 1
    assert sig is None


def test_parse_response_blocks_string_tool_input():
    """tool_use block with string input (needs JSON parsing)."""
    from connector_context.adapters.llm.anthropic import _parse_response_blocks

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tc-1"
    tool_block.name = "count"
    tool_block.input = '{"filter_groups": []}'

    _, _, tool_calls, _ = _parse_response_blocks([tool_block])

    assert tool_calls[0].arguments == {"filter_groups": []}


def test_parse_response_blocks_extracts_signature():
    """Signature is extracted from thinking blocks when present."""
    from connector_context.adapters.llm.anthropic import _parse_response_blocks

    think_block = MagicMock()
    think_block.type = "thinking"
    think_block.thinking = "Let me think..."
    think_block.signature = "sig_abc123"

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tc-1"
    tool_block.name = "search"
    tool_block.input = {"query": "test"}

    thinking_parts, _, _, sig = _parse_response_blocks([think_block, tool_block])

    assert thinking_parts == ["Let me think..."]
    assert sig == "sig_abc123"


# ---------------------------------------------------------------------------
# _build_assistant_blocks — thinking signature handling
# ---------------------------------------------------------------------------


def test_build_assistant_blocks_with_signature():
    """Thinking block is included when signature is present."""
    from connector_context.adapters.llm.anthropic import _build_assistant_blocks

    msg = {
        "role": "assistant",
        "content": "text",
        "_thinking": "I should search...",
        "_thinking_signature": "sig_abc123",
        "tool_calls": [],
    }

    blocks = _build_assistant_blocks(msg)

    thinking_blocks = [b for b in blocks if b["type"] == "thinking"]
    assert len(thinking_blocks) == 1
    assert thinking_blocks[0]["thinking"] == "I should search..."
    assert thinking_blocks[0]["signature"] == "sig_abc123"


def test_build_assistant_blocks_without_signature_skips_thinking():
    """Thinking block is skipped when signature is missing (cross-provider fallback)."""
    from connector_context.adapters.llm.anthropic import _build_assistant_blocks

    msg: dict[str, Any] = {
        "role": "assistant",
        "content": "text",
        "_thinking": "Together AI reasoning text...",
        "_thinking_signature": None,
        "tool_calls": [],
    }

    blocks = _build_assistant_blocks(msg)

    thinking_blocks = [b for b in blocks if b["type"] == "thinking"]
    assert len(thinking_blocks) == 0
    # Text content should still be present
    text_blocks = [b for b in blocks if b["type"] == "text"]
    assert len(text_blocks) == 1


def test_build_assistant_blocks_no_thinking_at_all():
    """No thinking block when _thinking is None."""
    from connector_context.adapters.llm.anthropic import _build_assistant_blocks

    msg: dict[str, Any] = {
        "role": "assistant",
        "content": "just text",
        "_thinking": None,
        "_thinking_signature": None,
        "tool_calls": [],
    }

    blocks = _build_assistant_blocks(msg)

    thinking_blocks = [b for b in blocks if b["type"] == "thinking"]
    assert len(thinking_blocks) == 0


def test_cross_provider_fallback_conversation():
    """Full conversation from Together (no sig) converts cleanly for Anthropic."""
    from connector_context.adapters.llm.anthropic import _convert_messages_to_anthropic

    messages = [
        {"role": "user", "content": "find tasks"},
        {
            "role": "assistant",
            "content": None,
            "_thinking": "Together reasoning: I should search for tasks...",
            "_thinking_signature": None,
            "tool_calls": [
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "search", "arguments": '{"query": "tasks"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tc-1", "content": "Found 4 results"},
    ]

    result = _convert_messages_to_anthropic(messages)

    # Assistant message should have tool_use but NO thinking block
    assistant_msg = result[1]
    assert assistant_msg["role"] == "assistant"
    thinking_blocks = [b for b in assistant_msg["content"] if b.get("type") == "thinking"]
    assert len(thinking_blocks) == 0
    tool_blocks = [b for b in assistant_msg["content"] if b.get("type") == "tool_use"]
    assert len(tool_blocks) == 1


def test_anthropic_conversation_preserves_thinking():
    """Conversation from Anthropic (with sig) preserves thinking blocks."""
    from connector_context.adapters.llm.anthropic import _convert_messages_to_anthropic

    messages = [
        {"role": "user", "content": "find tasks"},
        {
            "role": "assistant",
            "content": None,
            "_thinking": "Let me search for tasks...",
            "_thinking_signature": "sig_from_claude_abc123",
            "tool_calls": [
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "search", "arguments": '{"query": "tasks"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tc-1", "content": "Found 4 results"},
    ]

    result = _convert_messages_to_anthropic(messages)

    assistant_msg = result[1]
    thinking_blocks = [b for b in assistant_msg["content"] if b.get("type") == "thinking"]
    assert len(thinking_blocks) == 1
    assert thinking_blocks[0]["signature"] == "sig_from_claude_abc123"


# ---------------------------------------------------------------------------
# _convert_messages_to_anthropic
# ---------------------------------------------------------------------------


def test_convert_messages_merges_consecutive_user():
    """Consecutive user messages are merged (Anthropic requirement)."""
    from connector_context.adapters.llm.anthropic import _convert_messages_to_anthropic

    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "user", "content": "Can you search?"},
    ]

    result = _convert_messages_to_anthropic(messages)

    assert len(result) == 1
    assert result[0]["role"] == "user"
