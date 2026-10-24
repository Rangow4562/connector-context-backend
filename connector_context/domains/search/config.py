"""Configuration for search module."""

from enum import Enum

from connector_context.adapters.llm.registry import MODEL_REGISTRY, LLMModel, LLMProvider
from connector_context.adapters.tokenizer.registry import TokenizerEncoding, TokenizerType
from connector_context.core.config import settings

_DEFAULT_LLM_FALLBACK_CHAIN: list[tuple[LLMProvider, LLMModel]] = [
    (LLMProvider.TOGETHER, LLMModel.ZAI_GLM_5),
    (LLMProvider.ANTHROPIC, LLMModel.CLAUDE_SONNET_4_6),
]

# Value → enum lookup tables built once at import time. Dict insertion order
# matches enum declaration order, which we surface in error messages.
_VALID_PROVIDERS: dict[str, LLMProvider] = {p.value: p for p in LLMProvider}
_VALID_MODELS: dict[str, LLMModel] = {m.value: m for m in LLMModel}


def parse_llm_fallback_chain(raw: str | None) -> list[tuple[LLMProvider, LLMModel]]:
    """Parse the LLM_FALLBACK_CHAIN env var.

    Format: comma-separated ``provider:model`` pairs using the enum ``value``
    strings from ``connector_context.adapters.llm.registry``. When ``raw`` is None or
    empty, returns the in-code default chain.

    Raises ValueError at import time (startup) on unknown provider or model names,
    listing the accepted values so deployers can fix the misconfiguration fast.
    """
    if not raw or not raw.strip():
        return list(_DEFAULT_LLM_FALLBACK_CHAIN)

    parsed: list[tuple[LLMProvider, LLMModel]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise ValueError(
                f"Invalid LLM_FALLBACK_CHAIN entry {entry!r}: expected 'provider:model'."
            )
        provider_raw, model_raw = entry.split(":", 1)
        provider_raw = provider_raw.strip()
        model_raw = model_raw.strip()

        if provider_raw not in _VALID_PROVIDERS:
            raise ValueError(
                f"Unknown provider {provider_raw!r} in LLM_FALLBACK_CHAIN. "
                f"Accepted: {list(_VALID_PROVIDERS)}."
            )
        if model_raw not in _VALID_MODELS:
            raise ValueError(
                f"Unknown model {model_raw!r} in LLM_FALLBACK_CHAIN. "
                f"Accepted: {list(_VALID_MODELS)}."
            )
        provider = _VALID_PROVIDERS[provider_raw]
        model = _VALID_MODELS[model_raw]
        provider_models = MODEL_REGISTRY.get(provider, {})
        if model not in provider_models:
            raise ValueError(
                f"Model {model_raw!r} not available for provider {provider_raw!r}. "
                f"Available: {[m.value for m in provider_models]}."
            )
        parsed.append((provider, model))

    if not parsed:
        return list(_DEFAULT_LLM_FALLBACK_CHAIN)
    return parsed


class DatabaseImpl(str, Enum):
    """Supported database implementations."""

    POSTGRESQL = "postgresql"


# --- Vector Database ---


class VectorDBProvider(str, Enum):
    """Supported vector database providers."""

    VESPA = "vespa"


# --- Config ---


class SearchConfig:
    """Search module configuration."""

    # Database
    DATABASE_IMPL = DatabaseImpl.POSTGRESQL

    # LLM fallback chain — ordered list of (provider, model) pairs.
    # Tried in sequence: the first provider that is available (has an API key
    # configured) and responds successfully handles the request. Subsequent
    # providers are only tried when the previous one fails.
    #
    # Deployers can override via the LLM_FALLBACK_CHAIN env var
    # (format: "provider:model,provider:model"). Unset → use the default below.
    # Evaluated once at class-definition time. Tests that need to vary this must
    # call parse_llm_fallback_chain directly or reload the module — monkey-
    # patching settings.LLM_FALLBACK_CHAIN after import has no effect here.
    LLM_FALLBACK_CHAIN: list[tuple[LLMProvider, LLMModel]] = parse_llm_fallback_chain(
        settings.LLM_FALLBACK_CHAIN
    )

    # Tokenizer
    # Note: Must be compatible with the chosen LLM model (validated at startup)
    TOKENIZER_TYPE = TokenizerType.TIKTOKEN
    TOKENIZER_ENCODING = TokenizerEncoding.O200K_HARMONY

    # Vector database
    VECTOR_DB_PROVIDER = VectorDBProvider.VESPA

    # Agent loop
    MAX_ITERATIONS = 15  # tighter budget — agent pipelines multiple tool calls per iteration
    AGENT_LLM_MAX_RETRIES = 3
    AGENT_LLM_RETRY_DELAY = 2.0  # seconds, initial delay for exponential backoff
    STAGNATION_THRESHOLD = 4  # iterations without new marks before nudging
    READ_SURROUNDING_CHUNKS = 2  # ±N chunks around matched chunk in read tool

    # Context management
    MIN_USEFUL_BUDGET_TOKENS = 5_000  # safety valve threshold (~50 summaries or 2-3 full reads)
    NON_THINKING_OUTPUT_RESERVE = 10_000  # tokens reserved for non-thinking model output


config = SearchConfig()
