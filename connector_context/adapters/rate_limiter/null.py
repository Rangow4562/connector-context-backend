"""Null rate limiter — always allows. For local dev or DISABLE_RATE_LIMIT."""

from connector_context import schemas
from connector_context.core.protocols.rate_limiter import RateLimiter
from connector_context.schemas.rate_limit import RateLimitResult

UNLIMITED = RateLimitResult(allowed=True, retry_after=0.0, limit=9999, remaining=9999)


class NullRateLimiter(RateLimiter):
    """No-op rate limiter. Every request is allowed."""

    async def check(self, organization: schemas.Organization) -> RateLimitResult:
        """Always allow."""
        return UNLIMITED
