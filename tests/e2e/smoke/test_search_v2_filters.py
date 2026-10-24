"""
E2E smoke tests for new search tier filter endpoints (v2).

Uses stub + optional Stripe data to validate that the new tier endpoints
(/search/instant, /search/classic, /search/agentic) correctly handle filters
in the new FilterGroup format.

Tests cover:
1. Pydantic validation (invalid field/operator/timestamp -> 422)
2. Source name filtering across all three tiers
3. Entity type filtering (equals, in, not_equals)
4. Combined filter logic (AND within group, OR across groups)
5. Filter effectiveness (filtered < unfiltered)
6. Timestamp filtering

The fixture creates a collection with:
- Stub source: seed=42, 20 entities (deterministic, always available)
- Stripe source: added if TEST_STRIPE_API_KEY is available
"""

import asyncio
import atexit
import json
import time
from collections import Counter
from typing import AsyncGenerator, Dict, List, Optional

import httpx
import pytest
import pytest_asyncio


# =============================================================================
# Cleanup
# =============================================================================


def _cleanup_cached_collection():
    """Cleanup cached collection on process exit.

    Runs when the pytest worker process exits, ensuring we don't leave
    orphaned collections in the test environment.
    """
    global _cached_v2_filter_collection, _cached_v2_filter_readable_id

    if _cached_v2_filter_collection is None:
        return

    try:
        from config import settings

        import httpx as httpx_sync

        with httpx_sync.Client(
            base_url=settings.api_url,
            headers=settings.api_headers,
            timeout=30,
        ) as client:
            for conn_id in _cached_v2_filter_collection.get("_connections_to_cleanup", []):
                try:
                    client.delete(f"/source-connections/{conn_id}")
                except Exception:
                    pass

            if _cached_v2_filter_readable_id:
                try:
                    client.delete(f"/collections/{_cached_v2_filter_readable_id}")
                except Exception:
                    pass
    except Exception:
        pass


atexit.register(_cleanup_cached_collection)


# =============================================================================
# Helpers
# =============================================================================


def print_results_summary(results: dict, test_name: str, filter_list: list = None):
    """Print a summary of search results for debugging."""
    print(f"\n{'='*80}")
    print(f"TEST: {test_name}")
    print(f"{'='*80}")

    if filter_list:
        print(f"\nFILTER APPLIED:")
        print(json.dumps(filter_list, indent=2))
    else:
        print("\nNO FILTER APPLIED")

    result_list = results.get("results", [])
    print(f"\nTOTAL RESULTS RETURNED: {len(result_list)}")

    if not result_list:
        print("  (no results)")
        return

    source_names = Counter()
    entity_types = Counter()

    for r in result_list:
        sys_meta = r.get("connector_context_system_metadata", {})
        source_names[sys_meta.get("source_name", "UNKNOWN")] += 1
        entity_types[sys_meta.get("entity_type", "UNKNOWN")] += 1

    print(f"\nBY SOURCE NAME:")
    for sn, count in sorted(source_names.items()):
        print(f"  {sn}: {count}")

    print(f"\nBY ENTITY TYPE:")
    for et, count in sorted(entity_types.items()):
        print(f"  {et}: {count}")

    print(f"\nFIRST 5 RESULTS:")
    for i, r in enumerate(result_list[:5]):
        sys_meta = r.get("connector_context_system_metadata", {})
        print(f"  {i+1}. {r.get('entity_id')}")
        print(f"      type: {sys_meta.get('entity_type')}")
        print(f"      source: {sys_meta.get('source_name')}")
        print(f"      name: {r.get('name', 'N/A')[:50]}")

    if len(result_list) > 5:
        print(f"  ... and {len(result_list) - 5} more results")

    print(f"{'='*80}\n")


# =============================================================================
# Collection setup
# =============================================================================

_cached_v2_filter_collection: Optional[Dict] = None
_cached_v2_filter_readable_id: Optional[str] = None


async def wait_for_sync(
    client: httpx.AsyncClient,
    connection_id: str,
    max_wait_time: int = 180,
    poll_interval: int = 3,
) -> bool:
    """Wait for a source connection sync job to successfully complete.

    Polls the sync job status until it reaches a terminal state.
    Returns True only if the sync job completed successfully.
    Returns False if the job failed, was cancelled, or timed out.
    """
    elapsed = 0
    while elapsed < max_wait_time:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        status_response = await client.get(f"/source-connections/{connection_id}")
        if status_response.status_code != 200:
            continue

        conn_details = status_response.json()

        # Check sync job status (the actual job, not just the connection)
        sync_info = conn_details.get("sync")
        if sync_info and sync_info.get("last_job"):
            job_status = sync_info["last_job"].get("status")
            if job_status == "completed":
                return True
            if job_status in ["failed", "cancelled"]:
                return False

        # If no job info yet but connection errored, bail out
        if conn_details.get("status") == "error":
            return False

    return False


async def _create_v2_filter_collection(client: httpx.AsyncClient) -> Dict:
    """Create a collection with stub + optional Stripe data for v2 filter testing.

    - Stub source: seed=42, 20 entities (deterministic)
    - Stripe source: added if TEST_STRIPE_API_KEY is available
    """
    from config import settings

    connections_to_cleanup: List[str] = []

    # Create collection
    collection_data = {"name": f"SearchV2 Filter Test {int(time.time())}"}
    response = await client.post("/collections/", json=collection_data)

    if response.status_code != 200:
        pytest.fail(f"Failed to create collection: {response.text}")

    collection = response.json()
    readable_id = collection["readable_id"]

    # ---------- Source 1: Stub (always created) ----------
    stub_connection_data = {
        "name": f"Stub V2 Filter Test {int(time.time())}",
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
    }

    response = await client.post("/source-connections", json=stub_connection_data)
    if response.status_code != 200:
        pytest.fail(f"Failed to create stub connection: {response.text}")

    stub_connection = response.json()
    connections_to_cleanup.append(stub_connection["id"])

    # Wait for stub sync
    if not await wait_for_sync(client, stub_connection["id"]):
        pytest.fail("Stub sync did not complete within timeout")

    # Verify stub data is searchable (use regular /search -- cheaper, no LLM dependency)
    stub_verified = False
    for attempt in range(18):  # up to ~100s (3s x5, 5s x5, 8s x8)
        wait_secs = 3 if attempt < 5 else 5 if attempt < 10 else 8
        await asyncio.sleep(wait_secs)
        verify_resp = await client.post(
            f"/collections/{readable_id}/search",
            json={
                "query": "stub",
                "expand_query": False,
                "interpret_filters": False,
                "rerank": False,
                "generate_answer": False,
                "limit": 5,
            },
            timeout=60,
        )
        if verify_resp.status_code == 200:
            verify_data = verify_resp.json()
            if verify_data.get("results") and len(verify_data["results"]) > 0:
                stub_verified = True
                print(
                    f"  Stub sync verified: {len(verify_data['results'])} results "
                    f"(attempt {attempt + 1})"
                )
                break
        print(f"  [stub verify] attempt {attempt + 1}: no results yet, retrying...")

    if not stub_verified:
        pytest.fail("Stub sync completed but data not searchable after retries")

    # ---------- Source 2: Stripe (optional) ----------
    stripe_connection: Optional[Dict] = None
    has_stripe = False

    stripe_api_key = getattr(settings, "TEST_STRIPE_API_KEY", None)
    if stripe_api_key and stripe_api_key != "sk_test_dummy":
        stripe_connection_data = {
            "name": f"Stripe V2 Filter Test {int(time.time())}",
            "short_name": "stripe",
            "readable_collection_id": readable_id,
            "authentication": {"credentials": {"api_key": stripe_api_key}},
            "sync_immediately": True,
        }

        response = await client.post("/source-connections", json=stripe_connection_data)

        if response.status_code == 200:
            stripe_connection = response.json()
            connections_to_cleanup.append(stripe_connection["id"])

            if await wait_for_sync(client, stripe_connection["id"], max_wait_time=300):
                for attempt in range(8):
                    await asyncio.sleep(5)
                    verify_response = await client.post(
                        f"/collections/{readable_id}/search",
                        json={
                            "query": "customer OR invoice OR payment",
                            "expand_query": False,
                            "interpret_filters": False,
                            "rerank": False,
                            "generate_answer": False,
                            "limit": 5,
                        },
                        timeout=60,
                    )
                    if verify_response.status_code == 200:
                        verify_data = verify_response.json()
                        if verify_data.get("results") and len(verify_data["results"]) > 0:
                            has_stripe = True
                            print(
                                f"  Stripe sync verified: {len(verify_data['results'])} results "
                                f"(attempt {attempt + 1})"
                            )
                            break
                    print(
                        f"  [stripe verify] attempt {attempt + 1}: no results yet, retrying..."
                    )

                if not has_stripe:
                    print("  WARNING: Stripe sync completed but no data indexed")
            else:
                print("  WARNING: Stripe sync timed out")

    result = {
        "collection": collection,
        "stub_connection": stub_connection,
        "stripe_connection": stripe_connection,
        "has_stripe": has_stripe,
        "readable_id": readable_id,
        "sources": ["stub"] + (["stripe"] if has_stripe else []),
        "_connections_to_cleanup": connections_to_cleanup,
    }

    print(f"\n  V2 filter collection ready. Sources: {result['sources']}\n")

    return result


# =============================================================================
# Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def stub_filter_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create HTTP client for v2 filter tests.

    Uses a high default timeout (300s) to accommodate agentic tier tests.
    """
    from config import settings

    async with httpx.AsyncClient(
        base_url=settings.api_url,
        headers=settings.api_headers,
        timeout=httpx.Timeout(300),
        follow_redirects=True,
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def stub_v2_filter_collection(
    stub_filter_client: httpx.AsyncClient,
) -> AsyncGenerator[Dict, None]:
    """Provide collection with stub + optional Stripe data for v2 filter testing.

    Uses module-level cache to avoid recreating collections for each test.
    """
    global _cached_v2_filter_collection, _cached_v2_filter_readable_id

    client = stub_filter_client

    if _cached_v2_filter_collection is not None and _cached_v2_filter_readable_id is not None:
        check_response = await client.get(f"/collections/{_cached_v2_filter_readable_id}")
        if check_response.status_code == 200:
            yield _cached_v2_filter_collection
            return

    _cached_v2_filter_collection = await _create_v2_filter_collection(client)
    _cached_v2_filter_readable_id = _cached_v2_filter_collection["readable_id"]

    yield _cached_v2_filter_collection


# =============================================================================
# Search helper
# =============================================================================


def _is_transient_llm_error(status_code: int, response_text: str) -> bool:
    """Check if a non-200 response is caused by a transient LLM provider issue.

    These are not bugs in our code -- the LLM provider is temporarily overloaded.
    """
    text_lower = response_text.lower()
    transient_indicators = ["503", "rate", "too_many_requests", "queue_exceeded", "high traffic"]

    # Server-side timeout (504) -- LLM retries exceeded server's request timeout
    if status_code == 504:
        return True

    # 500 caused by LLM provider exhaustion (not a code bug)
    if status_code == 500 and any(ind in text_lower for ind in transient_indicators):
        return True

    return False


async def do_search_v2(
    client: httpx.AsyncClient,
    readable_id: str,
    query: str,
    tier: str = "instant",
    filter_list: list = None,
    timeout: int = 10,
) -> dict:
    """Execute a v2 tier search with optional filter.

    Transient LLM provider errors (503 rate limits, server timeouts) cause
    the test to skip rather than fail for the agentic tier.
    """
    payload: dict = {"query": query}
    if filter_list is not None:
        payload["filter"] = filter_list

    response = await client.post(
        f"/collections/{readable_id}/search/{tier}",
        json=payload,
        timeout=timeout,
    )

    if response.status_code != 200:
        if tier == "agentic" and _is_transient_llm_error(response.status_code, response.text):
            pytest.skip(
                f"Transient LLM provider error ({response.status_code}): "
                f"{response.text[:200]}"
            )
        pytest.fail(f"Search failed ({response.status_code}): {response.text}")

    return response.json()


# =============================================================================
# FILTER VALIDATION TESTS (Pydantic rejects bad input with 422)
# =============================================================================


@pytest.mark.asyncio
async def test_invalid_field_rejected_instant(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test that an invalid field name is rejected with 422 on the instant tier."""
    payload = {
        "query": "test",
        "filter": [
            {
                "conditions": [
                    {
                        "field": "nonexistent_field",
                        "operator": "equals",
                        "value": "test",
                    }
                ]
            }
        ],
    }

    response = await stub_filter_client.post(
        f"/collections/{stub_v2_filter_collection['readable_id']}/search/instant",
        json=payload,
        timeout=10,
    )

    assert response.status_code == 422, (
        f"Expected 422 for invalid field, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio
async def test_invalid_operator_rejected_classic(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test that an invalid operator is rejected with 422 on the classic tier."""
    payload = {
        "query": "test",
        "filter": [
            {
                "conditions": [
                    {
                        "field": "connector_context_system_metadata.source_name",
                        "operator": "invalid_op",
                        "value": "test",
                    }
                ]
            }
        ],
    }

    response = await stub_filter_client.post(
        f"/collections/{stub_v2_filter_collection['readable_id']}/search/classic",
        json=payload,
        timeout=30,
    )

    assert response.status_code == 422, (
        f"Expected 422 for invalid operator, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio
async def test_invalid_timestamp_rejected(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test that created_at with an invalid date string is rejected with 422."""
    payload = {
        "query": "test",
        "filter": [
            {
                "conditions": [
                    {
                        "field": "created_at",
                        "operator": "greater_than",
                        "value": "not-a-date",
                    }
                ]
            }
        ],
    }

    response = await stub_filter_client.post(
        f"/collections/{stub_v2_filter_collection['readable_id']}/search/instant",
        json=payload,
        timeout=10,
    )

    assert response.status_code == 422, (
        f"Expected 422 for invalid timestamp, got {response.status_code}: {response.text}"
    )


# =============================================================================
# SOURCE NAME FILTER TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_instant_filter_by_source_name(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test filtering by source_name on the instant tier -- all results should be stub."""
    filter_list = [
        {
            "conditions": [
                {
                    "field": "connector_context_system_metadata.source_name",
                    "operator": "equals",
                    "value": "stub",
                }
            ]
        }
    ]

    results = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "test",
        tier="instant",
        filter_list=filter_list,
        timeout=10,
    )

    print_results_summary(results, "test_instant_filter_by_source_name", filter_list)

    assert "results" in results
    assert len(results["results"]) > 0, "Expected results for stub source"

    for result in results["results"]:
        source_name = result.get("connector_context_system_metadata", {}).get("source_name")
        assert source_name == "stub", f"Expected stub, got {source_name}"


@pytest.mark.asyncio
async def test_classic_filter_by_source_name(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test filtering by source_name on the classic tier -- all results should be stub."""
    filter_list = [
        {
            "conditions": [
                {
                    "field": "connector_context_system_metadata.source_name",
                    "operator": "equals",
                    "value": "stub",
                }
            ]
        }
    ]

    results = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "test",
        tier="classic",
        filter_list=filter_list,
        timeout=30,
    )

    print_results_summary(results, "test_classic_filter_by_source_name", filter_list)

    assert "results" in results
    assert len(results["results"]) > 0, "Expected results for stub source"

    for result in results["results"]:
        source_name = result.get("connector_context_system_metadata", {}).get("source_name")
        assert source_name == "stub", f"Expected stub, got {source_name}"


@pytest.mark.asyncio
async def test_agentic_filter_by_source_name(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test filtering by source_name on the agentic tier -- all results should be stub."""
    filter_list = [
        {
            "conditions": [
                {
                    "field": "connector_context_system_metadata.source_name",
                    "operator": "equals",
                    "value": "stub",
                }
            ]
        }
    ]

    results = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "test",
        tier="agentic",
        filter_list=filter_list,
        timeout=300,
    )

    print_results_summary(results, "test_agentic_filter_by_source_name", filter_list)

    assert "results" in results
    assert len(results["results"]) > 0, "Expected results for stub source"

    for result in results["results"]:
        source_name = result.get("connector_context_system_metadata", {}).get("source_name")
        assert source_name == "stub", f"Expected stub, got {source_name}"


@pytest.mark.asyncio
async def test_filter_nonexistent_source_empty(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test that filtering for a non-existent source returns no results."""
    filter_list = [
        {
            "conditions": [
                {
                    "field": "connector_context_system_metadata.source_name",
                    "operator": "equals",
                    "value": "nonexistent_source_xyz",
                }
            ]
        }
    ]

    results = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "test",
        tier="instant",
        filter_list=filter_list,
        timeout=10,
    )

    print_results_summary(results, "test_filter_nonexistent_source_empty", filter_list)

    assert "results" in results
    assert len(results["results"]) == 0, (
        f"Expected 0 results for non-existent source, got {len(results['results'])}"
    )


# =============================================================================
# ENTITY TYPE FILTER TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_filter_by_entity_type_equals(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test filtering by exact entity_type -- MediumStubEntity only."""
    filter_list = [
        {
            "conditions": [
                {
                    "field": "connector_context_system_metadata.entity_type",
                    "operator": "equals",
                    "value": "MediumStubEntity",
                }
            ]
        }
    ]

    results = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "stub",
        tier="instant",
        filter_list=filter_list,
        timeout=10,
    )

    print_results_summary(results, "test_filter_by_entity_type_equals", filter_list)

    assert "results" in results

    for result in results["results"]:
        entity_type = result.get("connector_context_system_metadata", {}).get("entity_type")
        assert entity_type == "MediumStubEntity", (
            f"Expected MediumStubEntity, got {entity_type}"
        )


@pytest.mark.asyncio
async def test_filter_with_in_operator(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test the 'in' operator with a list of entity types."""
    filter_list = [
        {
            "conditions": [
                {
                    "field": "connector_context_system_metadata.entity_type",
                    "operator": "in",
                    "value": ["SmallStubEntity", "LargeStubEntity"],
                }
            ]
        }
    ]

    results = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "stub",
        tier="instant",
        filter_list=filter_list,
        timeout=10,
    )

    print_results_summary(results, "test_filter_with_in_operator", filter_list)

    assert "results" in results

    valid_types = {"SmallStubEntity", "LargeStubEntity"}
    for result in results["results"]:
        entity_type = result.get("connector_context_system_metadata", {}).get("entity_type")
        assert entity_type in valid_types, (
            f"Expected one of {valid_types}, got {entity_type}"
        )


@pytest.mark.asyncio
async def test_filter_with_not_equals(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test the 'not_equals' operator excludes StubContainerEntity."""
    filter_list = [
        {
            "conditions": [
                {
                    "field": "connector_context_system_metadata.entity_type",
                    "operator": "not_equals",
                    "value": "StubContainerEntity",
                }
            ]
        }
    ]

    results = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "stub",
        tier="instant",
        filter_list=filter_list,
        timeout=10,
    )

    print_results_summary(results, "test_filter_with_not_equals", filter_list)

    assert "results" in results

    for result in results["results"]:
        entity_type = result.get("connector_context_system_metadata", {}).get("entity_type")
        assert entity_type != "StubContainerEntity", (
            f"StubContainerEntity should be excluded, but found it"
        )


# =============================================================================
# COMBINED LOGIC TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_filter_multiple_conditions_and(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test multiple conditions within one group (AND logic).

    source=stub AND type=MediumStubEntity -- all results must match both.
    """
    filter_list = [
        {
            "conditions": [
                {
                    "field": "connector_context_system_metadata.source_name",
                    "operator": "equals",
                    "value": "stub",
                },
                {
                    "field": "connector_context_system_metadata.entity_type",
                    "operator": "equals",
                    "value": "MediumStubEntity",
                },
            ]
        }
    ]

    results = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "stub",
        tier="instant",
        filter_list=filter_list,
        timeout=10,
    )

    print_results_summary(results, "test_filter_multiple_conditions_and", filter_list)

    assert "results" in results

    for result in results["results"]:
        sys_meta = result.get("connector_context_system_metadata", {})
        assert sys_meta.get("source_name") == "stub", (
            f"Expected source_name=stub, got {sys_meta.get('source_name')}"
        )
        assert sys_meta.get("entity_type") == "MediumStubEntity", (
            f"Expected entity_type=MediumStubEntity, got {sys_meta.get('entity_type')}"
        )


@pytest.mark.asyncio
async def test_filter_multiple_groups_or(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test multiple filter groups (OR logic between groups).

    Group 1: type=SmallStubEntity OR Group 2: type=LargeStubEntity
    Results should contain either type.
    """
    filter_list = [
        {
            "conditions": [
                {
                    "field": "connector_context_system_metadata.entity_type",
                    "operator": "equals",
                    "value": "SmallStubEntity",
                }
            ]
        },
        {
            "conditions": [
                {
                    "field": "connector_context_system_metadata.entity_type",
                    "operator": "equals",
                    "value": "LargeStubEntity",
                }
            ]
        },
    ]

    results = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "stub",
        tier="instant",
        filter_list=filter_list,
        timeout=10,
    )

    print_results_summary(results, "test_filter_multiple_groups_or", filter_list)

    assert "results" in results

    valid_types = {"SmallStubEntity", "LargeStubEntity"}
    for result in results["results"]:
        entity_type = result.get("connector_context_system_metadata", {}).get("entity_type")
        assert entity_type in valid_types, (
            f"Expected one of {valid_types}, got {entity_type}"
        )


# =============================================================================
# FILTER EFFECTIVENESS TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_filter_reduces_result_count(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test that applying a filter reduces the result count compared to unfiltered.

    A restrictive entity type filter should return fewer results than no filter.
    """
    unfiltered = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "stub",
        tier="instant",
        timeout=10,
    )

    print_results_summary(unfiltered, "test_filter_reduces_result_count (UNFILTERED)")

    filter_list = [
        {
            "conditions": [
                {
                    "field": "connector_context_system_metadata.entity_type",
                    "operator": "equals",
                    "value": "StubContainerEntity",
                }
            ]
        }
    ]
    filtered = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "stub",
        tier="instant",
        filter_list=filter_list,
        timeout=10,
    )

    print_results_summary(filtered, "test_filter_reduces_result_count (FILTERED)", filter_list)

    unfiltered_count = len(unfiltered.get("results", []))
    filtered_count = len(filtered.get("results", []))

    print(f"\n>>> COMPARISON: unfiltered={unfiltered_count}, filtered={filtered_count}")

    assert filtered_count < unfiltered_count, (
        f"Filter should reduce results: unfiltered={unfiltered_count}, filtered={filtered_count}"
    )
    assert filtered_count >= 1, "Should have at least 1 container entity"


# =============================================================================
# TIMESTAMP FILTER TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_filter_timestamp_far_past_includes_all(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test that created_at > 2000-01-01 returns results (all data is newer)."""
    filter_list = [
        {
            "conditions": [
                {
                    "field": "created_at",
                    "operator": "greater_than",
                    "value": "2000-01-01T00:00:00Z",
                }
            ]
        }
    ]

    results = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "stub",
        tier="instant",
        filter_list=filter_list,
        timeout=10,
    )

    print_results_summary(
        results, "test_filter_timestamp_far_past_includes_all", filter_list
    )

    assert "results" in results
    assert len(results["results"]) > 0, (
        "Expected results for created_at > 2000-01-01 (all data is newer)"
    )


@pytest.mark.asyncio
async def test_filter_timestamp_far_future_excludes_all(
    stub_filter_client: httpx.AsyncClient,
    stub_v2_filter_collection: Dict,
):
    """Test that created_at > 2099-01-01 returns 0 results (no data from the future)."""
    filter_list = [
        {
            "conditions": [
                {
                    "field": "created_at",
                    "operator": "greater_than",
                    "value": "2099-01-01T00:00:00Z",
                }
            ]
        }
    ]

    results = await do_search_v2(
        stub_filter_client,
        stub_v2_filter_collection["readable_id"],
        "stub",
        tier="instant",
        filter_list=filter_list,
        timeout=10,
    )

    print_results_summary(
        results, "test_filter_timestamp_far_future_excludes_all", filter_list
    )

    assert "results" in results
    assert len(results["results"]) == 0, (
        f"Expected 0 results for created_at > 2099-01-01, got {len(results['results'])}"
    )
