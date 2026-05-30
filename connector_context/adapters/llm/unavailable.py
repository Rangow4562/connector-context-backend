"""Null-object LLM provider for deployments without any configured API key.

Wired into the container when LLM_FALLBACK_CHAIN has no entries whose API key is
set. Instant search — which does not use an LLM — keeps working. Classic and
agentic search services are unchanged (they still expect a non-null LLMProtocol);
the failure surfaces on first use as LLMUnavailableError, which the FastAPI
exception handler maps to HTTP 503.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from connector_context.adapters.llm.registry import PROVIDER_API_KEY_SETTINGS, LLMModelSpec
from connector_context.adapters.llm.tool_response import LLMResponse
from connector_context.core.exceptions import LLMUnavailableError

T = TypeVar("T", bound=BaseModel)

_DETAILED_MESSAGE = (
    "No LLM provider configured. Set one of: "
    f"{', '.join(PROVIDER_API_KEY_SETTINGS.values())} — "
    "or customize the chain via LLM_FALLBACK_CHAIN "
    "(format: 'provider:model,provider:model')."
)


class UnavailableLLM:
    """LLMProtocol implementation that raises on every call.

    The protocol is structural (``typing.Protocol``), so no inheritance is
    required. Every method and the ``model_spec`` property raise
    ``LLMUnavailableError`` with an actionable message.
    """

    @property
    def model_spec(self) -> LLMModelSpec:
        """Raise because no provider is configured."""
        raise LLMUnavailableError(_DETAILED_MESSAGE)

    async def structured_output(
        self,
        prompt: str,
        schema: type[T],
        system_prompt: str,
        thinking: bool = False,
    ) -> T:
        """Raise because no provider is configured."""
        raise LLMUnavailableError(_DETAILED_MESSAGE)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str,
        thinking: bool = False,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Raise because no provider is configured."""
        raise LLMUnavailableError(_DETAILED_MESSAGE)

    async def close(self) -> None:
        """No-op: the null-object holds no resources."""
        return None
