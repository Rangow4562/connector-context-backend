"""Container Factory.

All construction logic lives here. The factory reads settings and builds
the container with environment-appropriate implementations.

Design principles:
- Single place for all wiring decisions
- Environment-aware: local vs dev vs prd
- Fail fast: broken wiring crashes at startup, not at 3am
- Testable: can unit test factory logic with mock settings
"""

from typing import Optional

from prometheus_client import CollectorRegistry

from connector_context.adapters.analytics.posthog import PostHogTracker
from connector_context.adapters.analytics.subscriber import AnalyticsEventSubscriber
from connector_context.adapters.circuit_breaker import InMemoryCircuitBreaker
from connector_context.adapters.encryption.fernet import FernetCredentialEncryptor
from connector_context.adapters.event_bus.in_memory import InMemoryEventBus
from connector_context.adapters.health import PostgresHealthProbe, RedisHealthProbe, TemporalHealthProbe
from connector_context.adapters.llm.anthropic import AnthropicLLM
from connector_context.adapters.llm.cerebras import CerebrasLLM
from connector_context.adapters.llm.fallback import FallbackChainLLM
from connector_context.adapters.llm.gemini import GeminiLLM
from connector_context.adapters.llm.groq import GroqLLM
from connector_context.adapters.llm.mistral import MistralLLM
from connector_context.adapters.llm.registry import (
    PROVIDER_API_KEY_SETTINGS,
    LLMProvider,
)
from connector_context.adapters.llm.registry import (
    get_model_spec as get_llm_model_spec,
)
from connector_context.adapters.llm.together import TogetherLLM
from connector_context.adapters.llm.unavailable import UnavailableLLM
from connector_context.adapters.metrics import (
    PrometheusAgenticSearchMetrics,
    PrometheusDbPoolMetrics,
    PrometheusHttpMetrics,
    PrometheusMetricsRenderer,
)
from connector_context.adapters.pubsub.redis import RedisPubSub
from connector_context.adapters.reranker.cohere import CohereReranker
from connector_context.adapters.tokenizer.registry import get_model_spec as get_tokenizer_spec
from connector_context.adapters.tokenizer.tiktoken import TiktokenTokenizer
from connector_context.adapters.webhooks.endpoint_verifier import HttpEndpointVerifier
from connector_context.adapters.webhooks.svix import SvixAdapter
from connector_context.core.config import Settings
from connector_context.core.container.container import Container
from connector_context.core.health.service import HealthService
from connector_context.core.logging import logger
from connector_context.core.metrics_service import PrometheusMetricsService
from connector_context.core.protocols import CircuitBreaker, PubSub
from connector_context.core.protocols.event_bus import EventBus
from connector_context.core.protocols.identity import IdentityProvider
from connector_context.core.protocols.payment import PaymentGatewayProtocol
from connector_context.core.protocols.webhooks import WebhookPublisher
from connector_context.core.redis_client import redis_client
from connector_context.db.session import health_check_engine
from connector_context.domains.access_control.broker import AccessBroker
from connector_context.domains.access_control.repository import AccessControlMembershipRepository
from connector_context.domains.arf.service import ArfService
from connector_context.domains.auth_provider.registry import AuthProviderRegistry
from connector_context.domains.auth_provider.service import AuthProviderService
from connector_context.domains.browse_tree.repository import NodeSelectionRepository
from connector_context.domains.browse_tree.service import BrowseTreeService
from connector_context.domains.collections.repository import CollectionRepository
from connector_context.domains.collections.service import CollectionService
from connector_context.domains.collections.vector_db_deployment_metadata_repository import (
    VectorDbDeploymentMetadataRepository,
)
from connector_context.domains.connections.repository import ConnectionRepository
from connector_context.domains.converters.registry import ConverterRegistry
from connector_context.domains.credentials.repository import IntegrationCredentialRepository
from connector_context.domains.credentials.service import IntegrationCredentialService
from connector_context.domains.embedders.config import (
    DENSE_EMBEDDER,
    EMBEDDING_DIMENSIONS,
    SPARSE_EMBEDDER,
    validate_embedding_config_sync,
)
from connector_context.domains.embedders.protocols import DenseEmbedderProtocol, SparseEmbedderProtocol
from connector_context.domains.embedders.registry import DenseEmbedderRegistry, SparseEmbedderRegistry
from connector_context.domains.embedders.sparse.fastembed import (
    FastEmbedSparseEmbedder as DomainFastEmbedSparseEmbedder,
)
from connector_context.domains.entities.entity_count_repository import EntityCountRepository
from connector_context.domains.entities.entity_repository import EntityRepository
from connector_context.domains.entities.registry import EntityDefinitionRegistry
from connector_context.domains.oauth.callback_service import OAuthCallbackService
from connector_context.domains.oauth.flow_service import OAuthFlowService
from connector_context.domains.oauth.oauth1_service import OAuth1Service
from connector_context.domains.oauth.oauth2_service import OAuth2Service
from connector_context.domains.oauth.repository import (
    OAuthInitSessionRepository,
    OAuthRedirectSessionRepository,
)
from connector_context.domains.ocr.docling import DoclingOcrAdapter
from connector_context.domains.ocr.fallback import FallbackOcrProvider
from connector_context.domains.ocr.mistral.converter import MistralOCR
from connector_context.domains.ocr.protocols import OcrProvider
from connector_context.domains.organizations.protocols import UserOrganizationRepositoryProtocol
from connector_context.domains.organizations.repository import OrganizationRepository as OrgRepo
from connector_context.domains.organizations.repository import UserOrganizationRepository
from connector_context.domains.search.adapters.vector_db.filter_translator import FilterTranslator
from connector_context.domains.search.adapters.vector_db.vespa_client import VespaVectorDB
from connector_context.domains.search.agentic.service import AgenticSearchService
from connector_context.domains.search.agentic.subscribers.stream_relay import SearchStreamRelay
from connector_context.domains.search.builders.collection_metadata import CollectionMetadataBuilder
from connector_context.domains.search.classic.service import ClassicSearchService
from connector_context.domains.search.config import SearchConfig
from connector_context.domains.search.executor import SearchPlanExecutor
from connector_context.domains.search.instant.service import InstantSearchService
from connector_context.domains.source_connections.create import SourceConnectionCreationService
from connector_context.domains.source_connections.delete import SourceConnectionDeletionService
from connector_context.domains.source_connections.repository import SourceConnectionRepository
from connector_context.domains.source_connections.response import ResponseBuilder
from connector_context.domains.source_connections.service import SourceConnectionService
from connector_context.domains.source_connections.update import SourceConnectionUpdateService
from connector_context.domains.sources.lifecycle import SourceLifecycleService
from connector_context.domains.sources.registry import SourceRegistry
from connector_context.domains.sources.service import SourceService
from connector_context.domains.sources.validation import SourceValidationService
from connector_context.domains.storage.sync_file_manager import SyncFileManager
from connector_context.domains.sync_pipeline.factory import SyncFactory
from connector_context.domains.sync_pipeline.processors.chunk_embed import ChunkEmbedProcessor
from connector_context.domains.sync_pipeline.subscribers.progress_relay import SyncProgressRelay
from connector_context.domains.syncs.cursors.repository import SyncCursorRepository
from connector_context.domains.syncs.cursors.service import SyncCursorService
from connector_context.domains.syncs.jobs.repository import SyncJobRepository
from connector_context.domains.syncs.jobs.service import SyncJobService
from connector_context.domains.syncs.jobs.state_machine import SyncJobStateMachine
from connector_context.domains.syncs.repository import SyncRepository
from connector_context.domains.syncs.service import SyncService
from connector_context.domains.syncs.state_machine import SyncStateMachine
from connector_context.domains.temporal.client import get_cached_client as get_cached_temporal_client
from connector_context.domains.temporal.schedule_service import TemporalScheduleService
from connector_context.domains.temporal.service import TemporalWorkflowService
from connector_context.domains.usage.ledger import UsageLedger
from connector_context.domains.usage.limit_checker import UsageLimitChecker, UsageLimitCheckerProtocol
from connector_context.domains.usage.protocols import UsageLedgerProtocol
from connector_context.domains.usage.repository import UsageRepository
from connector_context.domains.usage.subscribers.billing_listener import UsageBillingListener
from connector_context.domains.webhooks.service import WebhookServiceImpl
from connector_context.domains.webhooks.subscribers import WebhookEventSubscriber
from connector_context.platform.auth.settings import integration_settings


def create_container(settings: Settings) -> Container:
    """Build container with environment-appropriate implementations.

    This is the single source of truth for dependency wiring. It reads
    the settings and decides which adapter implementation to use for
    each protocol.

    Args:
        settings: Application settings (from core/config.py)

    Returns:
        Fully constructed Container ready for use

    Example:
        # In main.py or worker.py
        from connector_context.core.config import settings
        from connector_context.core.container import create_container

        container = create_container(settings)
    """
    # -----------------------------------------------------------------
    # Webhooks (Svix adapter)
    # SvixAdapter implements both WebhookPublisher and WebhookAdmin
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # Context cache (Redis-backed, used by deps.py hot path)
    # -----------------------------------------------------------------
    from connector_context.adapters.cache.redis import RedisContextCache

    context_cache = RedisContextCache(redis_client=redis_client.client)

    # -----------------------------------------------------------------
    # Rate limiter (Redis-backed or Null for local dev / disabled)
    # -----------------------------------------------------------------
    rate_limiter = _create_rate_limiter(settings)

    svix_adapter = SvixAdapter()

    # -----------------------------------------------------------------
    # Endpoint verification (plain HTTP, not Svix)
    # -----------------------------------------------------------------
    endpoint_verifier = HttpEndpointVerifier()

    # -----------------------------------------------------------------
    # Billing services
    # -----------------------------------------------------------------
    billing_services = _create_billing_services(settings)

    # -----------------------------------------------------------------
    # Identity provider (Auth0 / Null)
    # -----------------------------------------------------------------
    identity_provider = _create_identity_provider(settings)

    # -----------------------------------------------------------------
    # Organization repositories
    # -----------------------------------------------------------------
    user_org_repo = UserOrganizationRepository()

    # Source Service + Source Lifecycle Service
    # Auth provider registry is built first, then passed to the source
    # registry so it can compute supported_auth_providers per source.
    # Both services share the same source_registry instance.
    # -----------------------------------------------------------------
    source_deps = _create_source_services(settings)

    # -----------------------------------------------------------------
    # Usage domain — checker (read) + ledger (write), both singletons
    # -----------------------------------------------------------------
    usage_checker = _create_usage_checker(settings, billing_services, source_deps, user_org_repo)
    usage_ledger = _create_usage_ledger(settings, billing_services)
    # -----------------------------------------------------------------
    # Webhook service (composes admin + verifier for API layer)
    # -----------------------------------------------------------------
    webhook_service = WebhookServiceImpl(
        webhook_admin=svix_adapter,
        endpoint_verifier=endpoint_verifier,
        verify_endpoints=settings.WEBHOOK_VERIFY_ENDPOINTS,
    )

    # -----------------------------------------------------------------
    # PubSub (realtime message transport — Redis adapter)
    # -----------------------------------------------------------------

    pubsub = RedisPubSub()

    # -----------------------------------------------------------------
    # Circuit Breaker + OCR
    # Shared circuit breaker tracks provider health across the process.
    # FallbackOcrProvider tries providers in order, skipping tripped ones.
    # -----------------------------------------------------------------
    circuit_breaker = _create_circuit_breaker()
    ocr_provider = _create_ocr_provider(circuit_breaker, settings)

    # -----------------------------------------------------------------
    # Health service
    # Owns shutdown flag and orchestrates readiness probes.
    # -----------------------------------------------------------------
    health = _create_health_service(settings)

    # -----------------------------------------------------------------
    # Metrics (Prometheus adapters, shared registry, wrapped in service)
    # -----------------------------------------------------------------
    metrics = _create_metrics_service(settings)

    event_bus = _create_event_bus(
        webhook_publisher=svix_adapter,
        settings=settings,
        pubsub=pubsub,
        usage_ledger=usage_ledger,
        context_cache=context_cache,
    )

    # -----------------------------------------------------------------
    # Organization domain service
    # -----------------------------------------------------------------
    org_service = _create_organization_service(
        identity_provider=identity_provider,
        payment_gateway=billing_services["payment_gateway"],
        billing_ops=billing_services.get("billing_ops"),
        billing_repo=billing_services["billing_repo"],
        webhook_admin=svix_adapter,
        event_bus=event_bus,
        user_org_repo=user_org_repo,
        context_cache=context_cache,
    )

    # -----------------------------------------------------------------
    # Email service
    # -----------------------------------------------------------------
    email_service = _create_email_service(settings)

    # -----------------------------------------------------------------
    # User domain service
    # -----------------------------------------------------------------
    user_service = _create_user_service(
        org_service=org_service,
        user_org_repo=user_org_repo,
        email_service=email_service,
    )

    # -----------------------------------------------------------------
    # Sync domain services
    # Repos come from source_deps; services are built here.
    # -----------------------------------------------------------------

    sync_deps = _create_sync_services(
        event_bus=event_bus,
        sc_repo=source_deps["sc_repo"],
        collection_repo=source_deps["collection_repo"],
        conn_repo=source_deps["conn_repo"],
        cred_repo=source_deps["cred_repo"],
        source_registry=source_deps["source_registry"],
        sync_repo=source_deps["sync_repo"],
        sync_cursor_repo=source_deps["sync_cursor_repo"],
        sync_job_repo=source_deps["sync_job_repo"],
        auth_provider_registry=source_deps["auth_provider_registry"],
    )

    # -----------------------------------------------------------------
    # Shared services (needed by both sync and source_connection domains)
    # Built here, before embedders, to keep deps available below.
    # -----------------------------------------------------------------
    source_validation = SourceValidationService(
        source_registry=source_deps["source_registry"],
    )
    encryptor = FernetCredentialEncryptor(settings.ENCRYPTION_KEY)
    init_session_repo = OAuthInitSessionRepository()

    oauth_flow_svc = OAuthFlowService(
        oauth2_service=source_deps["oauth2_service"],
        oauth1_service=source_deps["oauth1_service"],
        integration_settings=integration_settings,
        init_session_repo=init_session_repo,
        redirect_session_repo=source_deps["redirect_session_repo"],
        settings=settings,
    )

    auth_provider_service = AuthProviderService(
        auth_provider_registry=source_deps["auth_provider_registry"],
        connection_repo=source_deps["conn_repo"],
        credential_repo=source_deps["cred_repo"],
    )

    # -----------------------------------------------------------------
    # Embedder registries + instances (deployment-wide singletons)
    # -----------------------------------------------------------------
    dense_embedder_registry = DenseEmbedderRegistry()
    dense_embedder_registry.build()
    sparse_embedder_registry = SparseEmbedderRegistry()
    sparse_embedder_registry.build()

    # Validate env vars, registry lookups, dimensions, and credentials
    # before attempting to construct embedder instances.
    # DB reconciliation happens later in main.py lifespan.
    validate_embedding_config_sync(
        dense_registry=dense_embedder_registry,
        sparse_registry=sparse_embedder_registry,
    )

    dense_embedder = _create_dense_embedder(settings, dense_embedder_registry)
    sparse_embedder = _create_sparse_embedder(sparse_embedder_registry)

    # -----------------------------------------------------------------
    # Access control membership repo + chunk embed processor
    # -----------------------------------------------------------------
    acl_membership_repo = AccessControlMembershipRepository()
    access_broker = AccessBroker(acl_repo=acl_membership_repo)
    converter_registry = ConverterRegistry(ocr_provider=ocr_provider)
    chunk_embed_processor = ChunkEmbedProcessor(
        converter_registry=converter_registry,
        dense_embedder=dense_embedder,
        sparse_embedder=sparse_embedder,
    )

    # Storage domain
    # -----------------------------------------------------------------
    storage_backend = _create_storage_backend(settings)
    sync_file_manager = SyncFileManager(backend=storage_backend)

    # ARF domain service (raw entity capture / replay)
    # -----------------------------------------------------------------
    arf_service = ArfService(storage=storage_backend)

    # Node selection repo (shared by sync factory + browse tree service)
    node_selection_repo = NodeSelectionRepository()

    # -----------------------------------------------------------------
    # Sync factory + service
    # -----------------------------------------------------------------
    sync_factory = SyncFactory(
        # Repositories
        sc_repo=source_deps["sc_repo"],
        entity_repo=sync_deps["entity_repo"],
        entity_count_repo=sync_deps["entity_count_repo"],
        acl_repo=acl_membership_repo,
        selection_repo=node_selection_repo,
        # Registries
        entity_definition_registry=source_deps["entity_definition_registry"],
        source_registry=source_deps["source_registry"],
        # Services
        source_lifecycle_service=source_deps["source_lifecycle_service"],
        sync_state_machine=sync_deps["sync_state_machine"],
        sync_cursor_service=source_deps["sync_cursor_service"],
        processor=chunk_embed_processor,
        arf_service=arf_service,
        # Infrastructure
        event_bus=event_bus,
        usage_checker=usage_checker,
        usage_ledger=usage_ledger,
        storage_backend=storage_backend,
        state_machine=sync_deps["sync_job_state_machine"],
    )

    sync_service = SyncService(
        sync_repo=source_deps["sync_repo"],
        sync_job_repo=source_deps["sync_job_repo"],
        sync_cursor_repo=sync_deps["sync_cursor_repo"],
        state_machine=sync_deps["sync_state_machine"],
        job_state_machine=sync_deps["sync_job_state_machine"],
        temporal_workflow_service=sync_deps["temporal_workflow_service"],
        temporal_schedule_service=sync_deps["temporal_schedule_service"],
        sync_factory=sync_factory,
    )

    # -----------------------------------------------------------------
    # Source connection sub-services (need sync_service)
    # -----------------------------------------------------------------
    deletion_service = SourceConnectionDeletionService(
        sc_repo=source_deps["sc_repo"],
        collection_repo=source_deps["collection_repo"],
        response_builder=sync_deps["response_builder"],
        sync_service=sync_service,
    )
    update_service = SourceConnectionUpdateService(
        sc_repo=source_deps["sc_repo"],
        collection_repo=source_deps["collection_repo"],
        connection_repo=source_deps["conn_repo"],
        cred_repo=source_deps["cred_repo"],
        sync_repo=source_deps["sync_repo"],
        sync_service=sync_service,
        source_service=source_deps["source_service"],
        source_registry=source_deps["source_registry"],
        source_validation=source_validation,
        credential_encryptor=encryptor,
        response_builder=sync_deps["response_builder"],
        temporal_schedule_service=sync_deps["temporal_schedule_service"],
    )
    create_service = SourceConnectionCreationService(
        sc_repo=source_deps["sc_repo"],
        collection_repo=source_deps["collection_repo"],
        connection_repo=source_deps["conn_repo"],
        credential_service=source_deps["credential_service"],
        source_registry=source_deps["source_registry"],
        source_validation=source_validation,
        source_lifecycle=source_deps["source_lifecycle_service"],
        sync_service=sync_service,
        response_builder=sync_deps["response_builder"],
        oauth_flow_service=oauth_flow_svc,
        temporal_workflow_service=sync_deps["temporal_workflow_service"],
        event_bus=event_bus,
        auth_provider_service=auth_provider_service,
        sync_job_repo=source_deps["sync_job_repo"],
    )
    source_connection_service = SourceConnectionService(
        sc_repo=source_deps["sc_repo"],
        collection_repo=source_deps["collection_repo"],
        connection_repo=source_deps["conn_repo"],
        redirect_session_repo=source_deps["redirect_session_repo"],
        source_registry=source_deps["source_registry"],
        auth_provider_registry=source_deps["auth_provider_registry"],
        response_builder=sync_deps["response_builder"],
        sync_service=sync_service,
        event_bus=event_bus,
        create_service=create_service,
        update_service=update_service,
        deletion_service=deletion_service,
    )

    # -----------------------------------------------------------------
    # Search domain services (LLM, tokenizer, reranker, metadata builder, per-tier)
    # -----------------------------------------------------------------
    search_deps = _create_search_services(
        settings=settings,
        circuit_breaker=circuit_breaker,
        dense_embedder=dense_embedder,
        sparse_embedder=sparse_embedder,
        collection_repo=source_deps["collection_repo"],
        sc_repo=source_deps["sc_repo"],
        source_registry=source_deps["source_registry"],
        entity_definition_registry=source_deps["entity_definition_registry"],
        event_bus=event_bus,
        source_lifecycle=source_deps["source_lifecycle_service"],
        access_broker=access_broker,
    )

    # -----------------------------------------------------------------
    # Collection service
    # -----------------------------------------------------------------
    collection_service = CollectionService(
        collection_repo=source_deps["collection_repo"],
        sc_repo=source_deps["sc_repo"],
        sync_service=sync_service,
        event_bus=event_bus,
        settings=settings,
        deployment_metadata_repo=VectorDbDeploymentMetadataRepository(),
        dense_registry=dense_embedder_registry,
    )

    # OAuth callback service
    # -----------------------------------------------------------------

    oauth_callback_svc = OAuthCallbackService(
        oauth_flow_service=oauth_flow_svc,
        init_session_repo=init_session_repo,
        response_builder=sync_deps["response_builder"],
        source_registry=source_deps["source_registry"],
        source_lifecycle=source_deps["source_lifecycle_service"],
        sync_service=sync_service,
        temporal_workflow_service=sync_deps["temporal_workflow_service"],
        event_bus=event_bus,
        organization_repo=OrgRepo(),
        sc_repo=source_deps["sc_repo"],
        credential_repo=source_deps["cred_repo"],
        connection_repo=source_deps["conn_repo"],
        collection_repo=source_deps["collection_repo"],
        sync_repo=source_deps["sync_repo"],
        sync_job_repo=source_deps["sync_job_repo"],
        credential_encryptor=encryptor,
    )

    # -----------------------------------------------------------------
    # Connect domain service (after oauth_callback_svc for DI)
    # -----------------------------------------------------------------
    from connector_context.domains.connect.service import ConnectService
    from connector_context.domains.organizations.repository import OrganizationRepository as ConnectOrgRepo

    connect_service = ConnectService(
        source_connection_service=source_connection_service,
        source_service=source_deps["source_service"],
        org_repo=ConnectOrgRepo(),
        collection_repo=source_deps["collection_repo"],
        sync_job_repo=source_deps["sync_job_repo"],
        oauth_callback_service=oauth_callback_svc,
    )

    # -----------------------------------------------------------------
    # Browse tree service
    # -----------------------------------------------------------------
    browse_tree_service = BrowseTreeService(
        selection_repo=node_selection_repo,
        sc_repo=source_deps["sc_repo"],
        source_lifecycle=source_deps["source_lifecycle_service"],
        sync_repo=source_deps["sync_repo"],
        sync_job_repo=source_deps["sync_job_repo"],
        collection_repo=source_deps["collection_repo"],
        conn_repo=source_deps["conn_repo"],
        temporal_workflow_service=sync_deps["temporal_workflow_service"],
    )

    return Container(
        storage_backend=storage_backend,
        sync_file_manager=sync_file_manager,
        arf_service=arf_service,
        context_cache=context_cache,
        rate_limiter=rate_limiter,
        billing_service=billing_services["billing_service"],
        billing_webhook=billing_services["billing_webhook"],
        collection_service=collection_service,
        browse_tree_service=browse_tree_service,
        selection_repo=node_selection_repo,
        health=health,
        event_bus=event_bus,
        pubsub=pubsub,
        webhook_publisher=svix_adapter,
        webhook_admin=svix_adapter,
        circuit_breaker=circuit_breaker,
        dense_embedder_registry=dense_embedder_registry,
        sparse_embedder_registry=sparse_embedder_registry,
        dense_embedder=dense_embedder,
        sparse_embedder=sparse_embedder,
        ocr_provider=ocr_provider,
        metrics=metrics,
        source_service=source_deps["source_service"],
        source_registry=source_deps["source_registry"],
        auth_provider_registry=source_deps["auth_provider_registry"],
        auth_provider_service=auth_provider_service,
        entity_definition_registry=source_deps["entity_definition_registry"],
        sc_repo=source_deps["sc_repo"],
        collection_repo=source_deps["collection_repo"],
        conn_repo=source_deps["conn_repo"],
        cred_repo=source_deps["cred_repo"],
        credential_service=source_deps["credential_service"],
        user_org_repo=user_org_repo,
        oauth1_service=source_deps["oauth1_service"],
        oauth2_service=source_deps["oauth2_service"],
        redirect_session_repo=source_deps["redirect_session_repo"],
        source_connection_service=source_connection_service,
        connect_service=connect_service,
        oauth_flow_service=oauth_flow_svc,
        oauth_callback_service=oauth_callback_svc,
        init_session_repo=init_session_repo,
        source_lifecycle_service=source_deps["source_lifecycle_service"],
        endpoint_verifier=endpoint_verifier,
        webhook_service=webhook_service,
        response_builder=sync_deps["response_builder"],
        sync_repo=source_deps["sync_repo"],
        sync_cursor_repo=source_deps["sync_cursor_repo"],
        sync_cursor_service=source_deps["sync_cursor_service"],
        sync_job_repo=source_deps["sync_job_repo"],
        payment_gateway=billing_services["payment_gateway"],
        sync_job_service=sync_deps["sync_job_service"],
        sync_job_state_machine=sync_deps["sync_job_state_machine"],
        sync_service=sync_service,
        sync_factory=sync_factory,
        entity_repo=sync_deps["entity_repo"],
        access_broker=access_broker,
        converter_registry=converter_registry,
        temporal_workflow_service=sync_deps["temporal_workflow_service"],
        temporal_schedule_service=sync_deps["temporal_schedule_service"],
        usage_checker=usage_checker,
        usage_ledger=usage_ledger,
        identity_provider=identity_provider,
        organization_service=org_service,
        user_service=user_service,
        email_service=email_service,
        instant_search=search_deps["instant_search"],
        classic_search=search_deps["classic_search"],
        agentic_search=search_deps["agentic_search"],
    )


# ---------------------------------------------------------------------------
# Private factory functions for each dependency
# ---------------------------------------------------------------------------


def _create_health_service(settings: Settings) -> HealthService:
    """Create the health service with infrastructure probes.

    All known probes (postgres, redis, temporal) are always registered.
    The critical-vs-informational split comes from
    ``settings.health_critical_probes``.
    """
    critical_names = settings.health_critical_probes

    probes = {
        "postgres": PostgresHealthProbe(health_check_engine),
        "redis": RedisHealthProbe(redis_client.client),
        "temporal": TemporalHealthProbe(get_cached_temporal_client),
    }

    unknown = critical_names - probes.keys()
    if unknown:
        logger.warning(
            "HEALTH_CRITICAL_PROBES references unknown probes: %s",
            ", ".join(sorted(unknown)),
        )

    critical = [p for name, p in probes.items() if name in critical_names]
    informational = [p for name, p in probes.items() if name not in critical_names]

    return HealthService(
        critical=critical,
        informational=informational,
        timeout=settings.HEALTH_CHECK_TIMEOUT,
    )


def _create_metrics_service(settings: Settings) -> PrometheusMetricsService:
    """Build the PrometheusMetricsService with Prometheus adapters and a shared registry."""
    registry = CollectorRegistry()
    return PrometheusMetricsService(
        http=PrometheusHttpMetrics(registry=registry),
        agentic_search=PrometheusAgenticSearchMetrics(registry=registry),
        db_pool=PrometheusDbPoolMetrics(
            registry=registry,
            max_overflow=settings.db_pool_max_overflow,
        ),
        renderer=PrometheusMetricsRenderer(registry=registry),
        host=settings.METRICS_HOST,
        port=settings.METRICS_PORT,
    )


def _create_event_bus(
    webhook_publisher: WebhookPublisher,
    settings: Settings,
    pubsub: PubSub,
    usage_ledger: UsageLedgerProtocol,
    context_cache=None,
) -> EventBus:
    """Create event bus with subscribers wired up.

    The event bus fans out domain events to:
    - WebhookEventSubscriber: External webhooks via Svix (all events)
    - AnalyticsEventSubscriber: PostHog analytics tracking
    - SyncProgressRelay: Relays entity batch events to Redis PubSub (entity.*)
    - UsageBillingListener: Accumulates usage from entity/query/sync/
      source_connection events

    Returns:
        EventBus
    """
    bus = InMemoryEventBus()

    # WebhookEventSubscriber subscribes to * — all domain events
    # Svix channel filtering handles per-endpoint event type matching
    webhook_subscriber = WebhookEventSubscriber(webhook_publisher)
    for pattern in webhook_subscriber.EVENT_PATTERNS:
        bus.subscribe(pattern, webhook_subscriber.handle)

    # AnalyticsEventSubscriber — forwards domain events to PostHog
    tracker = PostHogTracker(settings)
    analytics_subscriber = AnalyticsEventSubscriber(tracker)
    for pattern in analytics_subscriber.EVENT_PATTERNS:
        bus.subscribe(pattern, analytics_subscriber.handle)

    # Sync progress relay (self-initializing from sync.running events)
    progress_relay = SyncProgressRelay(pubsub=pubsub)
    for pattern in progress_relay.EVENT_PATTERNS:
        bus.subscribe(pattern, progress_relay.handle)

    # UsageBillingListener — accumulates usage from entity/query/sync/
    # source_connection events
    usage_billing_listener = UsageBillingListener(ledger=usage_ledger)
    for pattern in usage_billing_listener.EVENT_PATTERNS:
        bus.subscribe(pattern, usage_billing_listener.handle)

    # SearchStreamRelay — bridges search events to PubSub for SSE streaming
    search_stream_relay = SearchStreamRelay(pubsub=pubsub)
    for pattern in search_stream_relay.EVENT_PATTERNS:
        bus.subscribe(pattern, search_stream_relay.handle)

    # DonkeNotificationSubscriber — best-effort signup notification
    from connector_context.domains.organizations.subscribers.donke_notification import (
        DonkeNotificationSubscriber,
    )

    donke_subscriber = DonkeNotificationSubscriber()
    for pattern in donke_subscriber.EVENT_PATTERNS:
        bus.subscribe(pattern, donke_subscriber.handle)

    return bus


def _create_circuit_breaker() -> CircuitBreaker:
    """Create the shared circuit breaker for provider failover.

    Uses a 120-second cooldown: after a provider fails, it is skipped
    for 2 minutes before being retried (half-open state).
    """
    return InMemoryCircuitBreaker(cooldown_seconds=120)


def _create_ocr_provider(
    circuit_breaker: CircuitBreaker, settings: Settings
) -> Optional[OcrProvider]:
    """Create OCR provider with fallback chain.

    Chain order: Mistral (cloud) -> Docling (local service, if configured).
    Docling is only added when DOCLING_BASE_URL is set.

    Returns None with a warning when no providers are available.
    """
    try:
        mistral_ocr = MistralOCR()
    except Exception as e:
        logger.error(f"Error creating Mistral OCR adapter: {e}")
        mistral_ocr = None

    providers = []
    if mistral_ocr:
        providers.append(("mistral-ocr", mistral_ocr))

    if settings.DOCLING_BASE_URL:
        try:
            docling_ocr = DoclingOcrAdapter(base_url=settings.DOCLING_BASE_URL)
            providers.append(("docling", docling_ocr))
        except Exception as e:
            logger.error(f"Error creating Docling OCR adapter: {e}")
            docling_ocr = None

    if not providers:
        logger.warning(
            "No OCR providers available — document processing will be disabled. "
            "Set MISTRAL_API_KEY or DOCLING_BASE_URL to enable OCR."
        )
        return None

    logger.info(f"Creating FallbackOcrProvider with {len(providers)} providers: {providers}")

    return FallbackOcrProvider(providers=providers, circuit_breaker=circuit_breaker)


def _create_dense_embedder(
    settings: Settings, registry: DenseEmbedderRegistry
) -> DenseEmbedderProtocol:
    """Create the deployment-wide dense embedder singleton.

    Uses the domain config constants (DENSE_EMBEDDER, EMBEDDING_DIMENSIONS)
    and the registry to look up the spec and construct the correct embedder.
    """
    from connector_context.domains.embedders.dense.gemini import GeminiDenseEmbedder
    from connector_context.domains.embedders.dense.local import LocalDenseEmbedder
    from connector_context.domains.embedders.dense.mistral import MistralDenseEmbedder
    from connector_context.domains.embedders.dense.openai import OpenAIDenseEmbedder

    spec = registry.get(DENSE_EMBEDDER)

    if spec.embedder_class_ref is GeminiDenseEmbedder:
        return GeminiDenseEmbedder(
            api_key=settings.GEMINI_API_KEY,
            model=spec.api_model_name,
            dimensions=EMBEDDING_DIMENSIONS,
        )

    if spec.embedder_class_ref is OpenAIDenseEmbedder:
        return OpenAIDenseEmbedder(
            api_key=settings.OPENAI_API_KEY,
            model=spec.api_model_name,
            dimensions=EMBEDDING_DIMENSIONS,
        )

    if spec.embedder_class_ref is MistralDenseEmbedder:
        return MistralDenseEmbedder(
            api_key=settings.MISTRAL_API_KEY,
            model=spec.api_model_name,
            dimensions=EMBEDDING_DIMENSIONS,
        )

    if spec.embedder_class_ref is LocalDenseEmbedder:
        return LocalDenseEmbedder(
            inference_url=settings.TEXT2VEC_INFERENCE_URL,
            dimensions=EMBEDDING_DIMENSIONS,
        )

    raise ValueError(f"Unknown dense embedder class: {spec.embedder_class_ref}")


def _create_sparse_embedder(registry: SparseEmbedderRegistry) -> SparseEmbedderProtocol:
    """Create the deployment-wide sparse embedder singleton.

    Uses the domain config constant (SPARSE_EMBEDDER) and the registry
    to look up the spec and construct the correct embedder.
    """
    spec = registry.get(SPARSE_EMBEDDER)

    return DomainFastEmbedSparseEmbedder(model=spec.api_model_name)


def _create_source_services(settings: Settings) -> dict:
    """Create source services, registries, repository adapters, and lifecycle service.

    Build order matters:
    1. Auth provider registry (no dependencies)
    2. Entity definition registry (no dependencies)
    3. Source registry (depends on both)
    4. Repository adapters (thin wrappers around crud singletons)
    5. OAuth2 service (with injected repos, encryptor, settings)
    6. SourceLifecycleService (depends on all of the above)
    """
    auth_provider_registry = AuthProviderRegistry()
    auth_provider_registry.build()

    entity_definition_registry = EntityDefinitionRegistry()
    entity_definition_registry.build()

    source_registry = SourceRegistry(auth_provider_registry, entity_definition_registry)
    source_registry.build()

    # Repository adapters
    sc_repo = SourceConnectionRepository(source_registry=source_registry)
    collection_repo = CollectionRepository(source_registry=source_registry, sc_repo=sc_repo)
    conn_repo = ConnectionRepository()
    cred_repo = IntegrationCredentialRepository()
    encryptor = FernetCredentialEncryptor(settings.ENCRYPTION_KEY)
    credential_service = IntegrationCredentialService(repo=cred_repo, encryptor=encryptor)
    sync_repo = SyncRepository()
    sync_cursor_repo = SyncCursorRepository()
    sync_job_repo = SyncJobRepository()
    sync_cursor_service = SyncCursorService()
    redirect_session_repo = OAuthRedirectSessionRepository()
    oauth1_svc = OAuth1Service()
    oauth2_svc = OAuth2Service(
        settings=settings,
        conn_repo=conn_repo,
        cred_repo=cred_repo,
        encryptor=encryptor,
        source_registry=source_registry,
    )

    source_service = SourceService(
        source_registry=source_registry,
        settings=settings,
    )
    source_lifecycle_service = SourceLifecycleService(
        source_registry=source_registry,
        auth_provider_registry=auth_provider_registry,
        sc_repo=sc_repo,
        conn_repo=conn_repo,
        credential_service=credential_service,
        oauth2_service=oauth2_svc,
    )

    return {
        "source_service": source_service,
        "source_registry": source_registry,
        "auth_provider_registry": auth_provider_registry,
        "entity_definition_registry": entity_definition_registry,
        "sc_repo": sc_repo,
        "collection_repo": collection_repo,
        "conn_repo": conn_repo,
        "cred_repo": cred_repo,
        "credential_service": credential_service,
        "oauth1_service": oauth1_svc,
        "oauth2_service": oauth2_svc,
        "redirect_session_repo": redirect_session_repo,
        "source_lifecycle_service": source_lifecycle_service,
        "sync_repo": sync_repo,
        "sync_cursor_repo": sync_cursor_repo,
        "sync_cursor_service": sync_cursor_service,
        "sync_job_repo": sync_job_repo,
    }


def _create_payment_gateway(settings: Settings) -> PaymentGatewayProtocol:
    """Create payment gateway: Stripe if enabled, otherwise a null implementation."""
    if settings.STRIPE_ENABLED:
        from connector_context.adapters.payment.stripe import StripePaymentGateway

        return StripePaymentGateway()

    from connector_context.adapters.payment.null import NullPaymentGateway

    return NullPaymentGateway()


def _create_billing_services(settings: Settings) -> dict:
    """Create billing service and webhook processor with shared dependencies."""
    from connector_context.domains.billing.operations import BillingOperations
    from connector_context.domains.billing.repository import (
        BillingPeriodRepository,
        OrganizationBillingRepository,
        WebhookEventRepository,
    )
    from connector_context.domains.billing.service import BillingService
    from connector_context.domains.billing.webhook_processor import BillingWebhookProcessor
    from connector_context.domains.organizations.repository import OrganizationRepository
    from connector_context.domains.usage.repository import UsageRepository

    payment_gateway = _create_payment_gateway(settings)
    billing_repo = OrganizationBillingRepository()
    period_repo = BillingPeriodRepository()
    org_repo = OrganizationRepository()
    usage_repo = UsageRepository()
    billing_ops = BillingOperations(
        billing_repo=billing_repo,
        period_repo=period_repo,
        usage_repo=usage_repo,
        payment_gateway=payment_gateway,
    )

    billing_service = BillingService(
        payment_gateway=payment_gateway,
        billing_repo=billing_repo,
        period_repo=period_repo,
        billing_ops=billing_ops,
        org_repo=org_repo,
    )
    webhook_event_repo = WebhookEventRepository()
    billing_webhook = BillingWebhookProcessor(
        payment_gateway=payment_gateway,
        billing_repo=billing_repo,
        period_repo=period_repo,
        billing_ops=billing_ops,
        org_repo=org_repo,
        webhook_event_repo=webhook_event_repo,
    )

    return {
        "billing_service": billing_service,
        "billing_webhook": billing_webhook,
        "billing_ops": billing_ops,
        "payment_gateway": payment_gateway,
        "billing_repo": billing_repo,
        "period_repo": period_repo,
    }


def _create_sync_services(
    event_bus: EventBus,
    sc_repo: SourceConnectionRepository,
    collection_repo: CollectionRepository,
    conn_repo: ConnectionRepository,
    cred_repo: IntegrationCredentialRepository,
    source_registry: SourceRegistry,
    sync_repo: SyncRepository,
    sync_cursor_repo: SyncCursorRepository,
    sync_job_repo: SyncJobRepository,
    auth_provider_registry: AuthProviderRegistry | None = None,
) -> dict:
    """Create leaf sync-domain services.

    The unified SyncService is built in create_container() because it
    depends on SyncFactory, which is built after embedders + storage.

    Build order:
    1. Leaf services (SyncJobService, TemporalWorkflowService)
    2. ResponseBuilder
    3. TemporalScheduleService
    4. SyncStateMachine
    """
    entity_count_repo = EntityCountRepository()
    entity_repo = EntityRepository()

    sync_job_service = SyncJobService(sync_job_repo=sync_job_repo)
    sync_job_state_machine = SyncJobStateMachine(
        sync_job_repo=sync_job_repo,
        event_bus=event_bus,
    )

    temporal_workflow_service = TemporalWorkflowService()

    response_builder = ResponseBuilder(
        sc_repo=sc_repo,
        connection_repo=conn_repo,
        credential_repo=cred_repo,
        source_registry=source_registry,
        entity_count_repo=entity_count_repo,
        sync_job_repo=sync_job_repo,
        auth_provider_registry=auth_provider_registry,
    )

    temporal_schedule_service = TemporalScheduleService(
        sync_repo=sync_repo,
        sc_repo=sc_repo,
        collection_repo=collection_repo,
        connection_repo=conn_repo,
    )

    sync_state_machine = SyncStateMachine(
        sync_repo=sync_repo,
        temporal_schedule_service=temporal_schedule_service,
    )

    return {
        "sync_job_service": sync_job_service,
        "sync_job_state_machine": sync_job_state_machine,
        "sync_state_machine": sync_state_machine,
        "sync_cursor_repo": sync_cursor_repo,
        "sync_job_repo": sync_job_repo,
        "temporal_workflow_service": temporal_workflow_service,
        "temporal_schedule_service": temporal_schedule_service,
        "response_builder": response_builder,
        "entity_repo": entity_repo,
        "entity_count_repo": entity_count_repo,
    }


def _create_usage_checker(
    settings: Settings,
    billing_deps: dict,
    source_deps: dict,
    user_org_repo: UserOrganizationRepositoryProtocol,
) -> UsageLimitCheckerProtocol:
    """Create the singleton UsageLimitChecker."""
    from connector_context.domains.usage.limit_checker import AlwaysAllowLimitChecker

    if settings.LOCAL_DEVELOPMENT:
        return AlwaysAllowLimitChecker()

    return UsageLimitChecker(
        usage_repo=UsageRepository(),
        billing_repo=billing_deps["billing_repo"],
        period_repo=billing_deps["period_repo"],
        sc_repo=source_deps["sc_repo"],
        user_org_repo=user_org_repo,
    )


def _create_usage_ledger(settings: Settings, billing_deps: dict) -> UsageLedgerProtocol:
    """Create the singleton UsageLedger."""
    from connector_context.domains.usage.ledger import NullUsageLedger
    from connector_context.domains.usage.repository import UsageRepository

    if settings.LOCAL_DEVELOPMENT:
        return NullUsageLedger()

    return UsageLedger(
        usage_repo=UsageRepository(),
        billing_repo=billing_deps["billing_repo"],
        period_repo=billing_deps["period_repo"],
    )


def _create_identity_provider(settings: Settings) -> IdentityProvider:
    """Create identity provider: Auth0 if enabled, otherwise null implementation."""
    if settings.AUTH_ENABLED:
        from connector_context.adapters.identity.auth0 import auth0_management_client

        if auth0_management_client:
            from connector_context.adapters.identity.auth0 import Auth0IdentityProvider

            return Auth0IdentityProvider(client=auth0_management_client)

    from connector_context.adapters.identity.null import NullIdentityProvider

    return NullIdentityProvider()


def _create_organization_service(
    *,
    identity_provider: IdentityProvider,
    payment_gateway: "PaymentGatewayProtocol",
    billing_ops,
    billing_repo,
    webhook_admin,
    event_bus,
    user_org_repo,
    context_cache,
):
    """Build the organization service with lifecycle + provisioning sub-modules."""
    from connector_context.domains.organizations.operations import OrganizationLifecycleOperations
    from connector_context.domains.organizations.provisioning.operations import ProvisioningOperations
    from connector_context.domains.organizations.repository import OrganizationRepository
    from connector_context.domains.organizations.service import OrganizationService

    org_repo = OrganizationRepository()

    lifecycle_ops = OrganizationLifecycleOperations(
        org_repo=org_repo,
        user_org_repo=user_org_repo,
        identity_provider=identity_provider,
        payment_gateway=payment_gateway,
        billing_ops=billing_ops,
        billing_repo=billing_repo,
        webhook_admin=webhook_admin,
        event_bus=event_bus,
        context_cache=context_cache,
    )
    from connector_context.domains.users.repository import UserRepository

    provisioning_ops = ProvisioningOperations(
        org_repo=org_repo,
        user_org_repo=user_org_repo,
        user_repo=UserRepository(),
        identity_provider=identity_provider,
    )

    return OrganizationService(
        lifecycle_ops=lifecycle_ops,
        provisioning_ops=provisioning_ops,
        org_repo=org_repo,
        user_org_repo=user_org_repo,
        identity_provider=identity_provider,
        event_bus=event_bus,
    )


def _create_user_service(  # type: ignore[no-untyped-def]
    *,
    org_service,
    user_org_repo,
    email_service,
):
    """Build the user service with org service + repo + email dependencies."""
    from connector_context.domains.users.repository import UserRepository
    from connector_context.domains.users.service import UserService

    return UserService(
        user_repo=UserRepository(),
        org_service=org_service,
        user_org_repo=user_org_repo,
        email_service=email_service,
    )


def _create_email_service(settings):  # type: ignore[no-untyped-def]
    """Create email service: Resend if configured, otherwise null (no-op)."""
    if settings.RESEND_API_KEY and settings.RESEND_FROM_EMAIL:
        from connector_context.adapters.email.resend import ResendEmailService

        return ResendEmailService()

    from connector_context.adapters.email.null import NullEmailService

    return NullEmailService()


def _create_rate_limiter(settings: Settings):
    """Create rate limiter: Redis if enabled, otherwise null (always allow)."""
    if settings.LOCAL_DEVELOPMENT or settings.DISABLE_RATE_LIMIT:
        from connector_context.adapters.rate_limiter.null import NullRateLimiter

        return NullRateLimiter()

    from connector_context.adapters.rate_limiter.redis import RedisRateLimiter

    return RedisRateLimiter(redis_client=redis_client.client)


def _build_llm_chain(
    settings: Settings,
    config: SearchConfig,
    circuit_breaker: CircuitBreaker,
):
    """Build LLM fallback chain from SearchConfig, skipping providers without API keys.

    When no provider in the chain has a configured API key (or all fail to initialize),
    returns an ``UnavailableLLM`` null-object rather than raising. This keeps the
    backend bootable for deployers who only use Instant search. Classic and agentic
    search surface ``LLMUnavailableError`` on first invocation, mapped to HTTP 503.
    """
    provider_classes = {
        LLMProvider.ANTHROPIC: AnthropicLLM,
        LLMProvider.CEREBRAS: CerebrasLLM,
        LLMProvider.GEMINI: GeminiLLM,
        LLMProvider.GROQ: GroqLLM,
        LLMProvider.MISTRAL: MistralLLM,
        LLMProvider.TOGETHER: TogetherLLM,
    }

    def _unavailable(reason: str, level: str = "info") -> UnavailableLLM:
        getattr(logger, level)(
            f"[SearchFactory] {reason} — classic/agentic search will return HTTP 503 "
            "until a key is set. Instant search is unaffected."
        )
        return UnavailableLLM()

    # Collect available (provider, model_spec, class) tuples first,
    # then decide retry strategy based on how many survived.
    available = []
    for provider, model in config.LLM_FALLBACK_CHAIN:
        api_key_attr = PROVIDER_API_KEY_SETTINGS.get(provider)
        if api_key_attr and not getattr(settings, api_key_attr, None):
            logger.debug(f"[SearchFactory] Skipping {provider.value}: no API key")
            continue

        model_spec = get_llm_model_spec(provider, model)
        provider_cls = provider_classes.get(provider)
        if provider_cls is None:
            logger.warning(f"[SearchFactory] Unknown provider: {provider.value}")
            continue

        available.append((provider, model, model_spec, provider_cls))

    if not available:
        return _unavailable("No LLM provider API keys configured")

    # Single provider: use default retries.
    # Multiple providers: max_retries=0 for all except the last provider,
    # which gets default retries since there's nothing to fall back to.
    llm_providers = []
    for idx, (provider, model, model_spec, provider_cls) in enumerate(available):
        is_last = idx == len(available) - 1
        retries = None if (len(available) == 1 or is_last) else 0
        try:
            llm_providers.append(provider_cls(model_spec=model_spec, max_retries=retries))
            logger.info(
                f"[SearchFactory] Added {provider.value}/{model.value} "
                f"({model_spec.api_model_name})"
            )
        except Exception as e:
            logger.warning(
                f"[SearchFactory] Failed to initialize "
                f"{provider.value}/{model.value}: {e}. Skipping."
            )

    if not llm_providers:
        return _unavailable("All configured LLM providers failed to initialize", level="warning")

    if len(llm_providers) == 1:
        return llm_providers[0]
    return FallbackChainLLM(providers=llm_providers, circuit_breaker=circuit_breaker)


def _create_search_services(
    settings: Settings,
    circuit_breaker: CircuitBreaker,
    dense_embedder: DenseEmbedderProtocol,
    sparse_embedder: SparseEmbedderProtocol,
    collection_repo: "CollectionRepository",
    sc_repo: "SourceConnectionRepository",
    source_registry: "SourceRegistry",
    entity_definition_registry: "EntityDefinitionRegistry",
    event_bus: "EventBus",
    source_lifecycle: "SourceLifecycleService",
    access_broker: "AccessBroker",
) -> dict:
    """Create search domain services (LLM, tokenizer, reranker, metadata builder, per-tier).

    Build order:
    1. Tokenizer (from SearchConfig)
    2. LLM fallback chain (from SearchConfig, skips providers without API keys)
    3. Reranker (optional, None if no COHERE_API_KEY)
    4. CollectionMetadataBuilder (needs repos)
    5. Per-tier services (instant, classic, agentic)
    """
    config = SearchConfig()

    # 1. Tokenizer — validate against primary LLM model requirements
    primary_provider, primary_model = config.LLM_FALLBACK_CHAIN[0]
    primary_llm_spec = get_llm_model_spec(primary_provider, primary_model)

    if config.TOKENIZER_TYPE != primary_llm_spec.required_tokenizer_type:
        raise ValueError(
            f"Primary LLM '{primary_provider.value}/{primary_model.value}' requires "
            f"tokenizer type '{primary_llm_spec.required_tokenizer_type.value}', "
            f"but SearchConfig specifies '{config.TOKENIZER_TYPE.value}'"
        )
    if config.TOKENIZER_ENCODING != primary_llm_spec.required_tokenizer_encoding:
        raise ValueError(
            f"Primary LLM '{primary_provider.value}/{primary_model.value}' requires "
            f"tokenizer encoding '{primary_llm_spec.required_tokenizer_encoding.value}', "
            f"but SearchConfig specifies '{config.TOKENIZER_ENCODING.value}'"
        )

    tokenizer_spec = get_tokenizer_spec(config.TOKENIZER_TYPE, config.TOKENIZER_ENCODING)
    tokenizer = TiktokenTokenizer(model_spec=tokenizer_spec)

    # 2. LLM fallback chain
    llm = _build_llm_chain(settings, config, circuit_breaker)

    # 3. Reranker (optional)
    reranker = None
    if getattr(settings, "COHERE_API_KEY", None):
        reranker = CohereReranker(api_key=settings.COHERE_API_KEY)
        logger.info("[SearchFactory] Cohere reranker enabled")

    # 4. CollectionMetadataBuilder
    metadata_builder = CollectionMetadataBuilder(
        collection_repo=collection_repo,
        sc_repo=sc_repo,
        source_registry=source_registry,
        entity_definition_registry=entity_definition_registry,
        entity_count_repo=EntityCountRepository(),
    )

    # 5. Vector DB + shared executor
    from vespa.application import Vespa

    vespa_app = Vespa(url=settings.VESPA_URL, port=settings.VESPA_PORT)
    filter_translator = FilterTranslator(logger=logger)
    vector_db = VespaVectorDB(app=vespa_app, logger=logger, filter_translator=filter_translator)

    executor = SearchPlanExecutor(
        dense_embedder=dense_embedder,
        sparse_embedder=sparse_embedder,
        vector_db=vector_db,
        sc_repo=sc_repo,
        source_registry=source_registry,
        source_lifecycle=source_lifecycle,
        access_broker=access_broker,
    )

    # 6. Per-tier services
    instant_search = InstantSearchService(
        executor=executor, collection_repo=collection_repo, event_bus=event_bus
    )
    classic_search = ClassicSearchService(
        llm=llm,
        reranker=reranker,
        executor=executor,
        collection_repo=collection_repo,
        metadata_builder=metadata_builder,
        event_bus=event_bus,
    )
    agentic_search = AgenticSearchService(
        llm=llm,
        tokenizer=tokenizer,
        reranker=reranker,
        executor=executor,
        vector_db=vector_db,
        metadata_builder=metadata_builder,
        collection_repo=collection_repo,
        event_bus=event_bus,
    )

    return {
        "instant_search": instant_search,
        "classic_search": classic_search,
        "agentic_search": agentic_search,
    }


def _create_storage_backend(settings: Settings):  # -> StorageBackend
    """Create storage backend from settings.

    Lazy-imports each adapter to avoid pulling in heavy cloud SDKs.
    """
    from connector_context.core.config import StorageBackendType

    backend_type = settings.STORAGE_BACKEND

    logger.info(f"Initializing storage backend: {backend_type}")

    if backend_type == StorageBackendType.FILESYSTEM:
        from connector_context.adapters.storage.filesystem import FilesystemBackend

        return FilesystemBackend(base_path=settings.STORAGE_PATH)

    if backend_type == StorageBackendType.AZURE:
        if not settings.STORAGE_AZURE_ACCOUNT:
            raise ValueError("STORAGE_AZURE_ACCOUNT required for azure backend")
        from connector_context.adapters.storage.azure_blob import AzureBlobBackend

        return AzureBlobBackend(
            storage_account=settings.STORAGE_AZURE_ACCOUNT,
            container=settings.STORAGE_AZURE_CONTAINER,
            prefix=settings.STORAGE_AZURE_PREFIX,
        )

    if backend_type == StorageBackendType.AWS:
        if not settings.STORAGE_AWS_BUCKET:
            raise ValueError("STORAGE_AWS_BUCKET required for aws backend")
        if not settings.STORAGE_AWS_REGION:
            raise ValueError("STORAGE_AWS_REGION required for aws backend")
        from connector_context.adapters.storage.aws_s3 import S3Backend

        return S3Backend(
            bucket=settings.STORAGE_AWS_BUCKET,
            region=settings.STORAGE_AWS_REGION,
            prefix=settings.STORAGE_AWS_PREFIX,
            endpoint_url=settings.STORAGE_AWS_ENDPOINT_URL,
        )

    if backend_type == StorageBackendType.GCP:
        if not settings.STORAGE_GCP_BUCKET:
            raise ValueError("STORAGE_GCP_BUCKET required for gcp backend")
        from connector_context.adapters.storage.gcp_gcs import GCSBackend

        return GCSBackend(
            bucket=settings.STORAGE_GCP_BUCKET,
            project=settings.STORAGE_GCP_PROJECT,
            prefix=settings.STORAGE_GCP_PREFIX,
        )

    valid_options = ", ".join(t.value for t in StorageBackendType)
    raise ValueError(f"Unknown STORAGE_BACKEND: {backend_type}. Valid options: {valid_options}")
