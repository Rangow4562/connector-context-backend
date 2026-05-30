"""CRUD operations for integration credentials."""

from connector_context.crud._base_organization import CRUDBaseOrganization
from connector_context.models.integration_credential import IntegrationCredential
from connector_context.schemas.integration_credential import (
    IntegrationCredentialCreateEncrypted,
    IntegrationCredentialUpdate,
)


class CRUDIntegrationCredential(
    CRUDBaseOrganization[
        IntegrationCredential, IntegrationCredentialCreateEncrypted, IntegrationCredentialUpdate
    ]
):
    """CRUD operations for integration credentials."""


integration_credential = CRUDIntegrationCredential(IntegrationCredential)
