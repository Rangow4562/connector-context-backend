"""HERB Code Review entity schemas."""

from datetime import datetime
from typing import Optional

from connector_context.platform.entities._connector_context_field import ConnectorContextField
from connector_context.platform.entities._base import BaseEntity

__all__ = ["HerbPullRequestEntity"]


class HerbPullRequestEntity(BaseEntity):
    """GitHub pull request from the HERB benchmark dataset."""

    pr_id: str = ConnectorContextField(
        ...,
        description="HERB PR ID (e.g. 'github_com_salesforce_backAIX_pull_1')",
        is_entity_id=True,
    )
    title: str = ConnectorContextField(
        ...,
        description="PR title",
        is_name=True,
        embeddable=True,
    )
    summary: str = ConnectorContextField(
        ...,
        description="PR summary/description",
        embeddable=True,
    )
    pr_link: str = ConnectorContextField(
        ...,
        description="PR URL (ground truth for PR-type questions)",
        embeddable=True,
    )
    state: str = ConnectorContextField(
        ...,
        description="PR state (open, closed, etc.)",
        embeddable=True,
    )
    merged: str = ConnectorContextField(
        ...,
        description="Whether PR is merged (string 'True'/'False' in HERB)",
        embeddable=True,
    )
    number: str = ConnectorContextField(
        ...,
        description="PR number",
        embeddable=True,
    )
    author_login: str = ConnectorContextField(
        ...,
        description="PR author login (eid_* or EMP_*)",
        embeddable=True,
    )
    reviews_text: Optional[str] = ConnectorContextField(
        None,
        description="Concatenated review comments with reviewer and state",
        embeddable=True,
    )
    pr_created_at: Optional[datetime] = ConnectorContextField(
        None,
        description="PR creation timestamp",
        is_created_at=True,
    )
    product_name: str = ConnectorContextField(
        ...,
        description="HERB product name this PR belongs to",
        embeddable=True,
    )
