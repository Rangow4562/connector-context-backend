"""Integration credential repository wrapping crud.integration_credential."""

from typing import Optional, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from connector_context import crud
from connector_context.api.context import ApiContext
from connector_context.db.unit_of_work import UnitOfWork
from connector_context.domains.credentials.protocols import (
    IntegrationCredentialRepositoryProtocol,
)
from connector_context.models.integration_credential import IntegrationCredential
from connector_context.schemas.integration_credential import (
    IntegrationCredentialCreateEncrypted,
    IntegrationCredentialUpdate,
)


class IntegrationCredentialRepository(IntegrationCredentialRepositoryProtocol):
    """Delegates to the crud.integration_credential singleton."""

    async def get(
        self, db: AsyncSession, id: UUID, ctx: ApiContext
    ) -> Optional[IntegrationCredential]:
        """Get an integration credential by ID."""
        return await crud.integration_credential.get(db, id, ctx)

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: IntegrationCredential,
        obj_in: Union[IntegrationCredentialUpdate, dict],
        ctx: ApiContext,
        uow: Optional[UnitOfWork] = None,
    ) -> IntegrationCredential:
        """Update an integration credential record."""
        return await crud.integration_credential.update(
            db, db_obj=db_obj, obj_in=obj_in, ctx=ctx, uow=uow
        )

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: IntegrationCredentialCreateEncrypted,
        ctx: ApiContext,
        uow: Optional[UnitOfWork] = None,
    ) -> IntegrationCredential:
        """Create a new integration credential record."""
        return await crud.integration_credential.create(db, obj_in=obj_in, ctx=ctx, uow=uow)
