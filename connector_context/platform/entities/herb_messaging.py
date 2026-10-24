"""HERB Messaging entity schemas."""

from datetime import datetime
from typing import Optional

from connector_context.platform.entities._connector_context_field import ConnectorContextField
from connector_context.platform.entities._base import BaseEntity

__all__ = ["HerbMessageEntity"]


class HerbMessageEntity(BaseEntity):
    """Slack message from the HERB benchmark dataset."""

    message_id: str = ConnectorContextField(
        ...,
        description="HERB message ID (e.g. '20260421-0-921c4')",
        is_entity_id=True,
    )
    text: str = ConnectorContextField(
        ...,
        description="Message text content",
        is_name=True,
        embeddable=True,
    )
    sender_id: str = ConnectorContextField(
        ...,
        description="Sender user ID (e.g. 'eid_9b023657')",
        embeddable=True,
    )
    sender_name: Optional[str] = ConnectorContextField(
        None,
        description="Resolved sender name from employee directory",
        embeddable=True,
    )
    channel_name: str = ConnectorContextField(
        ...,
        description="Slack channel name",
        embeddable=True,
    )
    channel_id: str = ConnectorContextField(
        ...,
        description="Slack channel ID",
    )
    message_time: datetime = ConnectorContextField(
        ...,
        description="Message timestamp",
        is_created_at=True,
    )
    product_name: str = ConnectorContextField(
        ...,
        description="HERB product name this message belongs to",
        embeddable=True,
    )
