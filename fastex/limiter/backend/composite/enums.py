from enum import Enum


class SwitchingStrategy(Enum):
    """Strategy for switching between primary and fallback backends."""

    FAIL_FAST = "fail_fast"  # Switch on first error
    CIRCUIT_BREAKER = "circuit_breaker"  # Switch after threshold of failures
    HEALTH_CHECK = "health_check"  # Switch based on health checks


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Primary backend is down
    HALF_OPEN = "half_open"  # Testing if primary is back
