"""Unit tests for IntegrationCredentialService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Union
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from connector_context.api.context import ApiContext
from connector_context.core.exceptions import NotFoundException
from connector_context.core.logging import logger
from connector_context.core.shared_models import AuthMethod, IntegrationType
from connector_context.db.unit_of_work import UnitOfWork
from connector_context.domains.credentials.service import IntegrationCredentialService
from connector_context.domains.credentials.types import DecryptedCredential
from connector_context.models.integration_credential import IntegrationCredential
from connector_context.schemas.integration_credential import (
    IntegrationCredentialCreateEncrypted,
    IntegrationCredentialUpdate,
)
from connector_context.schemas.organization import Organization
from connector_context.schemas.source_connection import AuthenticationMethod, OAuthType


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

CRED_ID = uuid4()
ORG_ID = uuid4()

RAW_CREDS = {"access_token": "at-123", "refresh_token": "rt-456"}


class StubEncryptor:
    """Symmetric stub: encrypt = json repr, decrypt = parse back."""

    def encrypt(self, data: dict[str, Any]) -> str:
        import json

        return json.dumps(data, sort_keys=True)

    def decrypt(self, encrypted: str) -> dict[str, Any]:
        import json

        result: dict[str, Any] = json.loads(encrypted)
        return result


class StubRepo:
    """In-memory repository stub."""

    def __init__(self) -> None:
        self._records: dict[UUID, IntegrationCredential] = {}

    def seed(self, record: IntegrationCredential) -> None:
        self._records[UUID(str(record.id))] = record

    async def get(
        self, db, id: UUID, ctx
    ) -> Optional[IntegrationCredential]:
        return self._records.get(id)

    async def create(
        self,
        db,
        *,
        obj_in: IntegrationCredentialCreateEncrypted,
        ctx,
        uow=None,
    ) -> IntegrationCredential:
        rid = uuid4()
        record = IntegrationCredential(
            id=rid,
            organization_id=ctx.organization.id,
            name=obj_in.name,
            integration_short_name=obj_in.integration_short_name,
            integration_type=obj_in.integration_type,
            authentication_method=obj_in.authentication_method,
            oauth_type=obj_in.oauth_type,
            auth_config_class=obj_in.auth_config_class,
            encrypted_credentials=obj_in.encrypted_credentials,
        )
        self._records[rid] = record
        return record

    async def update(
        self,
        db,
        *,
        db_obj: IntegrationCredential,
        obj_in: Union[IntegrationCredentialUpdate, dict],
        ctx,
        uow=None,
    ) -> IntegrationCredential:
        if isinstance(obj_in, IntegrationCredentialUpdate):
            if obj_in.encrypted_credentials is not None:
                db_obj.encrypted_credentials = obj_in.encrypted_credentials
        return db_obj


def _make_ctx() -> ApiContext:
    now = datetime.now(timezone.utc)
    org = Organization(
        id=str(ORG_ID),
        name="Test Org",
        created_at=now,
        modified_at=now,
        enabled_features=[],
    )
    return ApiContext(
        request_id="test",
        organization=org,
        auth_method=AuthMethod.SYSTEM,
        auth_metadata={},
        logger=logger.with_context(request_id="test"),
    )


def _make_record(
    cred_id: UUID = CRED_ID,
    encrypted: str = '{"access_token": "at-123", "refresh_token": "rt-456"}',
) -> IntegrationCredential:
    return IntegrationCredential(
        id=cred_id,
        organization_id=ORG_ID,
        name="Gmail - test",
        integration_short_name="gmail",
        integration_type=IntegrationType.SOURCE,
        authentication_method=AuthenticationMethod.OAUTH_BROWSER,
        encrypted_credentials=encrypted,
    )


def _make_service(
    repo: StubRepo | None = None,
) -> tuple[IntegrationCredentialService, StubRepo]:
    repo = repo or StubRepo()
    encryptor = StubEncryptor()
    return IntegrationCredentialService(repo=repo, encryptor=encryptor), repo


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


class TestGet:
    async def test_returns_decrypted_credential(self):
        svc, repo = _make_service()
        repo.seed(_make_record())

        result = await svc.get(MagicMock(), CRED_ID, _make_ctx())

        assert isinstance(result, DecryptedCredential)
        assert result.credential_id == CRED_ID
        assert result.integration_short_name == "gmail"
        assert result.access_token == "at-123"
        assert result.refresh_token == "rt-456"

    async def test_raises_not_found(self):
        svc, _ = _make_service()

        with pytest.raises(NotFoundException):
            await svc.get(MagicMock(), uuid4(), _make_ctx())


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------


class TestCreate:
    async def test_encrypts_and_persists(self):
        svc, repo = _make_service()
        ctx = _make_ctx()

        record = await svc.create(
            MagicMock(),
            short_name="gmail",
            source_name="Gmail",
            auth_payload=RAW_CREDS,
            auth_method=AuthenticationMethod.OAUTH_BROWSER,
            oauth_type=OAuthType.WITH_REFRESH,
            auth_config_name=None,
            ctx=ctx,
        )

        assert isinstance(record, IntegrationCredential)
        assert record.integration_short_name == "gmail"
        assert record.authentication_method == AuthenticationMethod.OAUTH_BROWSER

        roundtrip = StubEncryptor().decrypt(record.encrypted_credentials)
        assert roundtrip == RAW_CREDS

    async def test_name_includes_org_id(self):
        svc, _ = _make_service()
        ctx = _make_ctx()

        record = await svc.create(
            MagicMock(),
            short_name="slack",
            source_name="Slack",
            auth_payload={"api_key": "xoxb-123"},
            auth_method=AuthenticationMethod.DIRECT,
            oauth_type=None,
            auth_config_name="SlackAuthConfig",
            ctx=ctx,
        )

        assert str(ctx.organization.id) in record.name


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


class TestUpdate:
    async def test_re_encrypts_credential(self):
        svc, repo = _make_service()
        repo.seed(_make_record())
        ctx = _make_ctx()

        dc = DecryptedCredential(
            credential_id=CRED_ID,
            integration_short_name="gmail",
            raw={"access_token": "new-token", "refresh_token": "rt-456"},
        )
        record = await svc.update(MagicMock(), dc, ctx)

        roundtrip = StubEncryptor().decrypt(record.encrypted_credentials)
        assert roundtrip["access_token"] == "new-token"
        assert roundtrip["refresh_token"] == "rt-456"

    async def test_raises_not_found_for_missing_record(self):
        svc, _ = _make_service()
        dc = DecryptedCredential(
            credential_id=uuid4(),
            integration_short_name="gmail",
            raw=RAW_CREDS,
        )

        with pytest.raises(NotFoundException):
            await svc.update(MagicMock(), dc, _make_ctx())
