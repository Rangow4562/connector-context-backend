"""Core protocols for dependency injection.

Domain-specific protocols (repositories, OAuth2, source lifecycle) have moved
to their respective domains/ directories. This module keeps cross-cutting
infrastructure protocols only.
"""

from connector_context.core.health.protocols import HealthProbe, HealthServiceProtocol
from connector_context.core.protocols.cache import ContextCache
from connector_context.core.protocols.circuit_breaker import CircuitBreaker
from connector_context.core.protocols.email import EmailService
from connector_context.core.protocols.encryption import CredentialEncryptor
from connector_context.core.protocols.event_bus import DomainEvent, EventBus, EventHandler, EventSubscriber
from connector_context.core.protocols.identity import IdentityProvider
from connector_context.core.protocols.llm import LLMProtocol
from connector_context.core.protocols.metrics import (
    AgenticSearchMetrics,
    DbPool,
    DbPoolMetrics,
    HttpMetrics,
    MetricsRenderer,
    MetricsService,
    WorkerMetrics,
)
from connector_context.core.protocols.payment import PaymentGatewayProtocol
from connector_context.core.protocols.pubsub import PubSub, PubSubSubscription
from connector_context.core.protocols.rate_limiter import RateLimiter
from connector_context.core.protocols.reranker import RerankerProtocol
from connector_context.core.protocols.tokenizer import TokenizerProtocol
from connector_context.core.protocols.webhooks import (
    EndpointVerifier,
    WebhookAdmin,
    WebhookPublisher,
    WebhookServiceProtocol,
)
from connector_context.core.protocols.worker_metrics_registry import WorkerMetricsRegistryProtocol
from connector_context.domains.ocr.protocols import OcrProvider

__all__ = [
    "AgenticSearchMetrics",
    "ContextCache",
    "CircuitBreaker",
    "CredentialEncryptor",
    "DbPool",
    "DbPoolMetrics",
    "DomainEvent",
    "EmailService",
    "EndpointVerifier",
    "EventBus",
    "EventHandler",
    "EventSubscriber",
    "HealthProbe",
    "HealthServiceProtocol",
    "HttpMetrics",
    "LLMProtocol",
    "IdentityProvider",
    "MetricsRenderer",
    "MetricsService",
    "OcrProvider",
    "PaymentGatewayProtocol",
    "PubSub",
    "PubSubSubscription",
    "RateLimiter",
    "RerankerProtocol",
    "WebhookAdmin",
    "WebhookPublisher",
    "TokenizerProtocol",
    "WebhookServiceProtocol",
    "WorkerMetrics",
    "WorkerMetricsRegistryProtocol",
]
