"""Event bus adapter.

Implements the EventBus protocol with in-memory fan-out to subscribers.
"""

from connector_context.adapters.event_bus.fake import FakeEventBus
from connector_context.adapters.event_bus.in_memory import InMemoryEventBus

__all__ = ["InMemoryEventBus", "FakeEventBus"]
