"""Storage domain.

Unified storage abstractions for persistent file and object storage
across filesystem, Azure Blob, AWS S3, and GCP GCS backends.
"""

from connector_context.domains.storage.exceptions import (
    FileSkippedException,
    StorageAuthenticationError,
    StorageConnectionError,
    StorageException,
    StorageNotFoundError,
    StorageQuotaExceededError,
)
from connector_context.domains.storage.paths import StoragePaths, paths
from connector_context.domains.storage.protocols import StorageBackend, SyncFileManagerProtocol

__all__ = [
    "StorageBackend",
    "SyncFileManagerProtocol",
    "StoragePaths",
    "paths",
    "StorageException",
    "StorageConnectionError",
    "StorageAuthenticationError",
    "StorageNotFoundError",
    "StorageQuotaExceededError",
    "FileSkippedException",
]
