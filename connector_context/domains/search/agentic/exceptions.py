"""Exceptions for the agentic search tools.

Tool errors are caught by the dispatcher and returned to the LLM
as tool result messages, allowing it to self-correct.
Adapter-level retries (e.g., Vespa timeouts, LLM rate limits)
are handled by the adapters themselves.
"""

from connector_context.domains.search.exceptions import SearchError


class ToolError(SearchError):
    """Base tool error — message is returned to the LLM as tool result."""


class ToolValidationError(ToolError):
    """LLM provided invalid arguments (bad JSON, wrong types, missing fields)."""


class ToolTransientError(ToolError):
    """Tool failed due to a transient infrastructure error (vector DB, embedding).

    Tells the LLM "try again" rather than "try differently".
    """


class ToolExecutionError(ToolError):
    """Tool execution failed after adapter-level retries."""


class ToolNotFoundError(ToolError):
    """LLM called a tool that doesn't exist."""


class ContextBudgetExhaustedError(SearchError):
    """Context window too full for useful work, even after compression."""


class ContextBudgetCriticalError(SearchError):
    """Context exceeds hard limit — safety check failed."""
