"""Scope resolution endpoint — parse scope URLs for all source connectors."""

from pydantic import BaseModel

from connector_context.api.router import TrailingSlashRouter
from connector_context.domains.sources.url_scope_parser import ScopeParser, ScopeResolution

router = TrailingSlashRouter()


class ScopeResolveRequest(BaseModel):
    url: str


@router.post(
    "/{short_name}/resolve-scope",
    response_model=ScopeResolution,
    summary="Resolve Scope URL",
    description=(
        "Parse a scope URL or path for any source connector and return a resolution preview. "
        "Called by the frontend in real-time as the user types or pastes a scope URL. "
        "No auth required — pure URL parsing, no API calls to the source system."
    ),
)
async def resolve_scope(
    short_name: str,
    body: ScopeResolveRequest,
) -> ScopeResolution:
    """Parse a scope URL and return a human-readable resolution preview."""
    return ScopeParser.parse(short_name, body.url)
