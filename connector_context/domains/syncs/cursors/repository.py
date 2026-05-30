"""Sync cursor repository wrapping crud.sync_cursor."""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from connector_context import crud
from connector_context.api.context import ApiContext
from connector_context.domains.syncs.protocols import SyncCursorRepositoryProtocol
from connector_context.models.sync_cursor import SyncCursor


class SyncCursorRepository(SyncCursorRepositoryProtocol):
    """Delegates to the crud.sync_cursor singleton."""

    async def get_by_sync_id(
        self, db: AsyncSession, sync_id: UUID, ctx: ApiContext
    ) -> Optional[SyncCursor]:
        """Get the sync cursor for a given sync."""
        return await crud.sync_cursor.get_by_sync_id(db, sync_id=sync_id, ctx=ctx)
