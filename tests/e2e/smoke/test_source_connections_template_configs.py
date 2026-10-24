"""
Async test module for OAuth source connections with template configs.

Tests the new template configs feature that allows sources to require
config fields before OAuth flow can begin (e.g., instance-specific URLs).
"""

import pytest
import httpx
from typing import Dict
from urllib.parse import parse_qs, urlparse, unquote


def verify_redirect_uri(provider_url: str, expected_api_url: str) -> None:
    """Helper to verify redirect_uri parameter in OAuth URL.

    Args:
        provider_url: The OAuth provider URL
        expected_api_url: Expected API URL (e.g., http://localhost:8001)
    """
    parsed = urlparse(provider_url)
    params = parse_qs(parsed.query)

    assert "redirect_uri" in params, f"OAuth URL should have redirect_uri parameter: {provider_url}"
    redirect_uri = unquote(params["redirect_uri"][0])

    expected_redirect = f"{expected_api_url}/source-connections/callback"
    assert (
        redirect_uri == expected_redirect
    ), f"redirect_uri should be {expected_redirect}, got {redirect_uri}"


class TestTemplateConfigs:
    """Test suite for OAuth source connections with template configs."""

    @pytest.mark.asyncio
    async def test_zendesk_oauth_browser_with_template_config(
        self, api_client: httpx.AsyncClient, collection: Dict, config
    ):
        """Test Zendesk OAuth browser flow with subdomain template config.

        Note: Zendesk requires BYOC (bring your own credentials), so we provide dummy client credentials.
        """
        payload = {
            "name": "Test Zendesk OAuth Browser",
            "short_name": "zendesk",
            "readable_collection_id": collection["readable_id"],
            "description": "Testing OAuth browser flow with template configs",
            "config": {
                "subdomain": "testcompany",
                "exclude_closed_tickets": False,
            },
            "authentication": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
            },
            "sync_immediately": False,
        }

        response = await api_client.post("/source-connections", json=payload)

        response.raise_for_status()
        connection = response.json()

        # Verify OAuth browser flow response
        assert connection["id"]
        assert connection["auth"]["method"] == "oauth_browser"
        assert connection["auth"]["authenticated"] == False
        assert connection["status"] == "pending_auth"
        assert "auth_url" in connection["auth"]

        # Auth URL should be present (Connector Context's internal authorization endpoint)
        auth_url = connection["auth"]["auth_url"]
        assert auth_url is not None
        assert isinstance(auth_url, str)
        # Template configs are used internally; the auth_url is Connector Context's endpoint
        assert "/authorize/" in auth_url or "authorize" in auth_url

        # Follow the proxy URL to verify the actual OAuth provider URL is correctly formed
        # The authorize endpoint redirects (303) to the actual provider without auth
        proxy_response = await api_client.get(auth_url, follow_redirects=False)
        assert proxy_response.status_code == 303, "Should return redirect to OAuth provider"

        provider_url = proxy_response.headers.get("location")
        assert provider_url is not None, "Should have Location header with provider URL"
        # Verify the subdomain is correctly inserted into the Zendesk OAuth URL
        assert (
            "testcompany.zendesk.com" in provider_url
        ), f"Provider URL should contain subdomain: {provider_url}"
        assert "/oauth/" in provider_url, "Should be Zendesk OAuth URL"

        # Verify redirect_uri is correct for this environment
        verify_redirect_uri(provider_url, config.api_url)

        # Cleanup
        await api_client.delete(f"/source-connections/{connection['id']}")

    @pytest.mark.asyncio
    async def test_zendesk_missing_template_config(
        self, api_client: httpx.AsyncClient, collection: Dict
    ):
        """Test Zendesk OAuth flow fails without required subdomain config."""
        payload = {
            "name": "Test Zendesk Missing Config",
            "short_name": "zendesk",
            "readable_collection_id": collection["readable_id"],
            "config": {
                # Missing subdomain - should fail
                "exclude_closed_tickets": False,
            },
            "authentication": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
            },
            "sync_immediately": False,
        }

        response = await api_client.post("/source-connections", json=payload)

        # Should fail with 422 Unprocessable Entity
        assert (
            response.status_code == 422
        ), f"Expected 422, got {response.status_code}: {response.text}"
        error = response.json()
        detail = error.get("detail", "").lower()
        assert "subdomain" in detail, f"Error should mention 'subdomain': {detail}"
        assert (
            "template" in detail or "required" in detail or "before" in detail
        ), f"Error should mention template/required: {detail}"

    @pytest.mark.asyncio
    async def test_zendesk_empty_template_config(
        self, api_client: httpx.AsyncClient, collection: Dict
    ):
        """Test Zendesk OAuth flow fails with empty subdomain config."""
        payload = {
            "name": "Test Zendesk Empty Config",
            "short_name": "zendesk",
            "readable_collection_id": collection["readable_id"],
            "config": {
                "subdomain": "",  # Empty subdomain - should fail
            },
            "authentication": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
            },
            "sync_immediately": False,
        }

        response = await api_client.post("/source-connections", json=payload)

        # Should fail with either 400 or 422
        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}: {response.text}"

    @pytest.mark.asyncio
    async def test_zendesk_no_config_at_all(self, api_client: httpx.AsyncClient, collection: Dict):
        """Test Zendesk OAuth flow fails with no config provided."""
        payload = {
            "name": "Test Zendesk No Config",
            "short_name": "zendesk",
            "readable_collection_id": collection["readable_id"],
            "authentication": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
            },
            "sync_immediately": False,
            # No config field at all
        }

        response = await api_client.post("/source-connections", json=payload)

        # Should fail with 422 Unprocessable Entity
        assert (
            response.status_code == 422
        ), f"Expected 422, got {response.status_code}: {response.text}"
        error = response.json()
        detail = error.get("detail", "").lower()
        assert "subdomain" in detail, f"Error should mention 'subdomain': {detail}"

    @pytest.mark.asyncio
    async def test_zendesk_whitespace_only_template_config(
        self, api_client: httpx.AsyncClient, collection: Dict
    ):
        """Test Zendesk OAuth flow fails with whitespace-only subdomain config."""
        payload = {
            "name": "Test Zendesk Whitespace Config",
            "short_name": "zendesk",
            "readable_collection_id": collection["readable_id"],
            "config": {
                "subdomain": "   ",  # Whitespace only - should fail
            },
            "authentication": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
            },
            "sync_immediately": False,
        }

        response = await api_client.post("/source-connections", json=payload)

        # Should fail with 422 Unprocessable Entity
        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}: {response.text}"
        error = response.json()
        detail = error.get("detail", "").lower()
        assert "subdomain" in detail, f"Error should mention 'subdomain': {detail}"

    @pytest.mark.asyncio
    async def test_zendesk_oauth_token_with_template_config(
        self, api_client: httpx.AsyncClient, collection: Dict, config
    ):
        """Test Zendesk OAuth token injection with subdomain template config."""
        # Note: This test requires a valid Zendesk OAuth token
        # Skip if TEST_ZENDESK_TOKEN is not available
        zendesk_token = getattr(config, "TEST_ZENDESK_TOKEN", None)
        if not zendesk_token:
            pytest.skip("TEST_ZENDESK_TOKEN not configured")

        payload = {
            "name": "Test Zendesk Token Injection",
            "short_name": "zendesk",
            "readable_collection_id": collection["readable_id"],
            "description": "Testing OAuth token injection with template configs",
            "config": {
                "subdomain": "testcompany",
                "exclude_closed_tickets": True,
            },
            "authentication": {"access_token": zendesk_token},
            "sync_immediately": False,
        }

        response = await api_client.post("/source-connections", json=payload)

        response.raise_for_status()
        connection = response.json()

        # Verify OAuth token injection response
        assert connection["id"]
        assert connection["auth"]["method"] == "oauth_token"
        assert connection["auth"]["authenticated"] == True
        assert connection["status"] in ["active", "syncing"]

        # Cleanup
        await api_client.delete(f"/source-connections/{connection['id']}")

    @pytest.mark.asyncio
    async def test_zendesk_byoc_with_template_config(
        self, api_client: httpx.AsyncClient, collection: Dict, config
    ):
        """Test Zendesk BYOC (Bring Your Own Credentials) with template config."""
        # Note: This test requires Zendesk client credentials
        client_id = getattr(config, "TEST_ZENDESK_CLIENT_ID", None)
        client_secret = getattr(config, "TEST_ZENDESK_CLIENT_SECRET", None)

        if not client_id or not client_secret:
            pytest.skip("TEST_ZENDESK_CLIENT_ID or TEST_ZENDESK_CLIENT_SECRET not configured")

        payload = {
            "name": "Test Zendesk BYOC",
            "short_name": "zendesk",
            "readable_collection_id": collection["readable_id"],
            "description": "Testing BYOC with template configs",
            "config": {
                "subdomain": "testcompany",
            },
            "authentication": {
                "client_id": client_id,
                "client_secret": client_secret,
            },
            "sync_immediately": False,
        }

        response = await api_client.post("/source-connections", json=payload)

        response.raise_for_status()
        connection = response.json()

        # BYOC returns oauth_browser after creation
        assert connection["id"]
        assert connection["auth"]["method"] == "oauth_browser"
        assert connection["auth"]["authenticated"] == False
        assert connection["status"] == "pending_auth"
        assert "auth_url" in connection["auth"]

        # Auth URL should be present (template configs used internally)
        auth_url = connection["auth"]["auth_url"]
        assert auth_url is not None
        assert isinstance(auth_url, str)

        # Follow the proxy URL to verify template configs are used correctly
        proxy_response = await api_client.get(auth_url, follow_redirects=False)
        assert proxy_response.status_code == 303
        provider_url = proxy_response.headers.get("location")
        assert (
            "testcompany.zendesk.com" in provider_url
        ), f"BYOC provider URL should contain subdomain: {provider_url}"

        # Verify redirect_uri is correct
        verify_redirect_uri(provider_url, config.api_url)

        # Cleanup
        await api_client.delete(f"/source-connections/{connection['id']}")

    @pytest.mark.asyncio
    async def test_non_template_source_still_works(
        self, api_client: httpx.AsyncClient, collection: Dict, config
    ):
        """Test that sources without template configs still work normally."""
        # Use Linear which doesn't require template configs
        payload = {
            "name": "Test Linear OAuth Browser",
            "short_name": "linear",
            "readable_collection_id": collection["readable_id"],
            "description": "Testing OAuth browser flow without template configs",
            "authentication": {},  # Empty for browser flow
            "sync_immediately": False,
        }

        response = await api_client.post("/source-connections", json=payload)

        response.raise_for_status()
        connection = response.json()

        # Verify OAuth browser flow response
        assert connection["id"]
        assert connection["auth"]["method"] == "oauth_browser"
        assert connection["auth"]["authenticated"] == False
        assert connection["status"] == "pending_auth"
        assert "auth_url" in connection["auth"]
        assert connection["auth"]["auth_url"] is not None

        # Verify non-template source also has correct redirect_uri
        auth_url = connection["auth"]["auth_url"]
        proxy_response = await api_client.get(auth_url, follow_redirects=False)
        assert proxy_response.status_code == 303
        provider_url = proxy_response.headers.get("location")
        verify_redirect_uri(provider_url, config.api_url)

        # Cleanup
        await api_client.delete(f"/source-connections/{connection['id']}")

    @pytest.mark.asyncio
    async def test_template_config_with_special_characters(
        self, api_client: httpx.AsyncClient, collection: Dict, config
    ):
        """Test template config with special characters in subdomain."""
        payload = {
            "name": "Test Zendesk Special Chars",
            "short_name": "zendesk",
            "readable_collection_id": collection["readable_id"],
            "config": {
                "subdomain": "test-company-123",  # Hyphens and numbers
            },
            "authentication": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
            },
            "sync_immediately": False,
        }

        response = await api_client.post("/source-connections", json=payload)

        response.raise_for_status()
        connection = response.json()

        # Verify auth URL is present (special chars in subdomain handled internally)
        auth_url = connection["auth"]["auth_url"]
        assert auth_url is not None
        assert isinstance(auth_url, str)

        # Follow the proxy to verify special characters are handled correctly in OAuth URL
        proxy_response = await api_client.get(auth_url, follow_redirects=False)
        assert proxy_response.status_code == 303
        provider_url = proxy_response.headers.get("location")
        assert (
            "test-company-123.zendesk.com" in provider_url
        ), f"Provider URL should contain subdomain with special chars: {provider_url}"

        # Verify redirect_uri
        verify_redirect_uri(provider_url, config.api_url)

        # Cleanup
        await api_client.delete(f"/source-connections/{connection['id']}")

    @pytest.mark.asyncio
    async def test_get_source_zendesk_shows_required_config_fields(
        self, api_client: httpx.AsyncClient
    ):
        """Test that GET /sources/zendesk shows which config fields are required for auth."""
        response = await api_client.get("/sources/zendesk")

        assert response.status_code == 200
        source = response.json()

        # Check that config fields are present
        assert "config_fields" in source
        config_fields = source["config_fields"]

        # config_fields is a Fields object with a "fields" list
        assert "fields" in config_fields, "config_fields should have a 'fields' property"
        fields_list = config_fields["fields"]
        assert isinstance(fields_list, list), "fields should be a list"

        # Find subdomain field
        subdomain_field = None
        for field in fields_list:
            if field["name"] == "subdomain":
                subdomain_field = field
                break

        assert subdomain_field is not None, "subdomain field should be present in config_fields"

        # Check if it's marked as required (template configs should be required)
        assert (
            subdomain_field.get("required") == True
        ), f"subdomain should be marked as required, got: {subdomain_field}"


class TestTemplateConfigEdgeCases:
    """Test edge cases and error handling for template configs."""

    @pytest.mark.asyncio
    async def test_zendesk_with_full_domain_in_subdomain(
        self, api_client: httpx.AsyncClient, collection: Dict, config
    ):
        """Test providing full domain instead of just subdomain."""
        # Users might provide "mycompany.zendesk.com" instead of "mycompany"
        payload = {
            "name": "Test Zendesk Full Domain",
            "short_name": "zendesk",
            "readable_collection_id": collection["readable_id"],
            "config": {
                "subdomain": "testcompany.zendesk.com",  # Full domain - not recommended but might work
            },
            "authentication": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
            },
            "sync_immediately": False,
        }

        response = await api_client.post("/source-connections", json=payload)

        # This should either work or fail with helpful error
        # The behavior depends on implementation - document it
        if response.status_code == 200:
            connection = response.json()
            # Verify auth URL is present
            auth_url = connection["auth"]["auth_url"]
            assert auth_url is not None

            # Check what URL gets generated with full domain as subdomain
            proxy_response = await api_client.get(auth_url, follow_redirects=False)
            assert proxy_response.status_code == 303
            provider_url = proxy_response.headers.get("location")
            # Document the behavior - it might double the domain
            assert "zendesk.com" in provider_url, f"Provider URL: {provider_url}"

            # Verify redirect_uri
            verify_redirect_uri(provider_url, config.api_url)

            await api_client.delete(f"/source-connections/{connection['id']}")
        else:
            # If it fails, error should be helpful
            assert response.status_code in [400, 422]
            error = response.json()
            detail = error.get("detail", "").lower()
            # Error should be clear about the format
            assert "subdomain" in detail

    @pytest.mark.asyncio
    async def test_zendesk_config_with_extra_fields(
        self, api_client: httpx.AsyncClient, collection: Dict, config
    ):
        """Test that extra config fields don't break template config extraction."""
        payload = {
            "name": "Test Zendesk Extra Config",
            "short_name": "zendesk",
            "readable_collection_id": collection["readable_id"],
            "config": {
                "subdomain": "testcompany",
                "exclude_closed_tickets": True,
                "extra_field": "should_be_ignored",  # Extra field
            },
            "authentication": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
            },
            "sync_immediately": False,
        }

        response = await api_client.post("/source-connections", json=payload)

        # Should succeed and ignore extra field (or fail during config validation)
        # This tests that template config extraction is selective
        if response.status_code == 200:
            connection = response.json()
            auth_url = connection["auth"]["auth_url"]
            assert auth_url is not None

            # Verify extra fields don't affect OAuth URL generation
            proxy_response = await api_client.get(auth_url, follow_redirects=False)
            assert proxy_response.status_code == 303
            provider_url = proxy_response.headers.get("location")
            assert "testcompany.zendesk.com" in provider_url

            # Verify redirect_uri
            verify_redirect_uri(provider_url, config.api_url)

            await api_client.delete(f"/source-connections/{connection['id']}")
        else:
            # If it fails, should be due to unknown field in config validation
            assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_zendesk_minimal_payload_with_config(
        self, api_client: httpx.AsyncClient, collection: Dict, config
    ):
        """Test minimal Zendesk payload with only required fields."""
        payload = {
            "short_name": "zendesk",
            "readable_collection_id": collection["readable_id"],
            "config": {
                "subdomain": "minimal-test",
            },
            "authentication": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
            },
        }

        response = await api_client.post("/source-connections", json=payload)

        response.raise_for_status()
        connection = response.json()

        # Verify defaults are applied correctly
        assert connection["name"] == "Zendesk Connection"  # Default name
        assert connection["status"] == "pending_auth"
        assert connection["auth"]["method"] == "oauth_browser"
        assert "auth_url" in connection["auth"]
        auth_url = connection["auth"]["auth_url"]
        assert auth_url is not None

        # Verify minimal payload generates correct OAuth URL
        proxy_response = await api_client.get(auth_url, follow_redirects=False)
        assert proxy_response.status_code == 303
        provider_url = proxy_response.headers.get("location")
        assert (
            "minimal-test.zendesk.com" in provider_url
        ), f"Minimal payload should generate correct URL: {provider_url}"

        # Verify redirect_uri
        verify_redirect_uri(provider_url, config.api_url)

        # Cleanup
        await api_client.delete(f"/source-connections/{connection['id']}")
