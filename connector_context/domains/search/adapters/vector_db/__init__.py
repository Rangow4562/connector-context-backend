"""Vector DB adapters for the search module."""

from connector_context.domains.search.adapters.vector_db.exceptions import (
    FilterTranslationError,
    VectorDBError,
)
from connector_context.domains.search.adapters.vector_db.filter_translator import FilterTranslator
from connector_context.domains.search.adapters.vector_db.protocol import VectorDBProtocol
from connector_context.domains.search.adapters.vector_db.vespa_client import VespaVectorDB

__all__ = [
    "VectorDBProtocol",
    "VespaVectorDB",
    "FilterTranslator",
    "VectorDBError",
    "FilterTranslationError",
]
