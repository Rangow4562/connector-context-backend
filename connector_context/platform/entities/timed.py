"""Timed entity schema for testing purposes.

Provides a minimal entity type for the TimedSource, designed for
precise timing control in sync lifecycle tests.
"""

from datetime import datetime
from typing import Optional

from pydantic import computed_field

from connector_context.platform.entities._connector_context_field import ConnectorContextField
from connector_context.platform.entities._base import BaseEntity


class TimedContainerEntity(BaseEntity):
    """Container entity for organizing timed entities.

    Acts as a parent breadcrumb for all generated timed entities.
    """

    container_id: str = ConnectorContextField(
        ...,
        description="Unique identifier for the timed container",
        is_entity_id=True,
    )
    container_name: str = ConnectorContextField(
        ...,
        description="Name of the timed container",
        is_name=True,
        embeddable=True,
    )
    description: str = ConnectorContextField(
        default="",
        description="Description of the timed container",
        embeddable=True,
    )
    created_at: Optional[datetime] = ConnectorContextField(
        None,
        description="When the container was created",
        is_created_at=True,
    )

    @computed_field(return_type=str)
    def web_url(self) -> str:
        """Placeholder URL for the container."""
        return f"timed://container/{self.container_id}"


class TimedEntity(BaseEntity):
    """Minimal entity for timed source testing.

    Lightweight entity with just enough fields for the sync pipeline
    to process (entity_id, name, content). Designed for high throughput
    with minimal overhead.
    """

    entity_id: str = ConnectorContextField(
        ...,
        description="Unique identifier for the timed entity",
        is_entity_id=True,
    )
    name: str = ConnectorContextField(
        ...,
        description="Name of the timed entity",
        is_name=True,
        embeddable=True,
    )
    content: str = ConnectorContextField(
        ...,
        description="Content text for the entity",
        embeddable=True,
    )
    sequence_number: int = ConnectorContextField(
        default=0,
        description="Sequence number for ordering",
        embeddable=False,
    )
    created_at: Optional[datetime] = ConnectorContextField(
        None,
        description="When the entity was created",
        is_created_at=True,
    )

    @computed_field(return_type=str)
    def web_url(self) -> str:
        """Placeholder URL for the entity."""
        return f"timed://entity/{self.entity_id}"
