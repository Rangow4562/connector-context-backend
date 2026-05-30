"""Tests for _build_llm_chain: null-object fallback when no providers resolve."""

from __future__ import annotations

from unittest.mock import MagicMock

from connector_context.adapters.llm.registry import LLMModel, LLMProvider
from connector_context.adapters.llm.unavailable import UnavailableLLM
from connector_context.core.container.factory import _build_llm_chain


def _settings_with_no_keys() -> MagicMock:
    s = MagicMock()
    for attr in (
        "TOGETHER_API_KEY",
        "ANTHROPIC_API_KEY",
        "MISTRAL_API_KEY",
        "GROQ_API_KEY",
        "CEREBRAS_API_KEY",
    ):
        setattr(s, attr, None)
    return s


def _config_with_chain(chain: list[tuple[LLMProvider, LLMModel]]) -> MagicMock:
    config = MagicMock()
    config.LLM_FALLBACK_CHAIN = chain
    return config


def test_returns_unavailable_llm_when_no_keys_configured() -> None:
    settings = _settings_with_no_keys()
    config = _config_with_chain(
        [
            (LLMProvider.TOGETHER, LLMModel.ZAI_GLM_5),
            (LLMProvider.ANTHROPIC, LLMModel.CLAUDE_SONNET_4_6),
        ]
    )
    circuit_breaker = MagicMock()

    llm = _build_llm_chain(settings, config, circuit_breaker)

    assert isinstance(llm, UnavailableLLM)


def test_returns_unavailable_llm_when_chain_is_empty() -> None:
    settings = _settings_with_no_keys()
    config = _config_with_chain([])
    circuit_breaker = MagicMock()

    llm = _build_llm_chain(settings, config, circuit_breaker)

    assert isinstance(llm, UnavailableLLM)
