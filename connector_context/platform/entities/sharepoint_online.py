"""SharePoint Online Entities.

Entity hierarchy:
- SharePointOnlineSiteEntity (BaseEntity) - Sites
- SharePointOnlineDriveEntity (BaseEntity) - Document libraries (drives)
- SharePointOnlineItemEntity (BaseEntity) - List items
- SharePointOnlineFileEntity (FileEntity) - Files in drives
- SharePointOnlinePageEntity (BaseEntity) - Site pages

Deletion markers for incremental sync:
- SharePointOnlineFileDeletionEntity
- SharePointOnlineItemDeletionEntity
"""

from datetime import datetime
from typing import Any, Dict, Optional

from connector_context.platform.entities._connector_context_field import ConnectorContextField
from connector_context.platform.entities._base import BaseEntity, DeletionEntity, FileEntity


class SharePointOnlineSiteEntity(BaseEntity):
    """SharePoint Online site."""

    site_id: str = ConnectorContextField(..., description="Graph site ID", is_entity_id=True)
    display_name: str = ConnectorContextField(
        ..., description="Site display name", is_name=True, embeddable=True
    )
    web_url: str = ConnectorContextField(..., description="Site web URL")
    description: Optional[str] = ConnectorContextField(
        None, description="Site description", embeddable=True
    )
    is_personal_site: bool = ConnectorContextField(
        False, description="Whether this is a OneDrive personal site"
    )
    created_at: Optional[datetime] = ConnectorContextField(
        None, description="Creation time", is_created_at=True
    )
    last_modified_at: Optional[datetime] = ConnectorContextField(
        None, description="Last modified time", is_updated_at=True
    )


class SharePointOnlineDriveEntity(BaseEntity):
    """SharePoint Online document library (drive)."""

    drive_id: str = ConnectorContextField(..., description="Graph drive ID", is_entity_id=True)
    name: str = ConnectorContextField(..., description="Drive name", is_name=True, embeddable=True)
    drive_type: str = ConnectorContextField("documentLibrary", description="Drive type")
    web_url: str = ConnectorContextField(..., description="Drive web URL")
    description: Optional[str] = ConnectorContextField(
        None, description="Drive description", embeddable=True
    )
    site_id: str = ConnectorContextField(..., description="Parent site ID")
    quota_total: Optional[int] = ConnectorContextField(None, description="Total quota in bytes")
    quota_used: Optional[int] = ConnectorContextField(None, description="Used quota in bytes")
    created_at: Optional[datetime] = ConnectorContextField(
        None, description="Creation time", is_created_at=True
    )
    last_modified_at: Optional[datetime] = ConnectorContextField(
        None, description="Last modified time", is_updated_at=True
    )


class SharePointOnlineItemEntity(BaseEntity):
    """SharePoint Online list item (non-file)."""

    spo_entity_id: str = ConnectorContextField(
        ...,
        description="Composite entity ID: spo:item:{site_id}:{list_id}:{item_id}",
        is_entity_id=True,
    )
    item_id: str = ConnectorContextField(..., description="Graph item ID")
    list_id: str = ConnectorContextField(..., description="Parent list ID")
    site_id: str = ConnectorContextField(..., description="Parent site ID")
    title: str = ConnectorContextField(..., description="Item title", is_name=True, embeddable=True)
    web_url: str = ConnectorContextField(..., description="Item web URL")
    content_type: Optional[str] = ConnectorContextField(None, description="Content type name")
    fields: Dict[str, Any] = ConnectorContextField(
        default_factory=dict,
        description="List item field values",
        embeddable=True,
    )
    created_at: Optional[datetime] = ConnectorContextField(
        None, description="Creation time", is_created_at=True
    )
    updated_at: Optional[datetime] = ConnectorContextField(
        None, description="Last modified time", is_updated_at=True
    )


class SharePointOnlineFileEntity(FileEntity):
    """SharePoint Online file in a document library."""

    spo_entity_id: str = ConnectorContextField(
        ...,
        description="Composite entity ID: spo:file:{drive_id}:{item_id}",
        is_entity_id=True,
    )
    item_id: str = ConnectorContextField(..., description="Graph drive item ID")
    drive_id: str = ConnectorContextField(..., description="Parent drive ID")
    site_id: str = ConnectorContextField(..., description="Parent site ID")
    file_name: str = ConnectorContextField(
        ..., description="File name with extension", is_name=True, embeddable=True
    )
    web_url: str = ConnectorContextField(..., description="File web URL")
    download_url: Optional[str] = ConnectorContextField(
        None, description="Direct download URL", unhashable=True
    )
    parent_path: Optional[str] = ConnectorContextField(None, description="Parent folder path")
    created_by: Optional[str] = ConnectorContextField(None, description="Created by user email/name")
    last_modified_by: Optional[str] = ConnectorContextField(
        None, description="Last modified by user email/name"
    )
    created_at: Optional[datetime] = ConnectorContextField(
        None, description="Creation time", is_created_at=True
    )
    updated_at: Optional[datetime] = ConnectorContextField(
        None, description="Last modified time", is_updated_at=True
    )


class SharePointOnlinePageEntity(BaseEntity):
    """SharePoint Online site page."""

    page_id: str = ConnectorContextField(..., description="Graph page ID", is_entity_id=True)
    title: str = ConnectorContextField(..., description="Page title", is_name=True, embeddable=True)
    web_url: str = ConnectorContextField(..., description="Page web URL")
    description: Optional[str] = ConnectorContextField(
        None, description="Page description", embeddable=True
    )
    page_content: Optional[str] = ConnectorContextField(
        None, description="Page HTML content", embeddable=True
    )
    site_id: str = ConnectorContextField(..., description="Parent site ID")
    created_at: Optional[datetime] = ConnectorContextField(
        None, description="Creation time", is_created_at=True
    )
    updated_at: Optional[datetime] = ConnectorContextField(
        None, description="Last modified time", is_updated_at=True
    )


class SharePointOnlineFileDeletionEntity(DeletionEntity):
    """Deletion marker for a SharePoint Online file."""

    deletes_entity_class = SharePointOnlineFileEntity

    drive_id: str = ConnectorContextField(..., description="Drive ID of the deleted file")
    item_id: str = ConnectorContextField(..., description="Item ID of the deleted file", is_name=True)
    spo_entity_id: str = ConnectorContextField(
        ...,
        description="Entity ID of the deleted file",
        is_entity_id=True,
    )


class SharePointOnlineItemDeletionEntity(DeletionEntity):
    """Deletion marker for a SharePoint Online list item."""

    deletes_entity_class = SharePointOnlineItemEntity

    site_id: str = ConnectorContextField(..., description="Site ID of the deleted item")
    list_id: str = ConnectorContextField(..., description="List ID of the deleted item")
    item_id: str = ConnectorContextField(..., description="Item ID of the deleted item", is_name=True)
    spo_entity_id: str = ConnectorContextField(
        ...,
        description="Entity ID of the deleted item",
        is_entity_id=True,
    )
