"""Circuit breaker adapters."""

from connector_context.adapters.circuit_breaker.fake import FakeCircuitBreaker
from connector_context.adapters.circuit_breaker.in_memory import InMemoryCircuitBreaker

__all__ = ["InMemoryCircuitBreaker", "FakeCircuitBreaker"]
