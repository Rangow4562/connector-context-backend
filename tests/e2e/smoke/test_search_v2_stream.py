"""E2E smoke tests for the agentic search V2 streaming endpoint.

Tests the SSE streaming interface:
- POST /collections/{readable_id}/search/agentic/stream

The stream emits `data: {json}\n\n` lines with event types:
- started   — search began
- thinking  — LLM iteration (thinking, text, duration_ms, diagnostics)
- tool_call — tool executed (tool_name, duration_ms, diagnostics)
- reranking — results reranked (duration_ms, diagnostics)
- done      — search complete (results, duration_ms, diagnostics)
- error     — search failed (message, duration_ms)
"""

import json

import httpx
import pytest

# Transient LLM provider error indicators (503, rate limits, queue full).
# When these appear in an error message the test skips instead of failing,
# because they indicate an LLM provider issue, not a bug in our code.
_TRANSIENT_INDICATORS = ("503", "rate", "too_many_requests", "queue_exceeded")


def _is_transient_error(message: str) -> bool:
    """Return True if the error message looks like a transient LLM provider issue."""
    lower = message.lower()
    return any(indicator in lower for indicator in _TRANSIENT_INDICATORS)


class TestAgenticStream:
    """Tests for the agentic search V2 SSE streaming endpoint."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _collect_events(
        api_client: httpx.AsyncClient,
        readable_collection_id: str,
        payload: dict,
        timeout: int = 300,
    ) -> list[dict]:
        """Stream events from the agentic search endpoint until done or error.

        Returns the list of parsed SSE event dicts.
        """
        url = f"/collections/{readable_collection_id}/search/agentic/stream"

        events: list[dict] = []
        async with api_client.stream(
            "POST", url, json=payload, timeout=timeout
        ) as stream:
            assert stream.status_code == 200, (
                f"Stream request failed with status {stream.status_code}"
            )

            async for line in stream.aiter_lines():
                if not line.startswith("data: "):
                    continue

                raw = line[len("data: "):]
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                events.append(event)

                if event.get("type") in ("done", "error"):
                    break

        return events

    @staticmethod
    def _handle_transient_error(events: list[dict]) -> None:
        """If the stream ended with a transient LLM error, skip the test.

        Call this after collecting events. If the terminal event is a
        non-transient error, fail immediately.
        """
        if not events:
            pytest.fail("No SSE events received")

        last = events[-1]
        if last.get("type") != "error":
            return

        message = last.get("message", "")
        if _is_transient_error(message):
            pytest.skip(
                f"Skipped due to transient LLM provider error: {message[:120]}"
            )
        else:
            pytest.fail(f"Stream ended with non-transient error: {message}")

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_stream_returns_sse_events(
        self, api_client: httpx.AsyncClient, module_source_connection_stripe: dict
    ):
        """Stream emits events and terminates with done or error."""
        events = await self._collect_events(
            api_client,
            module_source_connection_stripe["readable_collection_id"],
            {"query": "invoices"},
            timeout=300,
        )

        assert len(events) > 0, "No SSE events received"

        last_type = events[-1].get("type")
        assert last_type in ("done", "error"), (
            f"Stream did not terminate properly. Last event type: {last_type}"
        )

        self._handle_transient_error(events)

    @pytest.mark.asyncio
    async def test_stream_event_types_present(
        self, api_client: httpx.AsyncClient, module_source_connection_stripe: dict
    ):
        """Stream includes at least thinking and tool_call events before done."""
        events = await self._collect_events(
            api_client,
            module_source_connection_stripe["readable_collection_id"],
            {"query": "invoices"},
            timeout=300,
        )
        self._handle_transient_error(events)

        event_types = {e.get("type") for e in events}

        assert "thinking" in event_types, (
            f"Expected 'thinking' event. Got types: {sorted(event_types)}"
        )
        assert "tool_call" in event_types, (
            f"Expected 'tool_call' event. Got types: {sorted(event_types)}"
        )

    @pytest.mark.asyncio
    async def test_stream_done_has_results(
        self, api_client: httpx.AsyncClient, module_source_connection_stripe: dict
    ):
        """The done event contains a results list."""
        events = await self._collect_events(
            api_client,
            module_source_connection_stripe["readable_collection_id"],
            {"query": "invoices"},
            timeout=300,
        )
        self._handle_transient_error(events)

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1, "Expected exactly one done event"

        done = done_events[0]
        assert "results" in done, "done event missing 'results' field"
        assert isinstance(done["results"], list), "results should be a list"

    @pytest.mark.asyncio
    async def test_stream_thinking_has_diagnostics(
        self, api_client: httpx.AsyncClient, module_source_connection_stripe: dict
    ):
        """First thinking event has diagnostics with prompt_tokens and completion_tokens."""
        events = await self._collect_events(
            api_client,
            module_source_connection_stripe["readable_collection_id"],
            {"query": "invoices"},
            timeout=300,
        )
        self._handle_transient_error(events)

        thinking_events = [e for e in events if e.get("type") == "thinking"]
        assert len(thinking_events) > 0, "No thinking events received"

        first_thinking = thinking_events[0]
        assert "diagnostics" in first_thinking, (
            "thinking event missing 'diagnostics' field"
        )

        diag = first_thinking["diagnostics"]
        assert "prompt_tokens" in diag, "diagnostics missing prompt_tokens"
        assert "completion_tokens" in diag, "diagnostics missing completion_tokens"

    @pytest.mark.asyncio
    async def test_stream_tool_call_has_stats(
        self, api_client: httpx.AsyncClient, module_source_connection_stripe: dict
    ):
        """First tool_call event has tool_name (str), duration_ms (int), diagnostics."""
        events = await self._collect_events(
            api_client,
            module_source_connection_stripe["readable_collection_id"],
            {"query": "invoices"},
            timeout=300,
        )
        self._handle_transient_error(events)

        tool_events = [e for e in events if e.get("type") == "tool_call"]
        assert len(tool_events) > 0, "No tool_call events received"

        first_tool = tool_events[0]
        assert "tool_name" in first_tool, "tool_call event missing 'tool_name'"
        assert isinstance(first_tool["tool_name"], str)

        assert "duration_ms" in first_tool, "tool_call event missing 'duration_ms'"
        assert isinstance(first_tool["duration_ms"], int)

        assert "diagnostics" in first_tool, "tool_call event missing 'diagnostics'"

    @pytest.mark.asyncio
    async def test_stream_transient_error_tolerated(
        self, api_client: httpx.AsyncClient, module_source_connection_stripe: dict
    ):
        """If the stream ends with a transient LLM error, skip instead of fail.

        This test exists to document the tolerance behavior. If the stream
        terminates with a non-transient error, it fails. If transient, it skips.
        If done, it passes.
        """
        events = await self._collect_events(
            api_client,
            module_source_connection_stripe["readable_collection_id"],
            {"query": "invoices"},
            timeout=300,
        )

        assert len(events) > 0, "No SSE events received"

        last = events[-1]
        if last.get("type") == "error":
            message = last.get("message", "")
            if _is_transient_error(message):
                pytest.skip(
                    f"Transient LLM error (expected tolerance): {message[:120]}"
                )
            else:
                pytest.fail(
                    f"Non-transient error should not be tolerated: {message}"
                )

        # If we got here, the stream completed successfully
        assert last.get("type") == "done"
