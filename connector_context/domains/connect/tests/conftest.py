"""Domain-specific fixtures for Connect tests."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from connector_context.api.context import ApiContext
from connector_context.core.logging import logger
from connector_context.core.shared_models import AuthMethod
from connector_context.domains.collections.fakes.repository import FakeCollectionRepository
from connector_context.domains.connect.service import ConnectService
from connector_context.domains.organizations.fakes.repository import FakeOrganizationRepository
from connector_context.domains.source_connections.fakes.service import FakeSourceConnectionService
from connector_context.domains.sources.fakes.service import FakeSourceService
from connector_context.domains.syncs.jobs.fakes.repository import FakeSyncJobRepository
from connector_context.schemas.connect_session import ConnectSessionContext, ConnectSessionMode
from connector_context.schemas.organization import Organization

NOW = datetime.now(timezone.utc)
ORG_ID = uuid4()
SESSION_ID = uuid4()
COLLECTION_ID = "test-collection-abc"


def make_org(org_id=ORG_ID) -> Organization:
    return Organization(id=str(org_id), name="Test Org", created_at=NOW, modified_at=NOW)


def make_session(
    mode: ConnectSessionMode = ConnectSessionMode.ALL,
    allowed_integrations=None,
    end_user_id=None,
    org_id=ORG_ID,
    collection_id=COLLECTION_ID,
) -> ConnectSessionContext:
    return ConnectSessionContext(
        session_id=SESSION_ID,
        organization_id=org_id,
        collection_id=collection_id,
        allowed_integrations=allowed_integrations,
        mode=mode,
        end_user_id=end_user_id,
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )


def make_ctx(org_id=ORG_ID) -> ApiContext:
    org = make_org(org_id)
    return ApiContext(
        request_id="test-req",
        organization=org,
        auth_method=AuthMethod.SYSTEM,
        logger=logger.with_context(request_id="test-req"),
    )


@pytest.fixture
def org_repo():
    repo = FakeOrganizationRepository()
    repo.seed(ORG_ID, make_org())
    return repo


@pytest.fixture
def sc_service(fake_sync_service):
    return FakeSourceConnectionService(sync_service=fake_sync_service)


@pytest.fixture
def source_service():
    return FakeSourceService()


@pytest.fixture
def collection_repo():
    return FakeCollectionRepository()


@pytest.fixture
def sync_job_repo():
    return FakeSyncJobRepository()


@pytest.fixture
def connect_service(org_repo, sc_service, source_service, collection_repo, sync_job_repo):
    from unittest.mock import AsyncMock

    return ConnectService(
        source_connection_service=sc_service,
        source_service=source_service,
        org_repo=org_repo,
        collection_repo=collection_repo,
        sync_job_repo=sync_job_repo,
        oauth_callback_service=AsyncMock(),
    )
