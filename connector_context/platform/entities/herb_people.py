"""HERB People entity schemas."""

from connector_context.platform.entities._connector_context_field import ConnectorContextField
from connector_context.platform.entities._base import BaseEntity

__all__ = ["HerbEmployeeEntity", "HerbCustomerEntity"]


class HerbEmployeeEntity(BaseEntity):
    """Employee record from the HERB benchmark dataset."""

    employee_id: str = ConnectorContextField(
        ...,
        description="Employee ID (e.g. 'eid_9b023657')",
        is_entity_id=True,
    )
    name: str = ConnectorContextField(
        ...,
        description="Employee full name",
        is_name=True,
        embeddable=True,
    )
    role: str = ConnectorContextField(
        ...,
        description="Job role/title",
        embeddable=True,
    )
    location: str = ConnectorContextField(
        ...,
        description="Office location",
        embeddable=True,
    )
    org: str = ConnectorContextField(
        ...,
        description="Organization unit",
        embeddable=True,
    )


class HerbCustomerEntity(BaseEntity):
    """Customer profile from the HERB benchmark dataset."""

    customer_id: str = ConnectorContextField(
        ...,
        description="Customer ID (e.g. 'CUST-0001')",
        is_entity_id=True,
    )
    name: str = ConnectorContextField(
        ...,
        description="Customer full name",
        is_name=True,
        embeddable=True,
    )
    role: str = ConnectorContextField(
        ...,
        description="Customer role/title",
        embeddable=True,
    )
    company: str = ConnectorContextField(
        ...,
        description="Customer company name",
        embeddable=True,
    )
