"""Tests for ContextManager — budget, fit, compress, and emergency compression."""

import pytest

from connector_context.domains.search.agentic.context_manager import (
    _format_read_older,
    _format_read_previous,
    _format_search_older,
    _format_search_previous,
)
from connector_context.domains.search.agentic.exceptions import ContextBudgetExhaustedError
from connector_context.domains.search.agentic.tests.conftest import (
    make_context_mgr,
    make_rendered_result,
    make_result,
    make_state,
)
from connector_context.domains.search.agentic.tools.types import (
    CollectToolResult,
    ReadToolResult,
    SearchToolResult,
    ToolErrorResult,
)

# ── Budget calculation ────────────────────────────────────────────────


class TestBudget:
    """Tests for budget calculation properties."""

    def test_fresh_conversation_has_large_budget(self) -> None:
        cm = make_context_mgr(context_window=100_000)
        messages = [{"role": "user", "content": "test"}]
        assert cm.available_budget(messages) > 50_000

    def test_thinking_enabled_reduces_input_budget(self) -> None:
        cm_think = make_context_mgr(thinking_enabled=True, max_output_tokens=40_000)
        cm_no = make_context_mgr(thinking_enabled=False, max_output_tokens=40_000)
        assert cm_think.input_budget < cm_no.input_budget

    def test_check_budget_false_when_exhausted(self) -> None:
        cm = make_context_mgr(context_window=500, max_output_tokens=100)
        messages = [{"role": "user", "content": "x" * 4000}]
        assert cm.check_budget(messages) is False

    def test_check_budget_true_when_healthy(self) -> None:
        cm = make_context_mgr(context_window=100_000)
        messages = [{"role": "user", "content": "test"}]
        assert cm.check_budget(messages) is True

    def test_budget_decreases_as_messages_grow(self) -> None:
        cm = make_context_mgr()
        budget_empty = cm.available_budget([])
        budget_with = cm.available_budget([{"role": "user", "content": "x" * 1000}])
        assert budget_with < budget_empty


# ── Fit tool results ──────────────────────────────────────────────────


class TestFitToolResult:
    """Tests for fitting tool results into budget."""

    def test_fit_search_all_fit(self) -> None:
        cm = make_context_mgr(context_window=100_000)
        summaries = [make_rendered_result(f"ent-{i}") for i in range(5)]
        result = SearchToolResult(summaries=summaries, new_count=5)

        content = cm.fit_tool_result(result, 100_000)

        for s in summaries:
            assert s.text in content
        assert "not shown" not in content

    def test_fit_search_truncated(self) -> None:
        cm = make_context_mgr(context_window=800, max_output_tokens=100)
        summaries = [make_rendered_result(f"ent-{i}", text="x" * 200) for i in range(10)]
        result = SearchToolResult(summaries=summaries, new_count=10)

        # Small budget forces truncation
        content = cm.fit_tool_result(result, 200)

        assert "not shown" in content

    def test_fit_search_empty(self) -> None:
        cm = make_context_mgr()
        result = SearchToolResult(summaries=[], new_count=0)

        content = cm.fit_tool_result(result, 100_000)

        assert "No results found" in content

    def test_fit_search_pagination_warning(self) -> None:
        cm = make_context_mgr()
        summaries = [make_rendered_result(f"ent-{i}") for i in range(10)]
        result = SearchToolResult(
            summaries=summaries,
            new_count=10,
            requested_limit=10,
            requested_offset=0,
        )

        content = cm.fit_tool_result(result, 100_000)

        assert "Results hit the limit" in content
        assert "offset=10" in content

    def test_fit_read_triage_nudge(self) -> None:
        cm = make_context_mgr()
        entities = [make_rendered_result("ent-1", text="Full content here.")]
        result = ReadToolResult(entities=entities, not_found=[], read_entity_ids=["ent-1"])

        content = cm.fit_tool_result(result, 100_000)

        assert "Entities read:" in content
        assert "add_to_results" in content

    def test_fit_collect_always_fits(self) -> None:
        cm = make_context_mgr(context_window=500, max_output_tokens=100)
        result = CollectToolResult(added=["ent-1"], total_collected=1)

        content = cm.fit_tool_result(result, 100_000)

        assert "Added 1" in content

    def test_fit_error_always_fits(self) -> None:
        cm = make_context_mgr(context_window=500, max_output_tokens=100)
        result = ToolErrorResult(error="Something went wrong")

        content = cm.fit_tool_result(result, 100_000)

        assert "Something went wrong" in content


# ── Compress history ──────────────────────────────────────────────────


class TestCompressHistory:
    """Tests for 3-tier context compression."""

    def test_current_iteration_untouched(self) -> None:
        cm = make_context_mgr()
        r = make_result(entity_id="ent-1")
        state = make_state(results={"ent-1": r})
        state.results_by_tool_call_id["tc-1"] = [r]

        messages = [
            {"role": "tool", "tool_call_id": "tc-1", "_tool_name": "search", "content": "full"},
        ]

        result = cm.compress_history(
            messages,
            state,
            current_search_ids={"tc-1"},
            current_read_ids=set(),
            previous_search_ids=set(),
            previous_read_ids=set(),
        )

        assert result[0]["content"] == "full"

    def test_previous_search_compressed(self) -> None:
        cm = make_context_mgr()
        r = make_result(entity_id="ent-1", name="Doc A")
        state = make_state(results={"ent-1": r})
        state.results_by_tool_call_id["tc-old"] = [r]

        messages = [
            {"role": "tool", "tool_call_id": "tc-old", "_tool_name": "search", "content": "full"},
        ]

        result = cm.compress_history(
            messages,
            state,
            current_search_ids=set(),
            current_read_ids=set(),
            previous_search_ids={"tc-old"},
            previous_read_ids=set(),
        )

        assert "IDs only" in result[0]["content"]
        assert "Doc A" in result[0]["content"]

    def test_older_search_compressed_to_oneliner(self) -> None:
        cm = make_context_mgr()
        r = make_result(entity_id="ent-1")
        state = make_state(results={"ent-1": r})
        state.results_by_tool_call_id["tc-old"] = [r]

        messages = [
            {"role": "tool", "tool_call_id": "tc-old", "_tool_name": "search", "content": "full"},
        ]

        result = cm.compress_history(
            messages,
            state,
            current_search_ids=set(),
            current_read_ids=set(),
            previous_search_ids=set(),
            previous_read_ids=set(),
        )

        assert "*[Searched:" in result[0]["content"]

    def test_no_compressible_messages_unchanged(self) -> None:
        cm = make_context_mgr()
        state = make_state()

        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        result = cm.compress_history(
            messages,
            state,
            current_search_ids=set(),
            current_read_ids=set(),
            previous_search_ids=set(),
            previous_read_ids=set(),
        )

        assert result is messages  # same object, no copy needed

    def test_does_not_mutate_input(self) -> None:
        cm = make_context_mgr()
        r = make_result(entity_id="ent-1")
        state = make_state(results={"ent-1": r})
        state.results_by_tool_call_id["tc-old"] = [r]

        messages = [
            {"role": "tool", "tool_call_id": "tc-old", "_tool_name": "search", "content": "full"},
        ]
        original_content = messages[0]["content"]

        cm.compress_history(
            messages,
            state,
            current_search_ids=set(),
            current_read_ids=set(),
            previous_search_ids=set(),
            previous_read_ids=set(),
        )

        assert messages[0]["content"] == original_content


# ── Compression formatters ────────────────────────────────────────────


class TestCompressionFormatters:
    """Tests for the standalone formatting functions."""

    def test_search_previous_format(self) -> None:
        r = make_result(entity_id="ent-1", name="Doc A", score=0.95)
        result = _format_search_previous([r])
        assert "1 search results" in result
        assert "`ent-1`" in result
        assert "Doc A" in result

    def test_search_older_format(self) -> None:
        r = make_result()
        result = _format_search_older([r])
        assert "*[Searched: 1 results returned]*" == result

    def test_read_previous_format(self) -> None:
        r = make_result(entity_id="ent-1", name="Doc A")
        result = _format_read_previous([r])
        assert "Read 1 entities" in result
        assert "metadata only" in result

    def test_read_older_format(self) -> None:
        r = make_result()
        result = _format_read_older([r])
        assert "*[Read 1 entities]*" == result

    def test_empty_results(self) -> None:
        assert "No results found" in _format_search_previous([])
        assert "No results found" in _format_search_older([])
        assert "*[Read: no results]*" == _format_read_previous([])
        assert "*[Read: no results]*" == _format_read_older([])


# ── max_output_tokens ────────────────────────────────────────────────


class TestMaxOutputTokens:
    """Tests for dynamic max_tokens computation."""

    def test_returns_max_output_tokens_when_input_is_small(self) -> None:
        """With plenty of room, returns the model's max_output_tokens."""
        cm = make_context_mgr(context_window=200_000, max_output_tokens=64_000)
        messages = [{"role": "user", "content": "short query"}]
        assert cm.max_output_tokens(messages) == 64_000

    def test_shrinks_when_input_is_large(self) -> None:
        """When input fills most of the window, max_tokens shrinks below max_output_tokens."""
        cm = make_context_mgr(context_window=10_000, max_output_tokens=8_000)
        # Fill ~6K tokens of input (6000 chars / 4 chars_per_token = 1500 tokens,
        # plus fixed overhead). Use enough to force shrinkage.
        messages = [{"role": "user", "content": "x" * 20_000}]  # ~5000 tokens
        result = cm.max_output_tokens(messages)
        assert result < 8_000
        assert result > 0

    def test_triggers_emergency_compress_when_nearly_full(self) -> None:
        """When input leaves less than _MIN_OUTPUT_TOKENS, emergency compress triggers."""
        # Window of 10K, each message ~25 tokens (100 chars / 4). 20 pairs = ~1000 tokens.
        # After emergency compress, half dropped → ~500 tokens → plenty of output room.
        cm = make_context_mgr(context_window=10_000, max_output_tokens=5_000)
        messages = [{"role": "user", "content": "query"}]
        for i in range(80):
            messages.append({"role": "assistant", "content": f"thinking {i}" * 30})
            messages.append({"role": "tool", "tool_call_id": f"tc-{i}",
                             "content": f"result {i}" * 30})

        # Messages should be large enough to trigger emergency compress
        assert cm.input_tokens(messages) > cm._context_window - cm._MIN_OUTPUT_TOKENS

        # Should not raise — emergency compression should rescue it
        result = cm.max_output_tokens(messages)
        assert result >= cm._MIN_OUTPUT_TOKENS
        # Messages should have been trimmed (mutated in place)
        assert len(messages) < 161  # was 1 + 80*2 = 161

    def test_raises_when_even_emergency_compress_fails(self) -> None:
        """If emergency compress can't free enough space, raises ContextBudgetExhaustedError."""
        cm = make_context_mgr(context_window=500, max_output_tokens=400)
        # Single huge message that can't be compressed away
        messages = [{"role": "user", "content": "x" * 8_000}]  # ~2000 tokens > 500 window

        with pytest.raises(ContextBudgetExhaustedError):
            cm.max_output_tokens(messages)

    def test_counts_thinking_in_input(self) -> None:
        """Assistant thinking tokens are counted as input for the next call."""
        cm = make_context_mgr(context_window=10_000, max_output_tokens=64_000)
        messages_without = [{"role": "user", "content": "query"}]
        messages_with = [
            {"role": "user", "content": "query"},
            {"role": "assistant", "content": "response", "_thinking": "x" * 4_000},
        ]
        result_without = cm.max_output_tokens(messages_without)
        result_with = cm.max_output_tokens(messages_with)
        assert result_with < result_without

    def test_counts_tool_calls_in_input(self) -> None:
        """Assistant tool call arguments are counted as input."""
        cm = make_context_mgr(context_window=10_000, max_output_tokens=64_000)
        messages_without = [{"role": "user", "content": "query"}]
        messages_with = [
            {"role": "user", "content": "query"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "tc-1", "type": "function", "function": {
                    "name": "search", "arguments": "x" * 4_000,
                }}
            ]},
        ]
        result_without = cm.max_output_tokens(messages_without)
        result_with = cm.max_output_tokens(messages_with)
        assert result_with < result_without


# ── Emergency compression ────────────────────────────────────────────


class TestEmergencyCompress:
    """Tests for last-resort message dropping."""

    def test_drops_oldest_half(self) -> None:
        """Emergency compress keeps first message and newest half."""
        cm = make_context_mgr()
        messages = [{"role": "user", "content": "query"}]
        for i in range(10):
            messages.append({"role": "assistant", "content": f"reply-{i}"})

        result = cm.emergency_compress(messages)

        # First message preserved
        assert result[0]["content"] == "query"
        # System note injected
        assert "Context limit reached" in result[1]["content"]
        # Newest messages preserved
        assert result[-1]["content"] == "reply-9"
        # Older messages dropped
        assert len(result) < len(messages)

    def test_injects_system_note(self) -> None:
        """The injected note tells the LLM messages were dropped."""
        cm = make_context_mgr()
        messages = [
            {"role": "user", "content": "query"},
            {"role": "assistant", "content": "old-1"},
            {"role": "assistant", "content": "old-2"},
            {"role": "assistant", "content": "old-3"},
            {"role": "assistant", "content": "recent"},
        ]

        result = cm.emergency_compress(messages)

        system_note = result[1]
        assert system_note["role"] == "user"
        assert "dropped" in system_note["content"].lower()

    def test_preserves_first_message(self) -> None:
        """First message (user query) is always kept."""
        cm = make_context_mgr()
        messages = [
            {"role": "user", "content": "original query"},
            {"role": "assistant", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "assistant", "content": "c"},
        ]

        result = cm.emergency_compress(messages)
        assert result[0]["content"] == "original query"

    def test_tiny_conversation_unchanged(self) -> None:
        """With <= 2 messages, nothing to drop."""
        cm = make_context_mgr()
        messages = [{"role": "user", "content": "query"}]
        result = cm.emergency_compress(messages)
        assert len(result) == 1
        assert result[0]["content"] == "query"

    def test_actually_reduces_token_count(self) -> None:
        """Emergency compression meaningfully reduces the total tokens."""
        cm = make_context_mgr(context_window=100_000)
        messages = [{"role": "user", "content": "query"}]
        for i in range(20):
            messages.append({"role": "assistant", "content": f"thinking {'x' * 500} {i}"})
            messages.append({"role": "tool", "tool_call_id": f"tc-{i}",
                             "content": f"result {'y' * 500} {i}"})

        tokens_before = cm.input_tokens(messages)
        result = cm.emergency_compress(messages)
        tokens_after = cm.input_tokens(result)

        assert tokens_after < tokens_before * 0.7  # at least 30% reduction


# ── Available budget and fair division ───────────────────────────────


class TestAvailableBudget:
    """Tests for available_budget — space for tool results."""

    def test_reserves_output_space(self) -> None:
        """available_budget leaves room for the LLM's output response."""
        cm = make_context_mgr(context_window=100_000, max_output_tokens=20_000)
        messages = [{"role": "user", "content": "query"}]

        budget = cm.available_budget(messages)
        max_out = cm.max_output_tokens(messages)

        # budget + output + input should not exceed context_window
        input_tokens = cm.input_tokens(messages)
        assert budget + cm.output_reserve + input_tokens <= cm._context_window

    def test_shrinks_as_messages_grow(self) -> None:
        """Adding messages reduces available budget."""
        cm = make_context_mgr(context_window=100_000)
        messages_small = [{"role": "user", "content": "query"}]
        messages_large = [
            {"role": "user", "content": "query"},
            {"role": "assistant", "content": "x" * 10_000},
        ]

        assert cm.available_budget(messages_large) < cm.available_budget(messages_small)

    def test_returns_zero_not_negative(self) -> None:
        """When messages exceed budget, returns 0 not negative."""
        cm = make_context_mgr(context_window=500, max_output_tokens=100)
        messages = [{"role": "user", "content": "x" * 8_000}]
        assert cm.available_budget(messages) == 0


# ── input_tokens helper ──────────────────────────────────────────────


class TestInputTokens:
    """Tests for exact input token counting."""

    def test_counts_fixed_overhead(self) -> None:
        """Input tokens include system prompt and tool definitions even with no messages."""
        cm = make_context_mgr()
        assert cm.input_tokens([]) == cm.fixed_overhead
        assert cm.fixed_overhead > 0

    def test_counts_message_content(self) -> None:
        """Message content tokens are added to fixed overhead."""
        cm = make_context_mgr()
        empty = cm.input_tokens([])
        with_msg = cm.input_tokens([{"role": "user", "content": "hello world"}])
        assert with_msg > empty

    def test_counts_thinking(self) -> None:
        """_thinking field on assistant messages is counted."""
        cm = make_context_mgr()
        without = cm.input_tokens([{"role": "assistant", "content": "hi"}])
        with_thinking = cm.input_tokens([
            {"role": "assistant", "content": "hi", "_thinking": "x" * 1000}
        ])
        assert with_thinking > without

    def test_counts_tool_calls(self) -> None:
        """tool_calls on assistant messages are counted."""
        cm = make_context_mgr()
        without = cm.input_tokens([{"role": "assistant", "content": "hi"}])
        with_tc = cm.input_tokens([{"role": "assistant", "content": "hi", "tool_calls": [
            {"id": "tc-1", "type": "function", "function": {"name": "s", "arguments": "x" * 500}}
        ]}])
        assert with_tc > without
