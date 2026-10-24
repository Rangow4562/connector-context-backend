"""LLM response types — re-exported from core/protocols for convenience."""

from connector_context.core.protocols.llm import LLMResponse, LLMToolCall

__all__ = ["LLMToolCall", "LLMResponse"]
