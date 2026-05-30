"""Exceptions for the search domain."""

from __future__ import annotations


class SearchError(Exception):
    """Base exception for the search domain."""


class FederatedSearchError(SearchError):
    """One or more federated sources failed during search.

    Contains per-source error details for debugging.
    """

    def __init__(self, source_errors: list[tuple[str, BaseException]]) -> None:
        """Initialize with per-source error details."""
        self.source_errors = source_errors
        summary = "; ".join(f"{name}: {err}" for name, err in source_errors)
        super().__init__(f"Federated search failed: {summary}")
