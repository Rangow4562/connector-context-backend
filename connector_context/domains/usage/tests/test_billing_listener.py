"""Unit tests for UsageBillingListener — event routing to the usage ledger."""

from uuid import UUID, uuid4

import pytest

from connector_context.core.events.enums import SourceConnectionEventType, SyncEventType
from connector_context.core.events.source_connection import SourceConnectionLifecycleEvent
from connector_context.core.events.sync import (
    EntityBatchProcessedEvent,
    QueryProcessedEvent,
    SyncLifecycleEvent,
)
from connector_context.domains.usage.fakes.ledger import FakeUsageLedger
from connector_context.domains.usage.subscribers.billing_listener import UsageBillingListener
from connector_context.domains.usage.types import ActionType

ORG_ID = UUID("00000000-0000-0000-0000-000000000001")
SYNC_ID = uuid4()
JOB_ID = uuid4()
COLLECTION_ID = uuid4()
SC_ID = uuid4()


def _make_listener():
    ledger = FakeUsageLedger()
    listener = UsageBillingListener(ledger=ledger)
    return listener, ledger


# ---------------------------------------------------------------------------
# EntityBatchProcessedEvent
# ---------------------------------------------------------------------------


class TestEntityBatchRouting:
    @pytest.mark.asyncio
    async def test_records_inserted_plus_updated(self):
        listener, ledger = _make_listener()
        event = EntityBatchProcessedEvent(
            organization_id=ORG_ID,
            sync_id=SYNC_ID,
            sync_job_id=JOB_ID,
            collection_id=COLLECTION_ID,
            source_connection_id=SC_ID,
            inserted=10,
            updated=5,
            deleted=2,
            kept=3,
            billable=True,
        )

        await listener.handle(event)

        assert ledger.recorded[(ORG_ID, ActionType.ENTITIES)] == 15

    @pytest.mark.asyncio
    async def test_skips_non_billable(self):
        listener, ledger = _make_listener()
        event = EntityBatchProcessedEvent(
            organization_id=ORG_ID,
            sync_id=SYNC_ID,
            sync_job_id=JOB_ID,
            collection_id=COLLECTION_ID,
            source_connection_id=SC_ID,
            inserted=50,
            updated=25,
            billable=False,
        )

        await listener.handle(event)

        assert (ORG_ID, ActionType.ENTITIES) not in ledger.recorded

    @pytest.mark.asyncio
    async def test_skips_zero_entities(self):
        listener, ledger = _make_listener()
        event = EntityBatchProcessedEvent(
            organization_id=ORG_ID,
            sync_id=SYNC_ID,
            sync_job_id=JOB_ID,
            collection_id=COLLECTION_ID,
            source_connection_id=SC_ID,
            inserted=0,
            updated=0,
            billable=True,
        )

        await listener.handle(event)

        assert len(ledger.record_calls) == 0

    @pytest.mark.asyncio
    async def test_only_counts_inserted_and_updated(self):
        """Deleted and kept entities should not be billed."""
        listener, ledger = _make_listener()
        event = EntityBatchProcessedEvent(
            organization_id=ORG_ID,
            sync_id=SYNC_ID,
            sync_job_id=JOB_ID,
            collection_id=COLLECTION_ID,
            source_connection_id=SC_ID,
            inserted=7,
            updated=3,
            deleted=100,
            kept=200,
            billable=True,
        )

        await listener.handle(event)

        assert ledger.recorded[(ORG_ID, ActionType.ENTITIES)] == 10


# ---------------------------------------------------------------------------
# QueryProcessedEvent
# ---------------------------------------------------------------------------


class TestQueryRouting:
    @pytest.mark.asyncio
    async def test_records_query(self):
        listener, ledger = _make_listener()
        event = QueryProcessedEvent(
            organization_id=ORG_ID,
            queries=1,
            billable=True,
        )

        await listener.handle(event)

        assert ledger.recorded[(ORG_ID, ActionType.QUERIES)] == 1

    @pytest.mark.asyncio
    async def test_records_multiple_queries(self):
        listener, ledger = _make_listener()
        event = QueryProcessedEvent(
            organization_id=ORG_ID,
            queries=5,
            billable=True,
        )

        await listener.handle(event)

        assert ledger.recorded[(ORG_ID, ActionType.QUERIES)] == 5

    @pytest.mark.asyncio
    async def test_skips_non_billable_query(self):
        listener, ledger = _make_listener()
        event = QueryProcessedEvent(
            organization_id=ORG_ID,
            queries=1,
            billable=False,
        )

        await listener.handle(event)

        assert len(ledger.record_calls) == 0


# ---------------------------------------------------------------------------
# SyncLifecycleEvent — terminal events flush the ledger
# ---------------------------------------------------------------------------


class TestSyncLifecycleRouting:
    @pytest.mark.asyncio
    async def test_completed_flushes(self):
        listener, ledger = _make_listener()
        event = SyncLifecycleEvent.completed(
            organization_id=ORG_ID,
            sync_id=SYNC_ID,
            sync_job_id=JOB_ID,
            collection_id=COLLECTION_ID,
            source_connection_id=SC_ID,
            source_type="slack",
            collection_name="test",
            collection_readable_id="test-col",
        )

        await listener.handle(event)

        assert ORG_ID in ledger.flushed_orgs

    @pytest.mark.asyncio
    async def test_failed_flushes(self):
        listener, ledger = _make_listener()
        event = SyncLifecycleEvent.failed(
            organization_id=ORG_ID,
            sync_id=SYNC_ID,
            sync_job_id=JOB_ID,
            collection_id=COLLECTION_ID,
            source_connection_id=SC_ID,
            source_type="slack",
            collection_name="test",
            collection_readable_id="test-col",
            error="something broke",
        )

        await listener.handle(event)

        assert ORG_ID in ledger.flushed_orgs

    @pytest.mark.asyncio
    async def test_cancelled_flushes(self):
        listener, ledger = _make_listener()
        event = SyncLifecycleEvent.cancelled(
            organization_id=ORG_ID,
            sync_id=SYNC_ID,
            sync_job_id=JOB_ID,
            collection_id=COLLECTION_ID,
            source_connection_id=SC_ID,
            source_type="slack",
            collection_name="test",
            collection_readable_id="test-col",
        )

        await listener.handle(event)

        assert ORG_ID in ledger.flushed_orgs

    @pytest.mark.asyncio
    async def test_running_does_not_flush(self):
        listener, ledger = _make_listener()
        event = SyncLifecycleEvent.running(
            organization_id=ORG_ID,
            sync_id=SYNC_ID,
            sync_job_id=JOB_ID,
            collection_id=COLLECTION_ID,
            source_connection_id=SC_ID,
            source_type="slack",
            collection_name="test",
            collection_readable_id="test-col",
        )

        await listener.handle(event)

        assert len(ledger.flushed_orgs) == 0

    @pytest.mark.asyncio
    async def test_pending_does_not_flush(self):
        listener, ledger = _make_listener()
        event = SyncLifecycleEvent.pending(
            organization_id=ORG_ID,
            sync_id=SYNC_ID,
            sync_job_id=JOB_ID,
            collection_id=COLLECTION_ID,
            source_connection_id=SC_ID,
            source_type="slack",
            collection_name="test",
            collection_readable_id="test-col",
        )

        await listener.handle(event)

        assert len(ledger.flushed_orgs) == 0


# ---------------------------------------------------------------------------
# SourceConnectionLifecycleEvent
# ---------------------------------------------------------------------------


class TestSourceConnectionRouting:
    @pytest.mark.asyncio
    async def test_created_records_plus_one(self):
        listener, ledger = _make_listener()
        event = SourceConnectionLifecycleEvent.created(
            organization_id=ORG_ID,
            source_connection_id=SC_ID,
            source_type="slack",
            collection_readable_id="test-col",
        )

        await listener.handle(event)

        assert ledger.recorded[(ORG_ID, ActionType.SOURCE_CONNECTIONS)] == 1

    @pytest.mark.asyncio
    async def test_deleted_records_minus_one(self):
        listener, ledger = _make_listener()
        event = SourceConnectionLifecycleEvent.deleted(
            organization_id=ORG_ID,
            source_connection_id=SC_ID,
            source_type="slack",
            collection_readable_id="test-col",
        )

        await listener.handle(event)

        assert ledger.recorded[(ORG_ID, ActionType.SOURCE_CONNECTIONS)] == -1

    @pytest.mark.asyncio
    async def test_auth_completed_is_ignored(self):
        """AUTH_COMPLETED is not a billable source connection event."""
        listener, ledger = _make_listener()
        event = SourceConnectionLifecycleEvent.auth_completed(
            organization_id=ORG_ID,
            source_connection_id=SC_ID,
            source_type="slack",
            collection_readable_id="test-col",
        )

        await listener.handle(event)

        assert len(ledger.record_calls) == 0


# ---------------------------------------------------------------------------
# Error handling — listener should not raise
# ---------------------------------------------------------------------------


class TestListenerErrorHandling:
    @pytest.mark.asyncio
    async def test_swallows_ledger_errors(self):
        """If the ledger raises, the listener logs but does not propagate."""

        class BrokenLedger(FakeUsageLedger):
            async def record(self, *args, **kwargs):
                raise RuntimeError("db connection lost")

        listener = UsageBillingListener(ledger=BrokenLedger())
        event = QueryProcessedEvent(
            organization_id=ORG_ID,
            queries=1,
            billable=True,
        )

        await listener.handle(event)


# ---------------------------------------------------------------------------
# EVENT_PATTERNS sanity check
# ---------------------------------------------------------------------------


class TestSearchCompletedRouting:
    """Tests for SearchCompletedEvent → billing routing."""

    @pytest.mark.asyncio
    async def test_agentic_with_diagnostics_records_tokens(self):
        """Agentic tier with diagnostics → TOKENS recorded via normalize_tokens."""
        from connector_context.adapters.llm.registry import get_model_spec
        from connector_context.core.events.search import CompletedDiagnostics, SearchCompletedEvent, SearchTier
        from connector_context.domains.search.config import SearchConfig

        listener, ledger = _make_listener()

        # Use real fallback chain to get real price factors
        provider, model = SearchConfig.LLM_FALLBACK_CHAIN[0]
        spec = get_model_spec(provider, model)

        prompt_tokens = 1000
        completion_tokens = 500
        expected_normalized = int(
            prompt_tokens * spec.input_price_factor
            + completion_tokens * spec.output_price_factor
        )

        event = SearchCompletedEvent(
            organization_id=ORG_ID,
            request_id="req-1",
            tier=SearchTier.AGENTIC,
            results=[],
            duration_ms=5000,
            billable=True,
            diagnostics=CompletedDiagnostics(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
        )

        await listener.handle(event)

        assert ledger.recorded[(ORG_ID, ActionType.TOKENS)] == expected_normalized
        assert expected_normalized > 0  # sanity: non-zero tokens were recorded

    @pytest.mark.asyncio
    async def test_classic_records_query(self):
        """Classic tier → QUERIES amount=1."""
        from connector_context.core.events.search import SearchCompletedEvent, SearchTier

        listener, ledger = _make_listener()
        event = SearchCompletedEvent(
            organization_id=ORG_ID,
            request_id="req-2",
            tier=SearchTier.CLASSIC,
            results=[],
            duration_ms=200,
            billable=True,
        )

        await listener.handle(event)

        assert ledger.recorded[(ORG_ID, ActionType.QUERIES)] == 1

    @pytest.mark.asyncio
    async def test_not_billable_skipped(self):
        """Non-billable SearchCompletedEvent → no records."""
        from connector_context.core.events.search import SearchCompletedEvent, SearchTier

        listener, ledger = _make_listener()
        event = SearchCompletedEvent(
            organization_id=ORG_ID,
            request_id="req-3",
            tier=SearchTier.AGENTIC,
            results=[],
            duration_ms=100,
            billable=False,
        )

        await listener.handle(event)

        assert len(ledger.record_calls) == 0

    @pytest.mark.asyncio
    async def test_agentic_without_diagnostics_records_query(self):
        """Agentic tier but no diagnostics → falls through to QUERIES."""
        from connector_context.core.events.search import SearchCompletedEvent, SearchTier

        listener, ledger = _make_listener()
        event = SearchCompletedEvent(
            organization_id=ORG_ID,
            request_id="req-4",
            tier=SearchTier.AGENTIC,
            results=[],
            duration_ms=300,
            billable=True,
            diagnostics=None,
        )

        await listener.handle(event)

        assert ledger.recorded[(ORG_ID, ActionType.QUERIES)] == 1

    @pytest.mark.asyncio
    async def test_agentic_zero_tokens_not_recorded(self):
        """Agentic with diagnostics but zero normalized tokens → no record."""
        from connector_context.core.events.search import CompletedDiagnostics, SearchCompletedEvent, SearchTier

        listener, ledger = _make_listener()
        event = SearchCompletedEvent(
            organization_id=ORG_ID,
            request_id="req-5",
            tier=SearchTier.AGENTIC,
            results=[],
            duration_ms=100,
            billable=True,
            diagnostics=CompletedDiagnostics(
                prompt_tokens=0,
                completion_tokens=0,
            ),
        )

        await listener.handle(event)

        # normalize_tokens(0, 0, ...) = 0 → no record call
        assert len(ledger.record_calls) == 0

    @pytest.mark.asyncio
    async def test_instant_records_query(self):
        """Instant tier → QUERIES amount=1."""
        from connector_context.core.events.search import SearchCompletedEvent, SearchTier

        listener, ledger = _make_listener()
        event = SearchCompletedEvent(
            organization_id=ORG_ID,
            request_id="req-6",
            tier=SearchTier.INSTANT,
            results=[],
            duration_ms=50,
            billable=True,
        )

        await listener.handle(event)

        assert ledger.recorded[(ORG_ID, ActionType.QUERIES)] == 1


class TestEventPatterns:
    def test_covers_expected_namespaces(self):
        patterns = UsageBillingListener.EVENT_PATTERNS
        assert "entity.*" in patterns
        assert "query.*" in patterns
        assert "sync.*" in patterns
        assert "source_connection.*" in patterns
