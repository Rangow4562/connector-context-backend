"""In-memory fake for LLMProtocol."""

from typing import TypeVar

from pydantic import BaseModel

from connector_context.adapters.llm.registry import LLMModelSpec
from connector_context.adapters.llm.tool_response import LLMResponse
from connector_context.core.protocols.llm import LLMProtocol

T = TypeVar("T", bound=BaseModel)


class FakeLLM(LLMProtocol):
    """In-memory fake for LLMProtocol.

    Seed responses before use. Calls are recorded for verification.
    Supports error injection via seed_error() — errors are queued
    alongside normal responses and raised in order.
    """

    def __init__(self, model_spec: LLMModelSpec) -> None:
        self._model_spec = model_spec
        self._structured_output_results: list[BaseModel | Exception] = []
        self._tool_responses: list[LLMResponse | Exception] = []
        self._calls: list[tuple] = []

    def seed_structured_output(self, result: BaseModel) -> None:
        """Seed a result to be returned by next structured_output call."""
        self._structured_output_results.append(result)

    def seed_tool_response(self, response: LLMResponse) -> None:
        """Seed a response to be returned by next chat call."""
        self._tool_responses.append(response)

    def seed_error(self, error: Exception, *, target: str = "chat") -> None:
        """Queue an error to be raised on the next call.

        Args:
            error: The exception to raise.
            target: Which method to target — "chat" or "structured_output".
        """
        if target == "structured_output":
            self._structured_output_results.append(error)
        else:
            self._tool_responses.append(error)

    @property
    def model_spec(self) -> LLMModelSpec:
        """Get the model specification."""
        return self._model_spec

    async def structured_output(
        self,
        prompt: str,
        schema: type[T],
        system_prompt: str,
        thinking: bool = False,
    ) -> T:
        """Return next seeded structured output result, or raise seeded error."""
        self._calls.append(("structured_output", prompt, schema, system_prompt))
        if not self._structured_output_results:
            raise RuntimeError("FakeLLM: no seeded structured_output results")
        result = self._structured_output_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result  # type: ignore[return-value]

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str,
        thinking: bool = False,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Return next seeded tool response, or raise seeded error."""
        self._calls.append(("chat", messages, tools, system_prompt))
        if not self._tool_responses:
            raise RuntimeError("FakeLLM: no seeded tool responses")
        result = self._tool_responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def close(self) -> None:
        """No-op cleanup."""
        self._calls.append(("close",))
