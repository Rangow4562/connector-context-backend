"""ARF (Connector Context Raw Format) domain.

Raw entity capture for replay, debugging, and evals.
"""

from connector_context.domains.arf.protocols import ArfReaderProtocol, ArfServiceProtocol
from connector_context.domains.arf.types import EntitySerializationMeta, SyncManifest

__all__ = [
    "ArfServiceProtocol",
    "ArfReaderProtocol",
    "SyncManifest",
    "EntitySerializationMeta",
]
