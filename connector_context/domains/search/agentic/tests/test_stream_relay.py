"""Tests for SearchStreamRelay — EventBus → PubSub bridge."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from connector_context.core.events.search import (
    RerankingDiagnostics,
    SearchCompletedEvent,
    SearchFailedEvent,
    SearchRerankingEvent,
    SearchStartedEvent,
    SearchThinkingEvent,
    SearchToolCalledEvent,
    ThinkingDiagnostics,
    ToolCalledDiagnostics,
)
from connector_context.domains.search.agentic.subscribers.stream_relay import SearchStreamRelay


class _FakePubSub:
    """Minimal fake PubSub for relay tests."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str, dict]] = []

    async def publish(self, namespace: str, id_value: str, data: dict) -> int:
        """Record published message."""
        self.published.append((namespace, id_value, data))
        return 1


class TestSearchStreamRelay:
    """Tests for the EventBus → PubSub relay."""

    @pytest.mark.asyncio
    async def test_thinking_event_relayed(self) -> None:
        """ThinkingEvent → PubSub with type='thinking'."""
        pubsub = _FakePubSub()
        relay = SearchStreamRelay(pubsub=pubsub)

        event = SearchThinkingEvent(
            organization_id=uuid4(),
            request_id="req-1",
            thinking="I should search...",
            text=None,
            duration_ms=500,
            diagnostics=ThinkingDiagnostics(iteration=0),
        )
        await relay.handle(event)

        assert len(pubsub.published) == 1
        ns, rid, payload = pubsub.published[0]
        assert ns == "agentic_search_v2"
        assert rid == "req-1"
        assert payload["type"] == "thinking"
        assert payload["duration_ms"] == 500

    @pytest.mark.asyncio
    async def test_tool_called_event_relayed(self) -> None:
        """ToolCalledEvent → PubSub with type='tool_call'."""
        pubsub = _FakePubSub()
        relay = SearchStreamRelay(pubsub=pubsub)

        event = SearchToolCalledEvent(
            organization_id=uuid4(),
            request_id="req-1",
            tool_name="search",
            duration_ms=300,
            diagnostics=ToolCalledDiagnostics(
                iteration=0, tool_call_id="tc-1", arguments={}, stats={}
            ),
        )
        await relay.handle(event)

        assert len(pubsub.published) == 1
        assert pubsub.published[0][2]["type"] == "tool_call"
        assert pubsub.published[0][2]["tool_name"] == "search"

    @pytest.mark.asyncio
    async def test_completed_event_relayed(self) -> None:
        """CompletedEvent → PubSub with type='done'."""
        pubsub = _FakePubSub()
        relay = SearchStreamRelay(pubsub=pubsub)

        event = SearchCompletedEvent(
            organization_id=uuid4(),
            request_id="req-1",
            tier="agentic",
            results=[],
            duration_ms=5000,
        )
        await relay.handle(event)

        assert len(pubsub.published) == 1
        assert pubsub.published[0][2]["type"] == "done"

    @pytest.mark.asyncio
    async def test_failed_event_relayed(self) -> None:
        """FailedEvent → PubSub with type='error'."""
        pubsub = _FakePubSub()
        relay = SearchStreamRelay(pubsub=pubsub)

        event = SearchFailedEvent(
            organization_id=uuid4(),
            request_id="req-1",
            tier="agentic",
            message="something broke",
            duration_ms=100,
        )
        await relay.handle(event)

        assert len(pubsub.published) == 1
        assert pubsub.published[0][2]["type"] == "error"
        assert pubsub.published[0][2]["message"] == "something broke"

    @pytest.mark.asyncio
    async def test_started_event_relayed(self) -> None:
        """StartedEvent → PubSub with type='started'."""
        pubsub = _FakePubSub()
        relay = SearchStreamRelay(pubsub=pubsub)

        event = SearchStartedEvent(
            organization_id=uuid4(),
            request_id="req-1",
            tier="agentic",
            collection_readable_id="test-col",
            query="test query",
        )
        await relay.handle(event)

        assert len(pubsub.published) == 1
        assert pubsub.published[0][2]["type"] == "started"

    @pytest.mark.asyncio
    async def test_no_request_id_skipped(self) -> None:
        """Event without request_id → not published."""
        pubsub = _FakePubSub()
        relay = SearchStreamRelay(pubsub=pubsub)

        # DomainEvent without request_id attribute
        from connector_context.core.events.base import DomainEvent
        from connector_context.core.events.enums import SearchEventType

        event = DomainEvent(
            event_type=SearchEventType.THINKING,
            organization_id=uuid4(),
        )
        await relay.handle(event)

        assert len(pubsub.published) == 0

    @pytest.mark.asyncio
    async def test_started_event_payload_fields(self) -> None:
        """StartedEvent → payload includes request_id, tier, collection_readable_id."""
        pubsub = _FakePubSub()
        relay = SearchStreamRelay(pubsub=pubsub)

        event = SearchStartedEvent(
            organization_id=uuid4(),
            request_id="req-start-1",
            tier="agentic",
            collection_readable_id="my-collection",
            query="find something",
        )
        await relay.handle(event)

        assert len(pubsub.published) == 1
        payload = pubsub.published[0][2]
        assert payload["type"] == "started"
        assert payload["request_id"] == "req-start-1"
        assert payload["tier"] == "agentic"
        assert payload["collection_readable_id"] == "my-collection"

    @pytest.mark.asyncio
    async def test_reranking_event_published(self) -> None:
        """RerankingEvent → payload with type=reranking, duration_ms, diagnostics."""
        pubsub = _FakePubSub()
        relay = SearchStreamRelay(pubsub=pubsub)

        event = SearchRerankingEvent(
            organization_id=uuid4(),
            request_id="req-rerank-1",
            duration_ms=150,
            diagnostics=RerankingDiagnostics(
                input_count=20,
                output_count=10,
                model="cohere/rerank-v4.0-pro",
                top_relevance_score=0.99,
                bottom_relevance_score=0.45,
            ),
        )
        await relay.handle(event)

        assert len(pubsub.published) == 1
        payload = pubsub.published[0][2]
        assert payload["type"] == "reranking"
        assert payload["duration_ms"] == 150
        assert payload["diagnostics"]["input_count"] == 20
        assert payload["diagnostics"]["output_count"] == 10

    @pytest.mark.asyncio
    async def test_unknown_event_type_not_published(self) -> None:
        """Event with an event_type not in _SSE_TYPE_MAP → no pubsub.publish call."""
        pubsub = _FakePubSub()
        relay = SearchStreamRelay(pubsub=pubsub)

        from connector_context.core.events.base import DomainEvent
        from connector_context.core.events.enums import EntityEventType

        # Subclass with request_id field so it passes the first guard
        class _UnknownEvent(DomainEvent):
            request_id: str

        # EntityEventType.BATCH_PROCESSED is "entity.batch_processed" — not in _SSE_TYPE_MAP
        event = _UnknownEvent(
            event_type=EntityEventType.BATCH_PROCESSED,
            organization_id=uuid4(),
            request_id="req-unknown-1",
        )
        await relay.handle(event)

        assert len(pubsub.published) == 0

    @pytest.mark.asyncio
    async def test_pubsub_error_does_not_propagate(self) -> None:
        """If pubsub.publish raises, the relay logs but does not re-raise."""
        broken_pubsub = AsyncMock()
        broken_pubsub.publish.side_effect = RuntimeError("redis down")
        relay = SearchStreamRelay(pubsub=broken_pubsub)

        event = SearchStartedEvent(
            organization_id=uuid4(),
            request_id="req-err-1",
            tier="agentic",
            collection_readable_id="col-1",
            query="test query",
        )
        # Should not raise
        await relay.handle(event)

        broken_pubsub.publish.assert_called_once()
