"""HERB Messaging source — syncs Slack messages from the HERB benchmark dataset."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import AsyncGenerator, Dict

from connector_context.core.logging import ContextualLogger
from connector_context.domains.browse_tree.types import NodeSelectionData
from connector_context.domains.sources.token_providers.protocol import SourceAuthProvider
from connector_context.domains.storage.file_service import FileService
from connector_context.domains.syncs.cursors.cursor import SyncCursor
from connector_context.platform.configs.auth import HerbAuthConfig
from connector_context.platform.configs.config import HerbConfig
from connector_context.platform.decorators import source
from connector_context.platform.entities._base import BaseEntity, Breadcrumb
from connector_context.platform.entities.herb_messaging import HerbMessageEntity
from connector_context.platform.http_client.connector_context_client import ConnectorContextHttpClient
from connector_context.platform.sources._base import BaseSource
from connector_context.schemas.source_connection import AuthenticationMethod


@source(
    name="HERB Messaging",
    short_name="herb_messaging",
    auth_methods=[AuthenticationMethod.DIRECT],
    auth_config_class=HerbAuthConfig,
    config_class=HerbConfig,
    labels=["Benchmark", "HERB"],
    internal=True,
)
class HerbMessagingSource(BaseSource):
    """Source that syncs Slack messages from the HERB benchmark dataset."""

    def __init__(
        self,
        *,
        auth: SourceAuthProvider,
        logger: ContextualLogger,
        http_client: ConnectorContextHttpClient,
    ) -> None:
        """Initialize the HERB messaging source."""
        super().__init__(auth=auth, logger=logger, http_client=http_client)
        self.data_dir: str = ""
        self._employees: Dict[str, Dict] = {}

    @classmethod
    async def create(
        cls,
        *,
        auth: SourceAuthProvider,
        logger: ContextualLogger,
        http_client: ConnectorContextHttpClient,
        config: HerbConfig,
    ) -> HerbMessagingSource:
        """Create a new HERB messaging source instance."""
        instance = cls(auth=auth, logger=logger, http_client=http_client)
        if config:
            instance.data_dir = config.data_dir if hasattr(config, "data_dir") else ""
        return instance

    def _load_employees(self) -> None:
        """Load employee directory for name resolution."""
        emp_path = os.path.join(self.data_dir, "metadata", "employee.json")
        if os.path.exists(emp_path):
            with open(emp_path) as f:
                self._employees = json.load(f)

    async def generate_entities(
        self,
        *,
        cursor: SyncCursor | None = None,
        files: FileService | None = None,
        node_selections: list[NodeSelectionData] | None = None,
    ) -> AsyncGenerator[BaseEntity, None]:
        """Generate HerbMessageEntity instances from HERB product files."""
        self._load_employees()
        products_dir = os.path.join(self.data_dir, "products")

        for fname in sorted(os.listdir(products_dir)):
            if not fname.endswith(".json"):
                continue

            product_name = fname.replace(".json", "")
            with open(os.path.join(products_dir, fname)) as f:
                data = json.load(f)

            for msg in data.get("slack", []):
                channel = msg.get("Channel", {})
                user_data = msg.get("Message", {}).get("User", {})
                sender_id = user_data.get("userId", "unknown")

                # Resolve sender name from employee directory
                emp = self._employees.get(sender_id, {})
                sender_name = emp.get("name") if emp else None

                # Parse timestamp
                ts_str = user_data.get("timestamp", "")
                try:
                    message_time = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):
                    message_time = datetime(2026, 1, 1)

                channel_id = channel.get("channelID", "")
                channel_name = channel.get("name", "")

                yield HerbMessageEntity(
                    message_id=msg["id"],
                    text=user_data.get("text", ""),
                    sender_id=sender_id,
                    sender_name=sender_name,
                    channel_name=channel_name,
                    channel_id=channel_id,
                    message_time=message_time,
                    product_name=product_name,
                    breadcrumbs=[
                        Breadcrumb(
                            entity_id=product_name,
                            name=product_name,
                            entity_type="HerbProduct",
                        ),
                        Breadcrumb(
                            entity_id=channel_id,
                            name=f"#{channel_name}",
                            entity_type="HerbChannel",
                        ),
                    ],
                )

    async def validate(self) -> None:
        """Validate that the HERB data directory exists and contains product files."""
        products_dir = os.path.join(self.data_dir, "products")
        if not (
            os.path.isdir(products_dir)
            and any(f.endswith(".json") for f in os.listdir(products_dir))
        ):
            raise ValueError(f"HERB data dir '{products_dir}' missing or has no product JSON files")
