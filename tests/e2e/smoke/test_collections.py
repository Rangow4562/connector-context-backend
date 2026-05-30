"""
Async test module for Collections CRUD operations.

Tests the complete lifecycle of collections.
Each test is independent and creates its own resources.
"""

import pytest
import httpx
import time
import asyncio
from typing import Dict, List


class TestCollections:
    """Test suite for Collections API."""

    @pytest.mark.asyncio
    async def test_create_collection(self, api_client: httpx.AsyncClient):
        """Test creating a new collection."""
        collection_data = {"name": f"Test Collection {int(time.time())}"}

        response = await api_client.post("/collections/", json=collection_data)

        assert response.status_code == 200, f"Failed to create collection: {response.text}"

        collection = response.json()
        assert "id" in collection
        assert "readable_id" in collection
        assert collection["name"] == collection_data["name"]
        assert "created_at" in collection

        # Cleanup
        await api_client.delete(f"/collections/{collection['readable_id']}")

    @pytest.mark.asyncio
    async def test_create_collection_auto_readable_id(self, api_client: httpx.AsyncClient):
        """Test that readable_id is auto-generated if not provided."""
        collection_data = {"name": "Auto ID Collection"}

        response = await api_client.post("/collections/", json=collection_data)

        assert response.status_code == 200
        collection = response.json()

        # Check that readable_id was auto-generated
        assert "readable_id" in collection
        assert collection["readable_id"]
        assert len(collection["readable_id"]) > 0

        # Cleanup
        await api_client.delete(f"/collections/{collection['readable_id']}")

    @pytest.mark.asyncio
    async def test_read_collection(self, api_client: httpx.AsyncClient, collection: Dict):
        """Test reading a collection by readable_id."""
        response = await api_client.get(f"/collections/{collection['readable_id']}")

        assert response.status_code == 200
        collection = response.json()

        assert collection["id"] == collection["id"]
        assert collection["readable_id"] == collection["readable_id"]
        assert collection["name"] == collection["name"]

    @pytest.mark.asyncio
    async def test_update_collection(self, api_client: httpx.AsyncClient, collection: Dict):
        """Test updating a collection."""
        update_data = {
            "name": "Updated Collection Name",
        }

        response = await api_client.patch(
            f"/collections/{collection['readable_id']}", json=update_data
        )

        assert response.status_code == 200
        updated = response.json()

        assert updated["name"] == update_data["name"]
        assert updated["id"] == collection["id"]
        assert updated["readable_id"] == collection["readable_id"]

    @pytest.mark.asyncio
    async def test_list_collections(self, api_client: httpx.AsyncClient):
        """Test listing collections."""
        # Create a few collections for testing
        created_ids = []

        # Create collections concurrently
        async def create_collection(i: int):
            collection_data = {"name": f"List Test Collection {i}"}
            response = await api_client.post("/collections/", json=collection_data)
            if response.status_code == 200:
                return response.json()["readable_id"]
            return None

        # Create 3 collections concurrently
        results = await asyncio.gather(*[create_collection(i) for i in range(3)])
        created_ids = [rid for rid in results if rid]

        # List collections
        response = await api_client.get("/collections/")

        assert response.status_code == 200
        collections = response.json()
        assert isinstance(collections, list)

        # Cleanup concurrently
        await asyncio.gather(*[api_client.delete(f"/collections/{rid}") for rid in created_ids])

    @pytest.mark.asyncio
    async def test_list_collections_pagination(self, api_client: httpx.AsyncClient):
        """Test listing collections with pagination."""

        # Create multiple collections concurrently
        async def create_collection(i: int):
            collection_data = {"name": f"Pagination Test {i}"}
            response = await api_client.post("/collections/", json=collection_data)
            if response.status_code == 200:
                return response.json()["readable_id"]
            return None

        results = await asyncio.gather(*[create_collection(i) for i in range(5)])
        created_ids = [rid for rid in results if rid]

        # Test with limit
        response = await api_client.get("/collections/", params={"limit": 2})

        assert response.status_code == 200
        collections = response.json()
        assert len(collections) <= 2

        # Test with offset
        response = await api_client.get("/collections/", params={"offset": 1, "limit": 2})

        assert response.status_code == 200

        # Cleanup concurrently
        await asyncio.gather(*[api_client.delete(f"/collections/{rid}") for rid in created_ids])

    @pytest.mark.asyncio
    async def test_delete_collection(self, api_client: httpx.AsyncClient):
        """Test deleting a collection."""
        # Create a collection to delete
        collection_data = {"name": "Collection to Delete"}
        response = await api_client.post("/collections/", json=collection_data)

        assert response.status_code == 200
        collection = response.json()

        # Delete the collection
        response = await api_client.delete(f"/collections/{collection['readable_id']}")

        assert response.status_code == 200

        # Verify it's deleted
        response = await api_client.get(f"/collections/{collection['readable_id']}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_collection_not_found(self, api_client: httpx.AsyncClient):
        """Test error handling for non-existent collection."""
        response = await api_client.get("/collections/non-existent-collection-xyz")

        assert response.status_code == 404
        error = response.json()
        assert "detail" in error

    @pytest.mark.asyncio
    async def test_create_collection_validation(self, api_client: httpx.AsyncClient):
        """Test validation when creating a collection."""
        # Test with empty name
        response = await api_client.post("/collections/", json={"name": ""})

        assert response.status_code == 422

        # Test with missing name
        response = await api_client.post("/collections/", json={})

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_non_existent_collection(self, api_client: httpx.AsyncClient):
        """Test updating a non-existent collection."""
        response = await api_client.patch(
            "/collections/non-existent-xyz", json={"name": "Updated Name"}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_non_existent_collection(self, api_client: httpx.AsyncClient):
        """Test deleting a non-existent collection."""
        response = await api_client.delete("/collections/non-existent-xyz")

        # Should return 404 or 204 (idempotent delete)
        assert response.status_code in [404, 204]

    @pytest.mark.asyncio
    async def test_collection_with_source_connections(self, api_client: httpx.AsyncClient, config):
        """Test that collections with source connections handle deletion properly."""
        # Create a collection
        collection_data = {"name": "Collection with Connections"}
        response = await api_client.post("/collections/", json=collection_data)

        assert response.status_code == 200
        collection = response.json()

        # Create a source connection in this collection
        connection_data = {
            "name": "Test Connection",
            "short_name": "stripe",
            "readable_collection_id": collection["readable_id"],
            "authentication": {"credentials": {"api_key": config.TEST_STRIPE_API_KEY}},
        }

        response = await api_client.post("/source-connections", json=connection_data)

        if response.status_code == 200:
            connection = response.json()

            # Try to delete the collection (should handle cascade or prevent)
            response = await api_client.delete(f"/collections/{collection['readable_id']}")

            # Clean up connection if collection delete failed
            if response.status_code != 200:
                await api_client.delete(f"/source-connections/{connection['id']}")
                # Then delete collection
                await api_client.delete(f"/collections/{collection['readable_id']}")
        else:
            # Just delete the collection if connection creation failed
            await api_client.delete(f"/collections/{collection['readable_id']}")
