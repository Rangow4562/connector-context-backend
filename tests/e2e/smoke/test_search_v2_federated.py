"""
E2E smoke tests for federated search through new tier endpoints (v2).

Tests search against federated sources (Slack via Composio) that query external
APIs at search time instead of syncing data to the vector DB.

Covers:
- Federated-only collections (Slack only, no synced data)
- Mixed collections (Stripe synced + Slack federated)
- Result structure validation
- Source filtering in mixed collections

All tests require Composio credentials for Slack.
"""

import uuid

import httpx
import pytest
import pytest_asyncio


# =============================================================================
# Helpers
# =============================================================================


def _is_transient_llm_error(status_code: int, response_text: str) -> bool:
    """Check if a non-200 response is caused by a transient LLM provider issue.

    These are not bugs in our code -- the LLM provider is temporarily overloaded.
    """
    text_lower = response_text.lower()
    transient_indicators = ["503", "rate", "too_many_requests", "queue_exceeded", "high traffic"]

    if status_code == 504:
        return True

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

    Transient LLM provider errors cause the test to skip for the agentic tier.
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
# Tests: federated-only collection (Slack only)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_composio
async def test_instant_federated_returns_results(
    api_client: httpx.AsyncClient,
    source_connection_slack_federated: dict,
):
    """Instant search on a Slack-only federated collection returns results."""
    readable_id = source_connection_slack_federated["readable_collection_id"]

    results = await do_search_v2(
        api_client,
        readable_id,
        "hello",
        tier="instant",
        timeout=10,
    )

    assert "results" in results
    assert isinstance(results["results"], list)


@pytest.mark.asyncio
@pytest.mark.requires_composio
async def test_classic_federated_returns_results(
    api_client: httpx.AsyncClient,
    source_connection_slack_federated: dict,
):
    """Classic search on a Slack-only federated collection returns results."""
    readable_id = source_connection_slack_federated["readable_collection_id"]

    results = await do_search_v2(
        api_client,
        readable_id,
        "hello",
        tier="classic",
        timeout=30,
    )

    assert "results" in results
    assert isinstance(results["results"], list)


@pytest.mark.asyncio
@pytest.mark.requires_composio
async def test_agentic_federated_returns_results(
    api_client: httpx.AsyncClient,
    source_connection_slack_federated: dict,
):
    """Agentic search on a Slack-only federated collection returns results.

    Transient LLM errors are skipped, not failed.
    """
    readable_id = source_connection_slack_federated["readable_collection_id"]

    results = await do_search_v2(
        api_client,
        readable_id,
        "hello",
        tier="agentic",
        timeout=300,
    )

    assert "results" in results
    assert isinstance(results["results"], list)


@pytest.mark.asyncio
@pytest.mark.requires_composio
async def test_federated_result_structure(
    api_client: httpx.AsyncClient,
    source_connection_slack_federated: dict,
):
    """Verify federated search results have the expected fields."""
    readable_id = source_connection_slack_federated["readable_collection_id"]

    results = await do_search_v2(
        api_client,
        readable_id,
        "test",
        tier="instant",
        timeout=10,
    )

    assert "results" in results

    if results["results"]:
        result = results["results"][0]
        assert "entity_id" in result, "Result missing entity_id"
        assert "name" in result, "Result missing name"
        assert "connector_context_system_metadata" in result, "Result missing connector_context_system_metadata"


# =============================================================================
# Tests: mixed collection (Stripe synced + Slack federated)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_composio
async def test_instant_mixed_returns_results(
    api_client: httpx.AsyncClient,
    module_source_connection_stripe: dict,
    composio_auth_provider: dict,
    config,
):
    """Instant search on a mixed Stripe+Slack collection returns results."""
    if not config.TEST_COMPOSIO_SLACK_AUTH_CONFIG_ID or not config.TEST_COMPOSIO_SLACK_ACCOUNT_ID:
        pytest.skip("Slack Composio configuration not available")

    readable_id = module_source_connection_stripe["readable_collection_id"]

    # Add Slack (federated) source to the existing Stripe collection
    resp = await api_client.post(
        "/source-connections",
        json={
            "name": f"Slack Mixed V2 {uuid.uuid4().hex[:8]}",
            "short_name": "slack",
            "readable_collection_id": readable_id,
            "authentication": {
                "provider_readable_id": composio_auth_provider["readable_id"],
                "provider_config": {
                    "auth_config_id": config.TEST_COMPOSIO_SLACK_AUTH_CONFIG_ID,
                    "account_id": config.TEST_COMPOSIO_SLACK_ACCOUNT_ID,
                },
            },
            "sync_immediately": False,
        },
    )
    assert resp.status_code == 200, f"Slack connection failed: {resp.text}"
    slack_conn = resp.json()

    try:
        results = await do_search_v2(
            api_client,
            readable_id,
            "invoice OR message",
            tier="instant",
            timeout=10,
        )

        assert "results" in results
        assert isinstance(results["results"], list)
        assert len(results["results"]) > 0, "Expected results from mixed collection"
    finally:
        try:
            await api_client.delete(f"/source-connections/{slack_conn['id']}")
        except Exception:
            pass


@pytest.mark.asyncio
@pytest.mark.requires_composio
async def test_mixed_filter_by_source_excludes_other(
    api_client: httpx.AsyncClient,
    module_source_connection_stripe: dict,
    composio_auth_provider: dict,
    config,
):
    """Filter for stub on a mixed collection excludes slack results.

    Since the mixed collection has Stripe (synced) + Slack (federated),
    filtering for source_name=stripe should exclude Slack results.
    """
    if not config.TEST_COMPOSIO_SLACK_AUTH_CONFIG_ID or not config.TEST_COMPOSIO_SLACK_ACCOUNT_ID:
        pytest.skip("Slack Composio configuration not available")

    readable_id = module_source_connection_stripe["readable_collection_id"]

    # Add Slack (federated) source to the existing Stripe collection
    resp = await api_client.post(
        "/source-connections",
        json={
            "name": f"Slack Mixed Filter V2 {uuid.uuid4().hex[:8]}",
            "short_name": "slack",
            "readable_collection_id": readable_id,
            "authentication": {
                "provider_readable_id": composio_auth_provider["readable_id"],
                "provider_config": {
                    "auth_config_id": config.TEST_COMPOSIO_SLACK_AUTH_CONFIG_ID,
                    "account_id": config.TEST_COMPOSIO_SLACK_ACCOUNT_ID,
                },
            },
            "sync_immediately": False,
        },
    )
    assert resp.status_code == 200, f"Slack connection failed: {resp.text}"
    slack_conn = resp.json()

    try:
        filter_list = [
            {
                "conditions": [
                    {
                        "field": "connector_context_system_metadata.source_name",
                        "operator": "equals",
                        "value": "stripe",
                    }
                ]
            }
        ]

        results = await do_search_v2(
            api_client,
            readable_id,
            "customer OR invoice",
            tier="instant",
            filter_list=filter_list,
            timeout=10,
        )

        assert "results" in results

        # All returned results should be from stripe, not slack
        for result in results.get("results", []):
            source_name = result.get("connector_context_system_metadata", {}).get("source_name")
            assert source_name == "stripe", (
                f"Expected stripe results only, got source_name={source_name}"
            )
    finally:
        try:
            await api_client.delete(f"/source-connections/{slack_conn['id']}")
        except Exception:
            pass
