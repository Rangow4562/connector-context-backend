"""HERB Documents entity schemas."""

from datetime import datetime
from typing import Optional

from connector_context.platform.entities._connector_context_field import ConnectorContextField
from connector_context.platform.entities._base import BaseEntity

__all__ = ["HerbDocumentEntity"]


class HerbDocumentEntity(BaseEntity):
    """Document (PRD, vision doc, system design, etc.) from the HERB benchmark dataset."""

    doc_id: str = ConnectorContextField(
        ...,
        description="HERB document ID (e.g. 'backaix_market_research_report')",
        is_entity_id=True,
    )
    title: str = ConnectorContextField(
        ...,
        description="Document title derived from ID",
        is_name=True,
        embeddable=True,
    )
    content: str = ConnectorContextField(
        ...,
        description="Full document content",
        embeddable=True,
    )
    doc_type: str = ConnectorContextField(
        ...,
        description="Document type (e.g. 'Market Research Report')",
        embeddable=True,
    )
    author_id: str = ConnectorContextField(
        ...,
        description="Author employee ID",
        embeddable=True,
    )
    author_name: Optional[str] = ConnectorContextField(
        None,
        description="Resolved author name from employee directory",
        embeddable=True,
    )
    feedback: Optional[str] = ConnectorContextField(
        None,
        description="Document feedback (present on ~200 of 400 docs)",
        embeddable=True,
    )
    document_link: Optional[str] = ConnectorContextField(
        None,
        description="Document URL (synthetic)",
    )
    doc_created_at: Optional[datetime] = ConnectorContextField(
        None,
        description="Document creation date",
        is_created_at=True,
    )
    product_name: str = ConnectorContextField(
        ...,
        description="HERB product name this document belongs to",
        embeddable=True,
    )
