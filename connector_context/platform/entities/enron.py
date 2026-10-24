"""Enron Email entity schema for evaluation.

Extends BaseEntity (not EmailEntity/FileEntity) — the email body is stored
directly as an embeddable field, not saved as a file. This follows the HERB
benchmark pattern and ensures zero data loss during sync.
"""

from datetime import datetime
from typing import List, Optional

from connector_context.platform.entities._connector_context_field import ConnectorContextField
from connector_context.platform.entities._base import BaseEntity


class EnronEmailEntity(BaseEntity):
    """Individual email from the Enron Email Dataset (HuggingFace: corbt/enron-emails)."""

    message_id: str = ConnectorContextField(
        ...,
        description=(
            "RFC 822 Message-ID header (e.g. '<17407857.1075840601283.JavaMail.evans@thyme>')"
        ),
        is_entity_id=True,
    )
    subject: str = ConnectorContextField(
        ...,
        description="Email subject line",
        is_name=True,
        embeddable=True,
    )
    body: str = ConnectorContextField(
        ...,
        description="Full email body text",
        embeddable=True,
    )
    sender: str = ConnectorContextField(
        ...,
        description="Sender email address (e.g. 'phillip.allen@enron.com')",
        embeddable=True,
    )
    to: List[str] = ConnectorContextField(
        default_factory=list,
        description="To recipients",
        embeddable=True,
    )
    cc: List[str] = ConnectorContextField(
        default_factory=list,
        description="CC recipients",
        embeddable=True,
    )
    bcc: List[str] = ConnectorContextField(
        default_factory=list,
        description="BCC recipients",
        embeddable=True,
    )
    sent_at: Optional[datetime] = ConnectorContextField(
        None,
        description="Email send date from the Date header",
        is_created_at=True,
    )
