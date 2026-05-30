"""Tests for UnavailableLLM null-object adapter."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from connector_context.adapters.llm.registry import PROVIDER_API_KEY_SETTINGS
from connector_context.adapters.llm.unavailable import UnavailableLLM
from connector_context.core.exceptions import LLMUnavailableError


class _Dummy(BaseModel):
    key: str


@pytest.mark.asyncio
async def test_structured_output_raises_llm_unavailable_error() -> None:
    llm = UnavailableLLM()
    with pytest.raises(LLMUnavailableError):
        await llm.structured_output(prompt="x", schema=_Dummy, system_prompt="y")


@pytest.mark.asyncio
async def test_chat_raises_llm_unavailable_error() -> None:
    llm = UnavailableLLM()
    with pytest.raises(LLMUnavailableError):
        await llm.chat(messages=[], tools=[], system_prompt="y")


def test_model_spec_raises_llm_unavailable_error() -> None:
    llm = UnavailableLLM()
    with pytest.raises(LLMUnavailableError):
        _ = llm.model_spec


@pytest.mark.asyncio
async def test_close_is_a_safe_noop() -> None:
    llm = UnavailableLLM()
    await llm.close()  # must not raise; returns None by type


def test_error_message_mentions_accepted_api_key_env_vars() -> None:
    llm = UnavailableLLM()
    with pytest.raises(LLMUnavailableError) as excinfo:
        _ = llm.model_spec

    message = str(excinfo.value)
    for env_var in PROVIDER_API_KEY_SETTINGS.values():
        assert env_var in message, f"{env_var} missing from error message"
    assert "LLM_FALLBACK_CHAIN" in message
