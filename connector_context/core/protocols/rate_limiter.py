"""Rate limiter protocol for API request throttling.

Adapters: Redis (production), Null (local dev / disabled), Fake (testing).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from connector_context.schemas.rate_limit import RateLimitResult

if TYPE_CHECKING:
    from connector_context import schemas


@runtime_checkable
class RateLimiter(Protocol):
    """Per-organization rate limiting with sliding window."""

    async def check(self, organization: schemas.Organization) -> RateLimitResult:
        """Check and record a request against the rate limit.

        The adapter reads billing plan info from the enriched Organization
        schema. If billing data is missing, the adapter should raise loudly
        — that indicates a data integrity problem.

        Returns:
            RateLimitResult with allowed/remaining/retry_after.

        Raises:
            RateLimitExceededException: When the limit is exceeded.
            RuntimeError: When billing data is missing (data integrity issue).
        """
        ...
