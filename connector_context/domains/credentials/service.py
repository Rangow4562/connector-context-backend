"""Integration credential service — get, create, and update credentials."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from connector_context.api.context import ApiContext
from connector_context.core.exceptions import NotFoundException
from connector_context.core.protocols.encryption import CredentialEncryptor
from connector_context.core.shared_models import IntegrationType
from connector_context.db.unit_of_work import UnitOfWork
from connector_context.domains.credentials.protocols import (
    IntegrationCredentialRepositoryProtocol,
    IntegrationCredentialServiceProtocol,
)
from connector_context.domains.credentials.types import DecryptedCredential
from connector_context.models.integration_credential import IntegrationCredential
from connector_context.schemas.integration_credential import (
    IntegrationCredentialCreateEncrypted,
    IntegrationCredentialUpdate,
)
from connector_context.schemas.source_connection import AuthenticationMethod, OAuthType


class IntegrationCredentialService(IntegrationCredentialServiceProtocol):
    """Encrypts, decrypts, and persists integration credentials.

    Sits between domain services and the raw repository + encryptor,
    ensuring callers always receive a typed ``DecryptedCredential``
    instead of a raw dict.
    """

    def __init__(
        self,
        repo: IntegrationCredentialRepositoryProtocol,
        encryptor: CredentialEncryptor,
    ) -> None:
        """Initialize with repository and encryptor dependencies."""
        self._repo = repo
        self._encryptor = encryptor

    async def get(
        self,
        db: AsyncSession,
        credential_id: UUID,
        ctx: ApiContext,
    ) -> DecryptedCredential:
        """Get and decrypt a credential by ID."""
        record = await self._repo.get(db, credential_id, ctx)
        if not record:
            raise NotFoundException("Integration credential not found")

        raw = self._encryptor.decrypt(record.encrypted_credentials)
        return DecryptedCredential(
            credential_id=UUID(str(record.id)),
            integration_short_name=record.integration_short_name,
            raw=raw,
        )

    async def create(
        self,
        db: AsyncSession,
        *,
        short_name: str,
        source_name: str,
        auth_payload: dict[str, Any],
        auth_method: AuthenticationMethod,
        oauth_type: Optional[OAuthType],
        auth_config_name: Optional[str],
        ctx: ApiContext,
        uow: Optional[UnitOfWork] = None,
    ) -> IntegrationCredential:
        """Encrypt and persist a new credential record."""
        credential_create = IntegrationCredentialCreateEncrypted(
            name=f"{source_name} - {ctx.organization.id}",
            description=f"Credentials for {source_name} - {ctx.organization.id}",
            integration_short_name=short_name,
            integration_type=IntegrationType.SOURCE,
            authentication_method=auth_method,
            oauth_type=oauth_type,
            auth_config_class=auth_config_name,
            encrypted_credentials=self._encryptor.encrypt(auth_payload),
        )
        return await self._repo.create(db, obj_in=credential_create, ctx=ctx, uow=uow)

    async def update(
        self,
        db: AsyncSession,
        credential: DecryptedCredential,
        ctx: ApiContext,
        uow: Optional[UnitOfWork] = None,
    ) -> IntegrationCredential:
        """Re-encrypt and persist an updated DecryptedCredential."""
        record = await self._repo.get(db, credential.credential_id, ctx)
        if not record:
            raise NotFoundException("Integration credential not found")

        update = IntegrationCredentialUpdate(
            encrypted_credentials=self._encryptor.encrypt(credential.raw),
        )
        return await self._repo.update(db, db_obj=record, obj_in=update, ctx=ctx, uow=uow)
