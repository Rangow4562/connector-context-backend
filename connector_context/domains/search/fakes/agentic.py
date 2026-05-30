"""In-memory fake for AgenticSearchServiceProtocol."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from connector_context.api.context import ApiContext
from connector_context.domains.search.protocols import AgenticSearchServiceProtocol
from connector_context.domains.search.types import SearchResults

if TYPE_CHECKING:
    from connector_context.schemas.search_v2 import AgenticSearchRequest


class FakeAgenticSearchService(AgenticSearchServiceProtocol):
    """Returns seeded or empty SearchResults. Records calls."""

    def __init__(self) -> None:
        self._result: SearchResults = SearchResults(results=[])
        self._calls: list[tuple] = []

    def seed_result(self, result: SearchResults) -> None:
        self._result = result

    async def search(
        self,
        db: AsyncSession,
        ctx: ApiContext,
        readable_id: str,
        request: AgenticSearchRequest,
    ) -> SearchResults:
        self._calls.append(("search", readable_id, request))
        return self._result
