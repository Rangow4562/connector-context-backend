"""Fake integration credential service for testing."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from connector_context.api.context import ApiContext
from connector_context.db.unit_of_work import UnitOfWork
from connector_context.domains.credentials.protocols import IntegrationCredentialServiceProtocol
from connector_context.domains.credentials.types import DecryptedCredential
from connector_context.models.integration_credential import IntegrationCredential
from connector_context.schemas.source_connection import AuthenticationMethod, OAuthType


class FakeIntegrationCredentialService(IntegrationCredentialServiceProtocol):
    """In-memory fake for IntegrationCredentialServiceProtocol."""

    def __init__(self) -> None:
        self._store: dict[UUID, DecryptedCredential] = {}
        self._records: dict[UUID, IntegrationCredential] = {}
        self._calls: list[tuple] = []

    def seed(self, credential: DecryptedCredential, record: IntegrationCredential) -> None:
        """Pre-populate the store with a credential for testing."""
        self._store[credential.credential_id] = credential
        self._records[credential.credential_id] = record

    async def get(
        self,
        db: AsyncSession,
        credential_id: UUID,
        ctx: ApiContext,
    ) -> DecryptedCredential:
        """Get a credential from the in-memory store."""
        self._calls.append(("get", credential_id))
        cred = self._store.get(credential_id)
        if cred is None:
            from connector_context.core.exceptions import NotFoundException

            raise NotFoundException("Integration credential not found")
        return cred

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
        """Create and store a fake credential record."""
        self._calls.append(("create", short_name, auth_payload))
        from uuid import uuid4

        from connector_context.core.shared_models import IntegrationType

        record = IntegrationCredential(
            id=uuid4(),
            organization_id=ctx.organization.id,
            name=f"{source_name} - {ctx.organization.id}",
            integration_short_name=short_name,
            integration_type=IntegrationType.SOURCE,
            authentication_method=auth_method,
            oauth_type=oauth_type,
            auth_config_class=auth_config_name,
            encrypted_credentials="fake-encrypted",
        )
        dc = DecryptedCredential(
            credential_id=record.id,
            integration_short_name=short_name,
            raw=auth_payload,
        )
        rid = UUID(str(record.id))
        self._store[rid] = dc
        self._records[rid] = record
        return record

    async def update(
        self,
        db: AsyncSession,
        credential: DecryptedCredential,
        ctx: ApiContext,
        uow: Optional[UnitOfWork] = None,
    ) -> IntegrationCredential:
        """Update a credential in the in-memory store."""
        self._calls.append(("update", credential.credential_id, credential.raw))
        record = self._records.get(credential.credential_id)
        if record is None:
            from connector_context.core.exceptions import NotFoundException

            raise NotFoundException("Integration credential not found")
        self._store[credential.credential_id] = credential
        record.encrypted_credentials = "fake-re-encrypted"
        return record
