"""Google Gemini LLM implementation.

Uses Google's OpenAI-compatible endpoint so no extra SDK is needed —
the standard `openai` package works with a custom base_url.

Structured output uses json_schema response_format.
Thinking is toggled via reasoning_effort="low" (on) or omitted (off).
"""

import copy
import json
import time
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from connector_context.adapters.llm.base import BaseLLM
from connector_context.adapters.llm.exceptions import LLMTransientError
from connector_context.adapters.llm.registry import LLMModelSpec
from connector_context.adapters.llm.tool_response import LLMResponse, LLMToolCall
from connector_context.core.config import settings

T = TypeVar("T", bound=BaseModel)

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _resolve_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline all $ref/$defs so Gemini's strict schema validator accepts the schema.

    Gemini rejects schemas that contain $defs with $ref pointers. This function
    resolves every "#/$defs/<Name>" reference to its inline definition and then
    removes all $defs keys from the result.
    """
    # Collect definitions from every level of the schema.
    defs: dict[str, Any] = {}

    def _collect_defs(node: Any) -> None:
        if isinstance(node, dict):
            defs.update(node.get("$defs", {}))
            for v in node.values():
                _collect_defs(v)
        elif isinstance(node, list):
            for v in node:
                _collect_defs(v)

    _collect_defs(schema)

    def _inline(node: Any, depth: int = 0) -> Any:
        if depth > 20:
            return node
        if isinstance(node, dict):
            ref = node.get("$ref")
            if ref and isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref[len("#/$defs/"):]
                if name in defs:
                    return _inline(copy.deepcopy(defs[name]), depth + 1)
                return node
            result = {}
            for k, v in node.items():
                if k == "$defs":
                    continue  # strip after resolving
                result[k] = _inline(v, depth + 1)
            return result
        if isinstance(node, list):
            return [_inline(v, depth + 1) for v in node]
        return node

    return _inline(copy.deepcopy(schema))


class GeminiLLM(BaseLLM):
    """Google Gemini LLM provider via OpenAI-compatible endpoint."""

    def __init__(
        self,
        model_spec: LLMModelSpec,
        max_retries: int | None = None,
    ) -> None:
        super().__init__(model_spec, max_retries=max_retries)

        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not configured. Set it in your environment or .env file."
            )

        try:
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=_GEMINI_BASE_URL,
                timeout=self.DEFAULT_TIMEOUT,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Gemini client: {e}") from e

        self._logger.debug(
            f"[GeminiLLM] Initialized with model={model_spec.api_model_name}, "
            f"context_window={model_spec.context_window}, "
            f"max_output_tokens={model_spec.max_output_tokens}"
        )

    def _prepare_schema(self, schema_json: dict[str, Any]) -> dict[str, Any]:
        return self._normalize_strict_schema(schema_json)

    def _prepare_tools(self, tools: list[dict]) -> list[dict]:
        """Resolve $ref/$defs in tool parameter schemas — Gemini rejects inline $defs."""
        result = copy.deepcopy(tools)
        for tool in result:
            params = tool.get("function", {}).get("parameters")
            if isinstance(params, dict):
                tool["function"]["parameters"] = _resolve_refs(params)
        return result

    async def _call_api(
        self,
        prompt: str,
        schema: type[T],
        schema_json: dict[str, Any],
        system_prompt: str,
        thinking: bool = False,
    ) -> T:
        extra: dict[str, Any] = {"reasoning_effort": "low"} if thinking else {}
        api_start = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._model_spec.api_model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__.lower(),
                    "schema": schema_json,
                    "strict": True,
                },
            },
            max_tokens=self._model_spec.max_output_tokens,
            **extra,
        )
        api_time = time.monotonic() - api_start

        content = response.choices[0].message.content
        if not content:
            raise LLMTransientError(
                "Gemini returned empty response content",
                provider=self._name,
            )

        if response.usage:
            self._logger.debug(
                f"[GeminiLLM] API call completed in {api_time:.2f}s, "
                f"tokens: prompt={response.usage.prompt_tokens}, "
                f"completion={response.usage.completion_tokens}"
            )

        return self._parse_json_response(content, schema)

    async def _call_api_chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str,
        thinking: bool = False,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        converted = self._prepare_messages_for_api(messages)
        api_messages = [{"role": "system", "content": system_prompt}, *converted]
        extra: dict[str, Any] = {"reasoning_effort": "low"} if thinking else {}

        api_start = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._model_spec.api_model_name,
            messages=api_messages,
            tools=tools,
            tool_choice="required",
            temperature=0.3,
            max_tokens=max_tokens or self._model_spec.max_output_tokens,
            **extra,
        )
        api_time = time.monotonic() - api_start

        choice = response.choices[0]
        message = choice.message

        text = message.content if message.content else None

        tool_calls: list[LLMToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                arguments = tc.function.arguments
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                tool_calls.append(
                    LLMToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=arguments,
                    )
                )

        prompt_tokens = 0
        completion_tokens = 0
        if response.usage:
            prompt_tokens = response.usage.prompt_tokens or 0
            completion_tokens = response.usage.completion_tokens or 0
            self._logger.debug(
                f"[GeminiLLM] Tool call completed in {api_time:.2f}s, "
                f"tokens: prompt={prompt_tokens}, completion={completion_tokens}"
            )

        return LLMResponse(
            text=text,
            thinking=None,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def close(self) -> None:
        """Close the Gemini/OpenAI async client."""
        if self._client:
            await self._client.close()
            self._logger.debug("[GeminiLLM] Client closed")
