"""Tool call dispatcher — routes LLM tool calls to handlers with error handling.

All tool errors are caught and converted to ToolError subclasses.
The agent loop catches ToolError and returns the message to the LLM,
allowing it to self-correct.
"""

from __future__ import annotations

from typing import Any, Protocol, Union

from pydantic import ValidationError

from connector_context.core.protocols.llm import LLMToolCall
from connector_context.domains.embedders.exceptions import EmbedderError
from connector_context.domains.search.adapters.vector_db.exceptions import VectorDBError
from connector_context.domains.search.agentic.exceptions import (
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
)
from connector_context.domains.search.agentic.state import AgentState
from connector_context.domains.search.agentic.tools.types import (
    CollectToolResult,
    CountToolResult,
    FinishToolResult,
    NavigateToolResult,
    ReadToolResult,
    ReviewToolResult,
    SearchToolResult,
)
from connector_context.domains.search.exceptions import SearchError

ToolResult = Union[
    SearchToolResult,
    ReadToolResult,
    CollectToolResult,
    CountToolResult,
    NavigateToolResult,
    ReviewToolResult,
    FinishToolResult,
]


class Tool(Protocol):
    """Protocol for a tool that can be dispatched."""

    async def execute(
        self,
        arguments: dict[str, Any],
        state: AgentState,
        tool_call_id: str = "",
    ) -> ToolResult:
        """Execute the tool with given arguments and state."""
        ...


class ToolDispatcher:
    """Routes tool calls to the appropriate handler with error handling.

    All exceptions are caught and converted:
    - ToolError subclasses pass through (already typed)
    - Pydantic ValidationError → ToolValidationError
    - Any other exception → ToolExecutionError
    """

    def __init__(self, tools: dict[str, Tool]) -> None:
        """Initialize with a mapping of tool_name -> tool instance."""
        self._tools = tools

    @property
    def tool_names(self) -> list[str]:
        """Available tool names."""
        return sorted(self._tools.keys())

    async def dispatch(
        self,
        tc: LLMToolCall,
        state: AgentState,
    ) -> ToolResult:
        """Dispatch a tool call to the appropriate handler.

        Correctable errors (bad arguments, not-found) are caught and converted
        to ToolError subclasses — the agent loop feeds these back to the LLM
        so it can self-correct.

        Infrastructure errors (vector DB down, embedder timeout, federated
        source failure) propagate uncaught — the LLM can't fix these, so they
        should crash the agent loop and surface to the user.

        Raises:
            ToolNotFoundError: Tool name not registered (correctable).
            ToolValidationError: LLM arguments fail validation (correctable).
            ToolExecutionError: Tool logic failed (correctable).
            SearchError: Infrastructure failure (NOT correctable — propagates).
        """
        tool = self._tools.get(tc.name)
        if not tool:
            raise ToolNotFoundError(
                f"Unknown tool '{tc.name}'. Available tools: {', '.join(self.tool_names)}"
            )
        try:
            return await tool.execute(tc.arguments, state, tool_call_id=tc.id)
        except (ToolError, SearchError, EmbedderError, VectorDBError):
            # ToolError subclasses and infrastructure errors propagate directly.
            # Infrastructure errors (SearchError, EmbedderError, VectorDBError)
            # reach the agent loop → SearchFailedEvent. The LLM can't fix these.
            raise
        except ValidationError as e:
            raise ToolValidationError(f"Invalid arguments for '{tc.name}': {e}") from e
        except Exception as e:
            raise ToolExecutionError(f"Tool '{tc.name}' failed: {e}") from e
