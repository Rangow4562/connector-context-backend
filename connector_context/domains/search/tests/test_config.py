"""Tests for LLM_FALLBACK_CHAIN env-var parser in search config."""

from __future__ import annotations

import pytest

from connector_context.adapters.llm.registry import LLMModel, LLMProvider
from connector_context.domains.search.config import (
    _DEFAULT_LLM_FALLBACK_CHAIN,
    parse_llm_fallback_chain,
)


def test_none_returns_default_chain() -> None:
    assert parse_llm_fallback_chain(None) == list(_DEFAULT_LLM_FALLBACK_CHAIN)


def test_empty_string_returns_default_chain() -> None:
    assert parse_llm_fallback_chain("") == list(_DEFAULT_LLM_FALLBACK_CHAIN)


def test_whitespace_only_returns_default_chain() -> None:
    assert parse_llm_fallback_chain("   ") == list(_DEFAULT_LLM_FALLBACK_CHAIN)


def test_single_entry_parsed_to_tuple() -> None:
    parsed = parse_llm_fallback_chain("mistral:mistral-large")
    assert parsed == [(LLMProvider.MISTRAL, LLMModel.MISTRAL_LARGE)]


def test_multiple_entries_preserve_order() -> None:
    parsed = parse_llm_fallback_chain(
        "together:zai-glm-5,anthropic:claude-sonnet-4.6,mistral:mistral-large"
    )
    assert parsed == [
        (LLMProvider.TOGETHER, LLMModel.ZAI_GLM_5),
        (LLMProvider.ANTHROPIC, LLMModel.CLAUDE_SONNET_4_6),
        (LLMProvider.MISTRAL, LLMModel.MISTRAL_LARGE),
    ]


def test_whitespace_around_entries_is_ignored() -> None:
    parsed = parse_llm_fallback_chain(" mistral : mistral-large , anthropic : claude-sonnet-4.6 ")
    assert parsed == [
        (LLMProvider.MISTRAL, LLMModel.MISTRAL_LARGE),
        (LLMProvider.ANTHROPIC, LLMModel.CLAUDE_SONNET_4_6),
    ]


def test_unknown_provider_raises_with_accepted_list() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_llm_fallback_chain("bogus:mistral-large")
    message = str(excinfo.value)
    assert "bogus" in message
    assert "mistral" in message
    assert "anthropic" in message


def test_unknown_model_raises_with_accepted_list() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_llm_fallback_chain("mistral:not-a-real-model")
    message = str(excinfo.value)
    assert "not-a-real-model" in message
    assert "mistral-large" in message


def test_missing_colon_raises_helpful_error() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_llm_fallback_chain("mistral-only")
    assert "provider:model" in str(excinfo.value)


def test_trailing_comma_is_tolerated() -> None:
    parsed = parse_llm_fallback_chain("mistral:mistral-large,")
    assert parsed == [(LLMProvider.MISTRAL, LLMModel.MISTRAL_LARGE)]


def test_valid_enums_but_invalid_pair_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_llm_fallback_chain("together:mistral-large")
    message = str(excinfo.value)
    assert "mistral-large" in message
    assert "together" in message
    assert "zai-glm-5" in message
