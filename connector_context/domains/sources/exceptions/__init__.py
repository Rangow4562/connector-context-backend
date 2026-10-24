"""Source domain exceptions.

Re-exports all exception classes so ``from connector_context.domains.sources.exceptions import …``
continues to work after the module-to-package conversion.
"""

from connector_context.domains.sources.exceptions._exceptions import (  # noqa: F401
    SourceAuthError,
    SourceCreationError,
    SourceEntityError,
    SourceEntityForbiddenError,
    SourceEntityNotFoundError,
    SourceEntitySkippedError,
    SourceError,
    SourceFileDownloadError,
    SourceNotFoundError,
    SourcePermanentError,
    SourceRateLimitError,
    SourceServerError,
    SourceTemporaryError,
    SourceTokenRefreshError,
    SourceValidationError,
)
