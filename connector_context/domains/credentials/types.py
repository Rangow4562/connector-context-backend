"""Credential domain types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


@dataclass(frozen=True)
class DecryptedCredential:
    """Canonical shape for a decrypted integration credential.

    Wraps the raw dict from the database with typed accessors so callers
    never need to guess the credential shape.  Immutable — use
    ``with_updated_token`` to obtain a copy with a fresh access_token.
    """

    credential_id: UUID
    integration_short_name: str
    raw: dict

    @property
    def access_token(self) -> Optional[str]:
        """Return the OAuth access token, if present."""
        return self.raw.get("access_token")

    @property
    def refresh_token(self) -> Optional[str]:
        """Return the OAuth refresh token, if present."""
        return self.raw.get("refresh_token")

    @property
    def has_refresh_token(self) -> bool:
        """Check whether a non-empty refresh token exists."""
        rt = self.raw.get("refresh_token")
        return bool(rt and str(rt).strip())

    def with_updated_token(self, access_token: str) -> DecryptedCredential:
        """Return a copy with a fresh access_token."""
        updated = {**self.raw, "access_token": access_token}
        return DecryptedCredential(
            credential_id=self.credential_id,
            integration_short_name=self.integration_short_name,
            raw=updated,
        )

    def to_auth_config(self, auth_config_class: type[BaseModel]) -> BaseModel:
        """Validate raw dict into a typed auth config model."""
        return auth_config_class.model_validate(self.raw)
