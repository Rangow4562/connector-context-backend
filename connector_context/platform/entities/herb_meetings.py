"""HERB Meetings entity schemas."""

from datetime import datetime
from typing import Optional

from connector_context.platform.entities._connector_context_field import ConnectorContextField
from connector_context.platform.entities._base import BaseEntity

__all__ = ["HerbMeetingTranscriptEntity", "HerbMeetingChatEntity"]


class HerbMeetingTranscriptEntity(BaseEntity):
    """Meeting transcript from the HERB benchmark dataset."""

    meeting_id: str = ConnectorContextField(
        ...,
        description="HERB meeting transcript ID",
        is_entity_id=True,
    )
    title: str = ConnectorContextField(
        ...,
        description="Meeting title (product + date)",
        is_name=True,
        embeddable=True,
    )
    transcript: str = ConnectorContextField(
        ...,
        description="Full meeting transcript with attendee names and dialogue",
        embeddable=True,
    )
    document_type: str = ConnectorContextField(
        ...,
        description="Document type classification",
        embeddable=True,
    )
    participant_ids: str = ConnectorContextField(
        ...,
        description="Comma-separated participant employee IDs",
        embeddable=True,
    )
    participant_names: Optional[str] = ConnectorContextField(
        None,
        description="Resolved participant names from employee directory",
        embeddable=True,
    )
    meeting_date: Optional[datetime] = ConnectorContextField(
        None,
        description="Meeting date",
        is_created_at=True,
    )
    product_name: str = ConnectorContextField(
        ...,
        description="HERB product name this meeting belongs to",
        embeddable=True,
    )


class HerbMeetingChatEntity(BaseEntity):
    """Meeting chat log from the HERB benchmark dataset."""

    chat_id: str = ConnectorContextField(
        ...,
        description="HERB meeting chat ID",
        is_entity_id=True,
    )
    text: str = ConnectorContextField(
        ...,
        description="Chat text content",
        is_name=True,
        embeddable=True,
    )
    product_name: str = ConnectorContextField(
        ...,
        description="HERB product name this chat belongs to",
        embeddable=True,
    )
