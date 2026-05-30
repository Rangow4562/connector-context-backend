"""Source auth provider implementations."""

from connector_context.domains.sources.token_providers.auth_provider import AuthProviderTokenProvider
from connector_context.domains.sources.token_providers.credential import DirectCredentialProvider
from connector_context.domains.sources.token_providers.oauth import OAuthTokenProvider
from connector_context.domains.sources.token_providers.protocol import (
    AuthProviderKind,
    SourceAuthProvider,
    TokenProviderProtocol,
)
from connector_context.domains.sources.token_providers.static import StaticTokenProvider

__all__ = [
    "AuthProviderKind",
    "AuthProviderTokenProvider",
    "DirectCredentialProvider",
    "OAuthTokenProvider",
    "SourceAuthProvider",
    "StaticTokenProvider",
    "TokenProviderProtocol",
]
