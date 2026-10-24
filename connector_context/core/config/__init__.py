"""Configuration module for Connector Context backend.

Provides centralized configuration management with type-safe enums.

Usage:
    from connector_context.core.config import settings, StorageBackendType, Environment

    # Access settings
    if settings.STORAGE_BACKEND == StorageBackendType.AWS:
        ...

    # Use enums for type safety
    if settings.ENVIRONMENT == Environment.PRD:
        ...
"""

from connector_context.core.config.enums import Environment, StorageBackendType
from connector_context.core.config.settings import Settings

__all__ = [
    "Settings",
    "StorageBackendType",
    "Environment",
    "settings",
]

# Singleton settings instance
settings = Settings()
