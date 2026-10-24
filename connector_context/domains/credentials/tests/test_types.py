"""Unit tests for DecryptedCredential."""

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest
from pydantic import BaseModel

from connector_context.domains.credentials.types import DecryptedCredential


CID = uuid4()


def _dc(raw: dict) -> DecryptedCredential:
    return DecryptedCredential(credential_id=CID, integration_short_name="gmail", raw=raw)


class TestAccessToken:
    def test_present(self):
        assert _dc({"access_token": "tok"}).access_token == "tok"

    def test_missing(self):
        assert _dc({}).access_token is None


class TestRefreshToken:
    def test_present(self):
        assert _dc({"refresh_token": "rt"}).refresh_token == "rt"

    def test_missing(self):
        assert _dc({}).refresh_token is None


class TestHasRefreshToken:
    def test_present(self):
        assert _dc({"refresh_token": "rt"}).has_refresh_token is True

    def test_missing(self):
        assert _dc({}).has_refresh_token is False

    def test_empty_string(self):
        assert _dc({"refresh_token": ""}).has_refresh_token is False

    def test_whitespace_only(self):
        assert _dc({"refresh_token": "  "}).has_refresh_token is False

    def test_none_value(self):
        assert _dc({"refresh_token": None}).has_refresh_token is False


class TestWithUpdatedToken:
    def test_returns_new_instance(self):
        orig = _dc({"access_token": "old", "refresh_token": "rt"})
        updated = orig.with_updated_token("new")

        assert updated is not orig
        assert updated.access_token == "new"
        assert updated.refresh_token == "rt"
        assert updated.credential_id == orig.credential_id
        assert updated.integration_short_name == orig.integration_short_name

    def test_original_unchanged(self):
        orig = _dc({"access_token": "old"})
        orig.with_updated_token("new")
        assert orig.access_token == "old"


class TestToAuthConfig:
    def test_validates_into_model(self):
        class GmailAuth(BaseModel):
            access_token: str
            refresh_token: str

        dc = _dc({"access_token": "tok", "refresh_token": "rt"})
        cfg = dc.to_auth_config(GmailAuth)

        assert isinstance(cfg, GmailAuth)
        assert cfg.access_token == "tok"
        assert cfg.refresh_token == "rt"

    def test_validation_error_propagates(self):
        class StrictAuth(BaseModel):
            api_key: str

        dc = _dc({"wrong_field": "val"})
        with pytest.raises(Exception):
            dc.to_auth_config(StrictAuth)


class TestFrozen:
    def test_cannot_mutate_fields(self):
        dc = _dc({"access_token": "tok"})
        with pytest.raises((AttributeError, FrozenInstanceError)):
            dc.credential_id = uuid4()  # type: ignore[misc]
