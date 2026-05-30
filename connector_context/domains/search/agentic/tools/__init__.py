"""Agentic search tools — definitions, implementations, and dispatcher."""

from connector_context.domains.search.agentic.tools.collect import (
    ADD_TO_RESULTS_TOOL,
    REMOVE_FROM_RESULTS_TOOL,
    AddToResultsTool,
    RemoveFromResultsTool,
)
from connector_context.domains.search.agentic.tools.count import COUNT_TOOL, CountTool
from connector_context.domains.search.agentic.tools.dispatcher import ToolDispatcher
from connector_context.domains.search.agentic.tools.finish import (
    RETURN_RESULTS_TOOL,
    REVIEW_RESULTS_TOOL,
    ReturnResultsTool,
    ReviewResultsTool,
)
from connector_context.domains.search.agentic.tools.navigate import (
    GET_CHILDREN_TOOL,
    GET_PARENT_TOOL,
    GET_SIBLINGS_TOOL,
    GetChildrenTool,
    GetParentTool,
    GetSiblingsTool,
)
from connector_context.domains.search.agentic.tools.read import READ_TOOL, ReadTool
from connector_context.domains.search.agentic.tools.search import SEARCH_TOOL, SearchTool

ALL_TOOL_DEFINITIONS = [
    SEARCH_TOOL,
    READ_TOOL,
    ADD_TO_RESULTS_TOOL,
    REMOVE_FROM_RESULTS_TOOL,
    COUNT_TOOL,
    GET_CHILDREN_TOOL,
    GET_SIBLINGS_TOOL,
    GET_PARENT_TOOL,
    REVIEW_RESULTS_TOOL,
    RETURN_RESULTS_TOOL,
]

__all__ = [
    "ALL_TOOL_DEFINITIONS",
    "ADD_TO_RESULTS_TOOL",
    "REMOVE_FROM_RESULTS_TOOL",
    "COUNT_TOOL",
    "GET_CHILDREN_TOOL",
    "GET_PARENT_TOOL",
    "GET_SIBLINGS_TOOL",
    "READ_TOOL",
    "RETURN_RESULTS_TOOL",
    "REVIEW_RESULTS_TOOL",
    "SEARCH_TOOL",
    "AddToResultsTool",
    "CountTool",
    "GetChildrenTool",
    "GetParentTool",
    "GetSiblingsTool",
    "ReadTool",
    "RemoveFromResultsTool",
    "ReturnResultsTool",
    "ReviewResultsTool",
    "SearchTool",
    "ToolDispatcher",
]
