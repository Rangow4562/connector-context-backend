"""Agentic search service.

Thin composition point — constructs the Agent and delegates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from connector_context.api.context import ApiContext
from connector_context.core.protocols.event_bus import EventBus
from connector_context.core.protocols.llm import LLMProtocol
from connector_context.core.protocols.reranker import RerankerProtocol
from connector_context.core.protocols.tokenizer import TokenizerProtocol
from connector_context.domains.collections.protocols import CollectionRepositoryProtocol
from connector_context.domains.search.adapters.vector_db.protocol import VectorDBProtocol
from connector_context.domains.search.agentic.agent import Agent
from connector_context.domains.search.config import SearchConfig
from connector_context.domains.search.protocols import (
    AgenticSearchServiceProtocol,
    CollectionMetadataBuilderProtocol,
    SearchPlanExecutorProtocol,
)
from connector_context.domains.search.types import SearchResults

if TYPE_CHECKING:
    from connector_context.schemas.search_v2 import AgenticSearchRequest


class AgenticSearchService(AgenticSearchServiceProtocol):
    """Agentic search — constructs an Agent per request and delegates."""

    def __init__(
        self,
        llm: LLMProtocol,
        tokenizer: TokenizerProtocol,
        reranker: Optional[RerankerProtocol],
        executor: SearchPlanExecutorProtocol,
        vector_db: VectorDBProtocol,
        metadata_builder: CollectionMetadataBuilderProtocol,
        collection_repo: CollectionRepositoryProtocol,
        event_bus: EventBus,
    ) -> None:
        """Initialize with all dependencies needed to construct agents."""
        self._llm = llm
        self._tokenizer = tokenizer
        self._reranker = reranker
        self._executor = executor
        self._vector_db = vector_db
        self._metadata_builder = metadata_builder
        self._collection_repo = collection_repo
        self._event_bus = event_bus

    def with_llm(self, llm: LLMProtocol) -> "AgenticSearchService":
        """Return a copy of this service with a different LLM (for model override)."""
        return AgenticSearchService(
            llm=llm,
            tokenizer=self._tokenizer,
            reranker=self._reranker,
            executor=self._executor,
            vector_db=self._vector_db,
            metadata_builder=self._metadata_builder,
            collection_repo=self._collection_repo,
            event_bus=self._event_bus,
        )

    async def search(
        self,
        db: AsyncSession,
        ctx: ApiContext,
        readable_id: str,
        request: AgenticSearchRequest,
        user_principal_override: str | None = None,
    ) -> SearchResults:
        """Run agentic search and return results."""
        agent = Agent(
            llm=self._llm,
            tokenizer=self._tokenizer,
            reranker=self._reranker,
            executor=self._executor,
            vector_db=self._vector_db,
            metadata_builder=self._metadata_builder,
            collection_repo=self._collection_repo,
            event_bus=self._event_bus,
            config=SearchConfig(),
        )
        return await agent.run(
            db, ctx, readable_id, request, user_principal_override=user_principal_override
        )
