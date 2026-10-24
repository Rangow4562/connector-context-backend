"""
Async test module for PubSub functionality.

Tests sync job pubsub subscription via SSE including:
- Subscribing to sync job progress updates
- Receiving and validating progress messages
- Handling SSE stream with authentication
"""

import pytest
import httpx
import asyncio
import json
from typing import List, Dict


@pytest.mark.asyncio
class TestPubSub:
    """Test suite for PubSub/SSE functionality."""

    async def test_sync_job_pubsub(
        self, api_client: httpx.AsyncClient, source_connection_fast: dict
    ):
        """Test sync job pubsub via SSE."""
        # Trigger a sync to get a job
        response = await api_client.post(f"/source-connections/{source_connection_fast['id']}/run")

        assert response.status_code == 200
        job = response.json()
        job_id = job["id"]

        # Subscribe to SSE stream
        messages = await self._subscribe_to_sse(api_client, job_id, timeout=30)

        # Verify we received messages
        assert len(messages) > 0, "Should receive at least one SSE message"

        # Verify message structure
        for msg in messages:
            if msg.get("type") in ["connected", "heartbeat", "error"]:
                continue

            # Progress messages should have these fields
            required_fields = [
                "inserted",
                "updated",
                "deleted",
                "kept",
                "skipped",
                "entities_encountered",
            ]

            for field in required_fields:
                assert field in msg, f"Missing field '{field}' in progress message"

    async def _subscribe_to_sse(
        self, api_client: httpx.AsyncClient, job_id: str, timeout: int = 30
    ) -> List[Dict]:
        """Subscribe to SSE stream and collect messages."""
        messages = []
        sse_url = f"/sync/job/{job_id}/subscribe"

        try:
            # Use stream for SSE
            async with api_client.stream("GET", sse_url, timeout=timeout) as response:
                if response.status_code != 200:
                    return messages

                # Read SSE stream
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        try:
                            data = json.loads(data_str)
                            messages.append(data)

                            # Stop if job is complete
                            if data.get("is_complete") or data.get("is_failed"):
                                break
                        except json.JSONDecodeError:
                            continue

                    # Stop after receiving some messages
                    if len(messages) >= 3:
                        break

        except asyncio.TimeoutError:
            # Timeout is expected for long-running streams
            pass
        except httpx.TimeoutException:
            # Also expected
            pass

        return messages

    async def test_multiple_subscribers(
        self, api_client: httpx.AsyncClient, source_connection_fast: dict
    ):
        """Test multiple concurrent SSE subscribers."""
        # Trigger a sync
        response = await api_client.post(f"/source-connections/{source_connection_fast['id']}/run")

        assert response.status_code == 200
        job = response.json()
        job_id = job["id"]

        # Subscribe from multiple clients concurrently
        tasks = [self._subscribe_to_sse(api_client, job_id, timeout=10) for _ in range(3)]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # At least one subscriber should receive messages
        successful_subscriptions = [r for r in results if isinstance(r, list) and len(r) > 0]
        assert len(successful_subscriptions) > 0, "At least one subscriber should receive messages"

    async def test_progress_tracking(self, api_client: httpx.AsyncClient, collection: dict, config):
        """Test progress tracking through SSE."""
        # Create a new connection and trigger sync
        connection_data = {
            "name": "Progress Test Connection",
            "short_name": "stripe",
            "readable_collection_id": collection["readable_id"],
            "authentication": {"credentials": {"api_key": config.TEST_STRIPE_API_KEY}},
            "sync_immediately": True,
        }

        response = await api_client.post("/source-connections", json=connection_data)
        assert response.status_code == 200
        connection = response.json()

        # Get the job from the connection
        response = await api_client.get(f"/source-connections/{connection['id']}/jobs")
        if response.status_code == 200:
            jobs = response.json()
            if jobs:
                job_id = jobs[0]["id"]

                # Subscribe and track progress
                messages = await self._subscribe_to_sse(api_client, job_id, timeout=30)

                # Track progress increments
                total_processed = 0
                for msg in messages:
                    if "inserted" in msg:
                        current_total = (
                            msg.get("inserted", 0)
                            + msg.get("updated", 0)
                            + msg.get("deleted", 0)
                            + msg.get("kept", 0)
                            + msg.get("skipped", 0)
                        )
                        # Progress should increase or stay same
                        assert current_total >= total_processed
                        total_processed = current_total

        # Cleanup
        await api_client.delete(f"/collections/{collection['readable_id']}")
