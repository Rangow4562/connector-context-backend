"""Tests for SearchPlanBuilder — user filters AND'd into LLM groups."""

import pytest
from pydantic import ValidationError

from connector_context.domains.search.builders.search_plan import SearchPlanBuilder
from connector_context.domains.search.types.filters import (
    FilterCondition,
    FilterGroup,
    FilterOperator,
    FilterableField,
)
from connector_context.domains.search.types.plan import RetrievalStrategy, SearchPlan, SearchQuery


def _make_plan(filter_groups: list[FilterGroup] | None = None) -> SearchPlan:
    """Create a minimal search plan for testing."""
    return SearchPlan(
        query=SearchQuery(primary="test query"),
        filter_groups=filter_groups or [],
        limit=10,
        offset=0,
        retrieval_strategy=RetrievalStrategy.HYBRID,
    )


def _make_filter_group(field: FilterableField, value: str) -> FilterGroup:
    """Create a simple equals filter group."""
    return FilterGroup(
        conditions=[
            FilterCondition(
                field=field,
                operator=FilterOperator.EQUALS,
                value=value,
            )
        ]
    )


class TestSearchPlanBuilder:
    """Tests for SearchPlanBuilder — user filters AND'd into LLM groups."""

    def test_no_user_filters_returns_original(self) -> None:
        """When no user filters, returns the original plan unchanged."""
        plan = _make_plan()
        result = SearchPlanBuilder.build(plan, [])
        assert result is plan

    def test_user_filter_and_into_llm_group(self) -> None:
        """User filter conditions are AND'd into each LLM filter group."""
        llm_filter = _make_filter_group(
            FilterableField.SYSTEM_METADATA_SOURCE_NAME, "slack"
        )
        plan = _make_plan(filter_groups=[llm_filter])

        user_filter = _make_filter_group(
            FilterableField.SYSTEM_METADATA_ENTITY_TYPE, "SlackMessageEntity"
        )
        result = SearchPlanBuilder.build(plan, [user_filter])

        # Still one group, but now with 2 conditions (LLM + user AND'd)
        assert len(result.filter_groups) == 1
        assert len(result.filter_groups[0].conditions) == 2

    def test_user_filter_no_llm_groups_creates_group(self) -> None:
        """When LLM has no filter groups, user conditions become a new group."""
        plan = _make_plan()

        user_filter = _make_filter_group(FilterableField.NAME, "doc1")
        result = SearchPlanBuilder.build(plan, [user_filter])

        assert len(result.filter_groups) == 1
        assert len(result.filter_groups[0].conditions) == 1

    def test_user_filter_and_into_multiple_llm_groups(self) -> None:
        """User conditions AND'd into every LLM group."""
        llm_group_a = _make_filter_group(
            FilterableField.SYSTEM_METADATA_SOURCE_NAME, "slack"
        )
        llm_group_b = _make_filter_group(
            FilterableField.SYSTEM_METADATA_SOURCE_NAME, "notion"
        )
        plan = _make_plan(filter_groups=[llm_group_a, llm_group_b])

        user_filter = _make_filter_group(
            FilterableField.SYSTEM_METADATA_ENTITY_TYPE, "MessageEntity"
        )
        result = SearchPlanBuilder.build(plan, [user_filter])

        # Still 2 groups, each now has 2 conditions
        assert len(result.filter_groups) == 2
        assert len(result.filter_groups[0].conditions) == 2
        assert len(result.filter_groups[1].conditions) == 2

    def test_user_filters_do_not_mutate_original(self) -> None:
        """User filters don't mutate the original plan."""
        plan = _make_plan()
        original_len = len(plan.filter_groups)

        user_filter = _make_filter_group(FilterableField.NAME, "doc1")
        SearchPlanBuilder.build(plan, [user_filter])

        assert len(plan.filter_groups) == original_len

    def test_plan_fields_preserved(self) -> None:
        """Non-filter fields are preserved in the result."""
        plan = _make_plan()
        user_filter = _make_filter_group(FilterableField.NAME, "doc1")
        result = SearchPlanBuilder.build(plan, [user_filter])

        assert result.query.primary == "test query"
        assert result.limit == 10
        assert result.offset == 0
        assert result.retrieval_strategy == RetrievalStrategy.HYBRID


# ═══════════════════════════════════════════════════════════════════════
# ISO TIMESTAMP VALIDATION
# ═══════════════════════════════════════════════════════════════════════


class TestDateFieldValidation:
    """Date fields (created_at, updated_at) must receive valid ISO 8601 timestamps."""

    def test_valid_iso_timestamp_accepted(self) -> None:
        """Standard ISO timestamp passes validation."""
        fc = FilterCondition(
            field=FilterableField.CREATED_AT,
            operator=FilterOperator.GREATER_THAN,
            value="2024-01-15T00:00:00Z",
        )
        assert fc.value == "2024-01-15T00:00:00Z"

    def test_valid_iso_with_timezone_offset(self) -> None:
        """ISO timestamp with timezone offset passes."""
        fc = FilterCondition(
            field=FilterableField.UPDATED_AT,
            operator=FilterOperator.LESS_THAN,
            value="2024-06-01T12:30:00+05:30",
        )
        assert fc.value == "2024-06-01T12:30:00+05:30"

    def test_valid_iso_without_timezone(self) -> None:
        """Naive ISO timestamp (no timezone) passes."""
        fc = FilterCondition(
            field=FilterableField.CREATED_AT,
            operator=FilterOperator.EQUALS,
            value="2024-01-15T00:00:00",
        )
        assert fc.value == "2024-01-15T00:00:00"

    def test_invalid_date_string_rejected(self) -> None:
        """Non-date string fails validation with clear error message."""
        with pytest.raises(ValidationError, match="ISO 8601"):
            FilterCondition(
                field=FilterableField.CREATED_AT,
                operator=FilterOperator.GREATER_THAN,
                value="not-a-date",
            )

    def test_date_only_accepted(self) -> None:
        """Date without time component is valid ISO 8601."""
        fc = FilterCondition(
            field=FilterableField.CREATED_AT,
            operator=FilterOperator.EQUALS,
            value="2024-01-15",
        )
        assert fc.value == "2024-01-15"

    def test_impossible_date_rejected(self) -> None:
        """Month 13 fails."""
        with pytest.raises(ValidationError, match="ISO 8601"):
            FilterCondition(
                field=FilterableField.CREATED_AT,
                operator=FilterOperator.GREATER_THAN,
                value="2024-13-01T00:00:00",
            )

    def test_text_field_not_validated_as_date(self) -> None:
        """Non-date fields don't get ISO validation."""
        fc = FilterCondition(
            field=FilterableField.NAME,
            operator=FilterOperator.EQUALS,
            value="anything goes here",
        )
        assert fc.value == "anything goes here"
