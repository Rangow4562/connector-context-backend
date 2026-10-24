"""E2E smoke tests for Search V2 endpoints (instant, classic, agentic).

Tests the new three-tier search API with deterministic stub data (seed=42)
so we can make meaningful assertions about what's found, not just that
the endpoint returns 200.

Timeouts:
- Instant: 10s (embed + Vespa, no LLM)
- Classic: 30s (one LLM call for search strategy)
- Agentic: 300s / 600s (multi-iteration agent loop)
"""

import asyncio
import atexit
import time
from typing import AsyncGenerator, Dict, List, Optional

import httpx
import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Module-level collection cache (stub source, deterministic seed=42)
# ---------------------------------------------------------------------------

_cached_collection: Optional[Dict] = None
_cached_readable_id: Optional[str] = None


def _cleanup():
    """Best-effort cleanup on process exit."""
    global _cached_collection, _cached_readable_id
    if _cached_collection is None:
        return
    try:
        from config import settings
        import httpx as httpx_sync

        with httpx_sync.Client(
            base_url=settings.api_url,
            headers=settings.api_headers,
            timeout=30,
        ) as client:
            for conn_id in _cached_collection.get("_connections_to_cleanup", []):
                try:
                    client.delete(f"/source-connections/{conn_id}")
                except Exception:
                    pass
            if _cached_readable_id:
                try:
                    client.delete(f"/collections/{_cached_readable_id}")
                except Exception:
                    pass
    except Exception:
        pass


atexit.register(_cleanup)


async def _wait_for_sync(
    client: httpx.AsyncClient, connection_id: str, max_wait: int = 180
) -> bool:
    elapsed = 0
    while elapsed < max_wait:
        await asyncio.sleep(3)
        elapsed += 3
        resp = await client.get(f"/source-connections/{connection_id}")
        if resp.status_code != 200:
            continue
        details = resp.json()
        sync_info = details.get("sync")
        if sync_info and sync_info.get("last_job"):
            status = sync_info["last_job"].get("status")
            if status == "completed":
                return True
            if status in ("failed", "cancelled"):
                return False
        if details.get("status") == "error":
            return False
    return False


async def _create_stub_collection(client: httpx.AsyncClient) -> Dict:
    """Create a collection with deterministic stub data (seed=42, 20 entities)."""
    connections: List[str] = []

    resp = await client.post("/collections/", json={"name": f"SearchV2 Test {int(time.time())}"})
    if resp.status_code != 200:
        pytest.fail(f"Failed to create collection: {resp.text}")
    collection = resp.json()
    readable_id = collection["readable_id"]

    # Create stub source
    resp = await client.post("/source-connections", json={
        "name": f"Stub SearchV2 {int(time.time())}",
        "short_name": "stub",
        "readable_collection_id": readable_id,
        "authentication": {"credentials": {"stub_key": "test"}},
        "config": {
            "seed": 42,
            "entity_count": 20,
            "generation_delay_ms": 0,
            "small_entity_weight": 25,
            "medium_entity_weight": 25,
            "large_entity_weight": 20,
            "small_file_weight": 10,
            "large_file_weight": 10,
            "code_file_weight": 10,
        },
        "sync_immediately": True,
    })
    if resp.status_code != 200:
        pytest.fail(f"Failed to create stub connection: {resp.text}")
    stub_conn = resp.json()
    connections.append(stub_conn["id"])

    if not await _wait_for_sync(client, stub_conn["id"]):
        pytest.fail("Stub sync did not complete")

    # Verify data is searchable
    for attempt in range(15):
        await asyncio.sleep(3 if attempt < 5 else 5)
        verify = await client.post(
            f"/collections/{readable_id}/search/instant",
            json={"query": "stub"},
            timeout=10,
        )
        if verify.status_code == 200:
            data = verify.json()
            if data.get("results") and len(data["results"]) > 0:
                print(f"  Stub data verified: {len(data['results'])} results (attempt {attempt + 1})")
                break
    else:
        pytest.fail("Stub data not searchable after retries")

    return {
        "collection": collection,
        "readable_id": readable_id,
        "stub_connection": stub_conn,
        "_connections_to_cleanup": connections,
    }


@pytest_asyncio.fixture(scope="function")
async def search_v2_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    from config import settings
    async with httpx.AsyncClient(
        base_url=settings.api_url,
        headers=settings.api_headers,
        timeout=httpx.Timeout(300),
        follow_redirects=True,
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def stub_collection(search_v2_client: httpx.AsyncClient) -> AsyncGenerator[Dict, None]:
    """Provide a collection with deterministic stub data. Module-cached."""
    global _cached_collection, _cached_readable_id
    if _cached_collection is not None and _cached_readable_id is not None:
        check = await search_v2_client.get(f"/collections/{_cached_readable_id}")
        if check.status_code == 200:
            yield _cached_collection
            return
    _cached_collection = await _create_stub_collection(search_v2_client)
    _cached_readable_id = _cached_collection["readable_id"]
    yield _cached_collection


def _is_transient_error(status_code: int, text: str) -> bool:
    if status_code == 504:
        return True
    lower = text.lower()
    return status_code == 500 and any(
        ind in lower for ind in ["503", "rate", "too_many_requests", "queue_exceeded"]
    )


# ---------------------------------------------------------------------------
# Instant search
# ---------------------------------------------------------------------------


class TestInstantSearch:
    """Instant tier — embed query, fire at Vespa, return results."""

    @pytest.mark.asyncio
    async def test_instant_finds_stub_data(
        self, search_v2_client: httpx.AsyncClient, stub_collection: Dict
    ):
        """Instant search finds entities from deterministic stub data."""
        resp = await search_v2_client.post(
            f"/collections/{stub_collection['readable_id']}/search/instant",
            json={"query": "stub"},
            timeout=10,
        )
        assert resp.status_code == 200, f"Instant search failed: {resp.text}"
        results = resp.json()["results"]
        assert len(results) > 0, "Expected stub entities to be found"

        # All results should come from the stub source
        for r in results:
            assert r["connector_context_system_metadata"]["source_name"] == "stub"

    @pytest.mark.asyncio
    async def test_instant_retrieval_strategies(
        self, search_v2_client: httpx.AsyncClient, stub_collection: Dict
    ):
        """All retrieval strategies return results from stub data."""
        url = f"/collections/{stub_collection['readable_id']}/search/instant"
        for strategy in ("hybrid", "semantic", "keyword"):
            resp = await search_v2_client.post(
                url,
                json={"query": "stub", "retrieval_strategy": strategy},
                timeout=10,
            )
            assert resp.status_code == 200, f"Strategy '{strategy}' failed: {resp.text}"
            assert len(resp.json()["results"]) > 0, f"No results for strategy '{strategy}'"

    @pytest.mark.asyncio
    async def test_instant_pagination(
        self, search_v2_client: httpx.AsyncClient, stub_collection: Dict
    ):
        """Pagination: offset=1 returns the same entity as position 2 at offset=0.

        Uses keyword strategy for deterministic BM25 ordering.
        """
        url = f"/collections/{stub_collection['readable_id']}/search/instant"

        resp_two = await search_v2_client.post(
            url,
            json={"query": "stub", "retrieval_strategy": "keyword", "limit": 2, "offset": 0},
            timeout=10,
        )
        assert resp_two.status_code == 200
        first_two = resp_two.json()["results"]
        assert len(first_two) >= 2, "Need at least 2 results for pagination test"

        resp_one = await search_v2_client.post(
            url,
            json={"query": "stub", "retrieval_strategy": "keyword", "limit": 1, "offset": 1},
            timeout=10,
        )
        assert resp_one.status_code == 200
        offset_result = resp_one.json()["results"]
        assert len(offset_result) == 1
        assert offset_result[0]["entity_id"] == first_two[1]["entity_id"]

    @pytest.mark.asyncio
    async def test_instant_empty_query_rejected(
        self, api_client: httpx.AsyncClient, collection: Dict
    ):
        """Empty query → 422."""
        resp = await api_client.post(
            f"/collections/{collection['readable_id']}/search/instant",
            json={"query": ""},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_instant_response_structure(
        self, search_v2_client: httpx.AsyncClient, stub_collection: Dict
    ):
        """Validate full SearchResult structure from stub data."""
        resp = await search_v2_client.post(
            f"/collections/{stub_collection['readable_id']}/search/instant",
            json={"query": "stub"},
            timeout=10,
        )
        assert resp.status_code == 200
        first = resp.json()["results"][0]

        assert "entity_id" in first
        assert "name" in first
        assert isinstance(first["relevance_score"], (int, float))
        assert first["connector_context_system_metadata"]["source_name"] == "stub"
        assert "entity_type" in first["connector_context_system_metadata"]
        assert isinstance(first["breadcrumbs"], list)
        assert "textual_representation" in first

    @pytest.mark.asyncio
    async def test_instant_entity_types_match_stub(
        self, search_v2_client: httpx.AsyncClient, stub_collection: Dict
    ):
        """Results contain entity types generated by the stub source."""
        resp = await search_v2_client.post(
            f"/collections/{stub_collection['readable_id']}/search/instant",
            json={"query": "stub", "limit": 100},
            timeout=10,
        )
        assert resp.status_code == 200
        entity_types = {
            r["connector_context_system_metadata"]["entity_type"] for r in resp.json()["results"]
        }
        # Stub source generates these entity types
        expected_types = {
            "SmallStubEntity", "MediumStubEntity", "LargeStubEntity",
            "StubContainerEntity",
        }
        assert entity_types & expected_types, (
            f"Expected some stub entity types, got {entity_types}"
        )


# ---------------------------------------------------------------------------
# Classic search
# ---------------------------------------------------------------------------


class TestClassicSearch:
    """Classic tier — LLM generates search plan, execute against Vespa."""

    @pytest.mark.asyncio
    async def test_classic_finds_stub_data(
        self, search_v2_client: httpx.AsyncClient, stub_collection: Dict
    ):
        """Classic search finds entities from stub data."""
        resp = await search_v2_client.post(
            f"/collections/{stub_collection['readable_id']}/search/classic",
            json={"query": "find all stub documents"},
            timeout=30,
        )
        assert resp.status_code == 200, f"Classic search failed: {resp.text}"
        results = resp.json()["results"]
        assert len(results) > 0

        for r in results:
            assert r["connector_context_system_metadata"]["source_name"] == "stub"

    @pytest.mark.asyncio
    async def test_classic_returns_multiple_results(
        self, search_v2_client: httpx.AsyncClient, stub_collection: Dict
    ):
        """Classic search returns multiple results with limit."""
        url = f"/collections/{stub_collection['readable_id']}/search/classic"

        resp = await search_v2_client.post(
            url, json={"query": "find all stub documents", "limit": 5}, timeout=30,
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 2, "Expected multiple results from stub data"

    @pytest.mark.asyncio
    async def test_classic_empty_query_rejected(
        self, api_client: httpx.AsyncClient, collection: Dict
    ):
        """Empty query → 422."""
        resp = await api_client.post(
            f"/collections/{collection['readable_id']}/search/classic",
            json={"query": ""},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Agentic search
# ---------------------------------------------------------------------------


class TestAgenticSearch:
    """Agentic tier — full agent loop with tool calling."""

    @pytest.mark.asyncio
    async def test_agentic_finds_stub_data(
        self, search_v2_client: httpx.AsyncClient, stub_collection: Dict
    ):
        """Agentic search finds and collects entities from stub data."""
        resp = await search_v2_client.post(
            f"/collections/{stub_collection['readable_id']}/search/agentic",
            json={"query": "find all available documents and data"},
            timeout=300,
        )
        if resp.status_code != 200 and _is_transient_error(resp.status_code, resp.text):
            pytest.skip(f"Transient LLM error ({resp.status_code})")
        assert resp.status_code == 200, f"Agentic search failed: {resp.text}"

        results = resp.json()["results"]
        assert len(results) > 0, "Agent should find stub entities"

        for r in results:
            assert r["connector_context_system_metadata"]["source_name"] == "stub"

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_agentic_with_thinking(
        self, search_v2_client: httpx.AsyncClient, stub_collection: Dict
    ):
        """Agentic search with thinking=true finds results."""
        resp = await search_v2_client.post(
            f"/collections/{stub_collection['readable_id']}/search/agentic",
            json={"query": "find documents", "thinking": True},
            timeout=600,
        )
        if resp.status_code != 200 and _is_transient_error(resp.status_code, resp.text):
            pytest.skip(f"Transient LLM error ({resp.status_code})")
        assert resp.status_code == 200, f"Thinking search failed: {resp.text}"
        assert len(resp.json()["results"]) > 0

    @pytest.mark.asyncio
    async def test_agentic_limit_truncates(
        self, search_v2_client: httpx.AsyncClient, stub_collection: Dict
    ):
        """The limit parameter caps result count."""
        url = f"/collections/{stub_collection['readable_id']}/search/agentic"

        resp = await search_v2_client.post(
            url, json={"query": "find all documents", "limit": 2}, timeout=300,
        )
        if resp.status_code != 200 and _is_transient_error(resp.status_code, resp.text):
            pytest.skip(f"Transient LLM error ({resp.status_code})")
        assert resp.status_code == 200
        assert len(resp.json()["results"]) <= 2

    @pytest.mark.asyncio
    async def test_agentic_empty_query_rejected(
        self, api_client: httpx.AsyncClient, collection: Dict
    ):
        """Empty query → 422."""
        resp = await api_client.post(
            f"/collections/{collection['readable_id']}/search/agentic",
            json={"query": ""},
        )
        assert resp.status_code == 422
