"""HERB Resources entity schemas."""

from connector_context.platform.entities._connector_context_field import ConnectorContextField
from connector_context.platform.entities._base import BaseEntity

__all__ = ["HerbResourceEntity"]


class HerbResourceEntity(BaseEntity):
    """Shared URL/bookmark from the HERB benchmark dataset."""

    resource_id: str = ConnectorContextField(
        ...,
        description="HERB resource ID",
        is_entity_id=True,
    )
    description: str = ConnectorContextField(
        ...,
        description="URL description",
        is_name=True,
        embeddable=True,
    )
    link: str = ConnectorContextField(
        ...,
        description="URL (ground truth for URL-type questions)",
        embeddable=True,
    )
    product_name: str = ConnectorContextField(
        ...,
        description="HERB product name this resource belongs to",
        embeddable=True,
    )
