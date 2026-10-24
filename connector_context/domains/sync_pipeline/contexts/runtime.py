"""Sync runtime — per-sync mutable state.

Separated from SyncContext (frozen data) so that context is pure data
and runtime holds only per-sync mutable state.

Stateless app-scoped services (event_bus, usage_checker, embedders)
are injected directly into their consumers via constructor DI.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from connector_context.domains.sync_pipeline.pipeline.entity_tracker import EntityTracker
    from connector_context.domains.syncs.cursors.cursor import SyncCursor
    from connector_context.platform.destinations._base import BaseDestination
    from connector_context.platform.sources._base import BaseSource


@dataclass
class SyncRuntime:
    """Per-sync mutable state.

    Built by SyncFactory alongside SyncContext.
    Contains only per-sync stateful objects — stateless singletons
    (event_bus, usage_checker, embedders) are DI'd directly into consumers.
    """

    source: "BaseSource"
    entity_tracker: "EntityTracker"
    cursor: Optional["SyncCursor"] = None
    destinations: List["BaseDestination"] = field(default_factory=list)
