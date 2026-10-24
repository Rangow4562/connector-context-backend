"""Shared prompt loading for the search domain.

Used by both classic and agentic tiers to build system prompts
from the shared connector_context_overview.md + tier-specific task prompts.
"""

from __future__ import annotations

import functools
from pathlib import Path

from connector_context.domains.search.types.metadata import CollectionMetadata


@functools.cache
def _load_overview() -> str:
    """Load and cache the shared connector_context overview prompt."""
    return (Path(__file__).parent / "context" / "connector_context_overview.md").read_text()


def build_system_prompt(
    overview: str,
    task: str,
    metadata: CollectionMetadata,
    **replacements: object,
) -> str:
    """Assemble system prompt from overview + task + metadata.

    Applies any template replacements (e.g., {max_iterations}) to the task text.
    """
    for key, value in replacements.items():
        task = task.replace(f"{{{key}}}", str(value))
    return (
        f"# Connector Context Overview\n\n{overview}\n\n"
        f"---\n\n{task}\n\n"
        f"---\n\n## Collection Metadata\n\n{metadata.to_md()}"
    )
