"""LLM adapters."""

from connector_context.adapters.llm.anthropic import AnthropicLLM
from connector_context.adapters.llm.base import BaseLLM
from connector_context.adapters.llm.cerebras import CerebrasLLM
from connector_context.adapters.llm.gemini import GeminiLLM
from connector_context.adapters.llm.exceptions import (
    LLMAllProvidersFailedError,
    LLMError,
    LLMFatalError,
    LLMProviderExhaustedError,
    LLMTransientError,
)
from connector_context.adapters.llm.fallback import FallbackChainLLM
from connector_context.adapters.llm.groq import GroqLLM
from connector_context.adapters.llm.mistral import MistralLLM
from connector_context.adapters.llm.override import create_llm_from_override
from connector_context.adapters.llm.registry import (
    MODEL_REGISTRY,
    PROVIDER_API_KEY_SETTINGS,
    LLMModel,
    LLMModelSpec,
    LLMProvider,
    ThinkingConfig,
    get_available_models,
    get_model_spec,
)
from connector_context.adapters.llm.together import TogetherLLM
from connector_context.adapters.llm.tool_response import LLMResponse, LLMToolCall
from connector_context.core.protocols.llm import LLMProtocol

__all__ = [
    # Protocol
    "LLMProtocol",
    # Base + providers
    "BaseLLM",
    "AnthropicLLM",
    "CerebrasLLM",
    "GeminiLLM",
    "GroqLLM",
    "MistralLLM",
    "TogetherLLM",
    "FallbackChainLLM",
    # Exceptions
    "LLMError",
    "LLMTransientError",
    "LLMFatalError",
    "LLMProviderExhaustedError",
    "LLMAllProvidersFailedError",
    # Enums
    "LLMProvider",
    "LLMModel",
    # Types
    "LLMModelSpec",
    "ThinkingConfig",
    "LLMToolCall",
    "LLMResponse",
    # Registry
    "MODEL_REGISTRY",
    "PROVIDER_API_KEY_SETTINGS",
    "get_model_spec",
    "get_available_models",
    # Override
    "create_llm_from_override",
]
