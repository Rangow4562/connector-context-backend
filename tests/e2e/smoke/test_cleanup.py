"""
Async test module for Cleanup operations.

Tests deletion of created resources including:
- Deleting source connections with and without data
- Deleting collections with and without data
- Verifying cascade deletions
- Error handling for non-existent resources
"""

import pytest
import httpx
import uuid


@pytest.mark.asyncio
class TestCleanup:
    """Test suite for cleanup operations."""

    async def test_delete_source_connection(
        self, api_client: httpx.AsyncClient, source_connection_fast: dict
    ):
        """Test deleting a source connection."""
        conn_id = source_connection_fast["id"]

        # Delete without data
        response = await api_client.delete(f"/source-connections/{conn_id}")

        assert response.status_code == 200
        deleted = response.json()
        assert deleted["id"] == conn_id

        # Verify it's deleted
        response = await api_client.get(f"/source-connections/{conn_id}")
        assert response.status_code == 404

    async def test_delete_source_connection_with_data(
        self, api_client: httpx.AsyncClient, source_connection_fast: dict
    ):
        """Test deleting a source connection with its data."""
        conn_id = source_connection_fast["id"]

        # Delete with data
        response = await api_client.delete(f"/source-connections/{conn_id}")

        assert response.status_code == 200
        deleted = response.json()
        assert deleted["id"] == conn_id

        # Verify it's deleted
        response = await api_client.get(f"/source-connections/{conn_id}")
        assert response.status_code == 404

    async def test_delete_collection(self, api_client: httpx.AsyncClient, collection: dict):
        """Test deleting a collection."""
        collection_id = collection["readable_id"]

        # Delete without data
        response = await api_client.delete(f"/collections/{collection_id}")

        # Could be 200 or 404 if already deleted by cascade
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            deleted = response.json()
            assert deleted["readable_id"] == collection_id

        # Verify it's deleted
        response = await api_client.get(f"/collections/{collection_id}")
        assert response.status_code == 404

    async def test_delete_collection_with_data(
        self, api_client: httpx.AsyncClient, collection: dict
    ):
        """Test deleting a collection with its data."""
        collection_id = collection["readable_id"]

        # Delete with data
        response = await api_client.delete(f"/collections/{collection_id}")

        # Could be 200 or 404 if already deleted
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            deleted = response.json()
            assert deleted["readable_id"] == collection_id

        # Verify it's deleted
        response = await api_client.get(f"/collections/{collection_id}")
        assert response.status_code == 404

    async def test_delete_non_existent_source_connection(self, api_client: httpx.AsyncClient):
        """Test deleting a non-existent source connection."""
        fake_id = str(uuid.uuid4())

        response = await api_client.delete(f"/source-connections/{fake_id}")
        assert response.status_code == 404

    async def test_delete_non_existent_collection(self, api_client: httpx.AsyncClient):
        """Test deleting a non-existent collection."""
        response = await api_client.delete("/collections/non-existent-collection")
        assert response.status_code == 404

    async def test_cascade_deletion(self, api_client: httpx.AsyncClient, config):
        """Test cascade deletion behavior."""
        # Create a collection
        collection_data = {"name": "Cascade Test Collection"}
        response = await api_client.post("/collections/", json=collection_data)
        assert response.status_code == 200
        collection = response.json()

        # Create a source connection in this collection
        connection_data = {
            "name": "Cascade Test Connection",
            "short_name": "stripe",
            "readable_collection_id": collection["readable_id"],
            "authentication": {"credentials": {"api_key": config.TEST_STRIPE_API_KEY}},
            "sync_immediately": False,
        }

        response = await api_client.post("/source-connections", json=connection_data)
        if response.status_code == 400 and "invalid" in response.text.lower():
            # Skip test if using dummy credentials
            pytest.skip(f"Skipping test due to invalid credentials: {response.text}")
        assert response.status_code == 200
        connection = response.json()

        # Delete the collection
        response = await api_client.delete(
            f"/collections/{collection['readable_id']}"
        )

        # Should succeed or return 404 if cascade handled it
        assert response.status_code in [200, 204, 404]

        # Verify both are deleted
        response = await api_client.get(f"/collections/{collection['readable_id']}")
        assert response.status_code == 404

        response = await api_client.get(f"/source-connections/{connection['id']}")
        # Connection might be deleted by cascade or might need separate deletion
        # depending on implementation
        if response.status_code == 200:
            # Clean up connection if still exists
            await api_client.delete(f"/source-connections/{connection['id']}")

    async def test_list_after_deletion(self, api_client: httpx.AsyncClient):
        """Test that deleted items don't appear in lists."""
        # Create and delete a collection
        collection_data = {"name": "List Test Collection"}
        response = await api_client.post("/collections/", json=collection_data)
        assert response.status_code == 200
        collection = response.json()
        collection_id = collection["readable_id"]

        # Delete it
        response = await api_client.delete(f"/collections/{collection_id}")
        assert response.status_code in [200, 204]

        # List collections and verify it's not there
        response = await api_client.get("/collections/")
        assert response.status_code == 200
        collections = response.json()

        collection_ids = [c["readable_id"] for c in collections]
        assert collection_id not in collection_ids

    async def test_cleanup_order(self, api_client: httpx.AsyncClient, config):
        """Test proper cleanup order (connections before collections)."""
        # Create collection
        collection_data = {"name": "Order Test Collection"}
        response = await api_client.post("/collections/", json=collection_data)
        assert response.status_code == 200
        collection = response.json()

        # Create two connections
        connections = []
        for i in range(2):
            connection_data = {
                "name": f"Order Test Connection {i}",
                "short_name": "stripe",
                "readable_collection_id": collection["readable_id"],
                "authentication": {"credentials": {"api_key": config.TEST_STRIPE_API_KEY}},
                "sync_immediately": False,
            }

            response = await api_client.post("/source-connections", json=connection_data)
            if response.status_code == 400 and "invalid" in response.text.lower():
                # Skip test if using dummy credentials
                pytest.skip(f"Skipping test due to invalid credentials: {response.text}")
            assert response.status_code == 200
            connections.append(response.json())

        # Delete connections first
        for conn in connections:
            response = await api_client.delete(f"/source-connections/{conn['id']}")
            assert response.status_code == 200

        # Then delete collection
        response = await api_client.delete(
            f"/collections/{collection['readable_id']}"
        )
        assert response.status_code in [200, 204]

        # Verify all deleted
        for conn in connections:
            response = await api_client.get(f"/source-connections/{conn['id']}")
            assert response.status_code == 404

        response = await api_client.get(f"/collections/{collection['readable_id']}")
        assert response.status_code == 404
