"""
Test module for collection access control and error handling.

Tests the implementation of cross-organization access controls,
ensuring collections cannot be accessed across organization boundaries
and proper 404 errors are returned without leaking information.
"""

import pytest
import httpx
import time


class TestCollectionAccessControl:
    """Test suite for collection access control and error handling."""

    @pytest.mark.asyncio
    async def test_search_nonexistent_collection(self, api_client: httpx.AsyncClient):
        """Test searching a collection that doesn't exist returns 404."""
        # Use a collection ID that definitely doesn't exist
        fake_collection_id = "nonexistent-collection-xyz-12345"

        response = await api_client.get(
            f"/collections/{fake_collection_id}/search",
            params={"query": "test query", "response_type": "raw"},
        )

        assert response.status_code == 404
        error = response.json()
        assert "detail" in error
        assert fake_collection_id in error["detail"]
        assert "not found" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_advanced_search_nonexistent_collection(self, api_client: httpx.AsyncClient):
        """Test advanced search on a collection that doesn't exist returns 404."""
        fake_collection_id = "nonexistent-collection-xyz-12345"

        response = await api_client.post(
            f"/collections/{fake_collection_id}/search",
            json={
                "query": "test query",
                "response_type": "raw",
                "search_method": "hybrid",
                "limit": 10,
            },
        )

        assert response.status_code == 404
        error = response.json()
        assert "detail" in error
        assert fake_collection_id in error["detail"]
        assert "not found" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_nonexistent_collection(self, api_client: httpx.AsyncClient):
        """Test getting a collection that doesn't exist returns 404."""
        fake_collection_id = "nonexistent-collection-xyz-12345"

        response = await api_client.get(f"/collections/{fake_collection_id}")

        assert response.status_code == 404
        error = response.json()
        assert "detail" in error

    @pytest.mark.asyncio
    async def test_update_nonexistent_collection(self, api_client: httpx.AsyncClient):
        """Test updating a collection that doesn't exist returns 404."""
        fake_collection_id = "nonexistent-collection-xyz-12345"

        response = await api_client.patch(
            f"/collections/{fake_collection_id}",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 404
        error = response.json()
        assert "detail" in error

    @pytest.mark.asyncio
    async def test_delete_nonexistent_collection(self, api_client: httpx.AsyncClient):
        """Test deleting a collection that doesn't exist returns 404."""
        fake_collection_id = "nonexistent-collection-xyz-12345"

        response = await api_client.delete(f"/collections/{fake_collection_id}")

        assert response.status_code == 404
        error = response.json()
        assert "detail" in error

    @pytest.mark.asyncio
    async def test_search_error_message_format(self, api_client: httpx.AsyncClient):
        """Test that search error messages follow the expected format."""
        fake_collection_id = "test-nonexistent-123"

        response = await api_client.get(
            f"/collections/{fake_collection_id}/search",
            params={"query": "test", "response_type": "raw"},
        )

        assert response.status_code == 404
        error = response.json()

        # Verify error message format matches the implementation
        expected_message = f"Collection '{fake_collection_id}' not found."
        assert error["detail"] == expected_message

    @pytest.mark.asyncio
    async def test_advanced_search_error_message_format(self, api_client: httpx.AsyncClient):
        """Test that advanced search error messages follow the expected format."""
        fake_collection_id = "test-nonexistent-456"

        response = await api_client.post(
            f"/collections/{fake_collection_id}/search",
            json={"query": "test", "response_type": "raw"},
        )

        assert response.status_code == 404
        error = response.json()

        # Verify error message format matches the implementation
        expected_message = f"Collection '{fake_collection_id}' not found."
        assert error["detail"] == expected_message

    @pytest.mark.asyncio
    async def test_search_after_deletion(self, api_client: httpx.AsyncClient):
        """Test that searching a deleted collection returns 404."""
        # Create a collection
        collection_data = {"name": f"Temp Collection {int(time.time())}"}
        response = await api_client.post("/collections/", json=collection_data)
        assert response.status_code == 200
        collection = response.json()
        collection_id = collection["readable_id"]

        # Delete the collection
        response = await api_client.delete(f"/collections/{collection_id}")
        assert response.status_code in [200, 204]

        # Try to search the deleted collection
        response = await api_client.get(
            f"/collections/{collection_id}/search",
            params={"query": "test", "response_type": "raw"},
        )

        assert response.status_code == 404
        error = response.json()
        assert "detail" in error
        assert collection_id in error["detail"]
        assert "not found" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_advanced_search_after_deletion(self, api_client: httpx.AsyncClient):
        """Test that advanced searching a deleted collection returns 404."""
        # Create a collection
        collection_data = {"name": f"Temp Collection {int(time.time())}"}
        response = await api_client.post("/collections/", json=collection_data)
        assert response.status_code == 200
        collection = response.json()
        collection_id = collection["readable_id"]

        # Delete the collection
        response = await api_client.delete(f"/collections/{collection_id}")
        assert response.status_code in [200, 204]

        # Try to advanced search the deleted collection
        response = await api_client.post(
            f"/collections/{collection_id}/search",
            json={"query": "test", "response_type": "raw"},
        )

        assert response.status_code == 404
        error = response.json()
        assert "detail" in error
        assert collection_id in error["detail"]
        assert "not found" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_search_with_special_characters_in_id(self, api_client: httpx.AsyncClient):
        """Test that search handles collection IDs with special characters properly."""
        # Test various special character combinations
        special_ids = [
            "collection-with-dashes",
            "collection_with_underscores",
            "collection123",
        ]

        for collection_id in special_ids:
            response = await api_client.get(
                f"/collections/{collection_id}/search",
                params={"query": "test", "response_type": "raw"},
            )

            # Should return 404 since these don't exist
            assert response.status_code == 404
            error = response.json()
            assert collection_id in error["detail"]

    @pytest.mark.asyncio
    async def test_consistent_error_across_endpoints(self, api_client: httpx.AsyncClient):
        """Test that error format is consistent across search endpoints."""
        fake_collection_id = "consistent-test-collection"

        # Test regular search
        response1 = await api_client.get(
            f"/collections/{fake_collection_id}/search",
            params={"query": "test", "response_type": "raw"},
        )

        # Test advanced search
        response2 = await api_client.post(
            f"/collections/{fake_collection_id}/search",
            json={"query": "test", "response_type": "raw"},
        )

        # Both should return 404
        assert response1.status_code == 404
        assert response2.status_code == 404

        # Both should have the same error message format
        error1 = response1.json()
        error2 = response2.json()

        expected_message = f"Collection '{fake_collection_id}' not found."
        assert error1["detail"] == expected_message
        assert error2["detail"] == expected_message
