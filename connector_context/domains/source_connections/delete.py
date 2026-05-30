"""Source connection deletion service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from connector_context import schemas
from connector_context.api.context import ApiContext
from connector_context.core.exceptions import NotFoundException
from connector_context.domains.collections.protocols import CollectionRepositoryProtocol
from connector_context.domains.source_connections.protocols import (
    ResponseBuilderProtocol,
    SourceConnectionDeletionServiceProtocol,
    SourceConnectionRepositoryProtocol,
)
from connector_context.domains.syncs.protocols import SyncServiceProtocol
from connector_context.schemas.source_connection import SourceConnection as SourceConnectionSchema


class SourceConnectionDeletionService(SourceConnectionDeletionServiceProtocol):
    """Deletes a source connection and all related data.

    The flow is:
    1. Delegate cancel + wait + cleanup scheduling to SyncService.delete.
    2. CASCADE-delete the DB records (source connection, sync, jobs, entities).
    """

    def __init__(  # noqa: D107
        self,
        sc_repo: SourceConnectionRepositoryProtocol,
        collection_repo: CollectionRepositoryProtocol,
        response_builder: ResponseBuilderProtocol,
        sync_service: SyncServiceProtocol,
    ) -> None:
        self._sc_repo = sc_repo
        self._collection_repo = collection_repo
        self._response_builder = response_builder
        self._sync_service = sync_service

    async def delete(
        self,
        db: AsyncSession,
        *,
        id: UUID,
        ctx: ApiContext,
    ) -> SourceConnectionSchema:
        """Delete a source connection and all related data."""
        source_conn = await self._sc_repo.get(db, id=id, ctx=ctx)
        if not source_conn:
            raise NotFoundException("Source connection not found")

        sync_id = source_conn.sync_id
        collection_orm = await self._collection_repo.get_by_readable_id(
            db, readable_id=source_conn.readable_collection_id, ctx=ctx
        )
        if not collection_orm:
            raise NotFoundException("Collection not found")
        collection = schemas.CollectionRecord.model_validate(collection_orm, from_attributes=True)

        response = await self._response_builder.build_response(db, source_conn, ctx)

        if sync_id:
            await self._sync_service.delete(
                db,
                sync_id=sync_id,
                collection_id=collection.id,
                organization_id=collection.organization_id,
                ctx=ctx,
                cancel_timeout_seconds=15,
            )

        await self._sc_repo.remove(db, id=id, ctx=ctx)

        return response
