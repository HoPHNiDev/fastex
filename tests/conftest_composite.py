"""
Composite Backend Test Fixtures

This module provides pytest fixtures for testing the composite backend.
It includes mock backends, configurations, and test scenarios.

The fixtures support:
- Mock primary and fallback backends
- Different switching strategies
- Circuit breaker testing scenarios
- Health check testing
- Error simulation
- Statistics verification
"""

import datetime
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio

from fastex.limiter.backend.composite.composite import CompositeLimiterBackend
from fastex.limiter.backend.composite.enums import (
    CircuitBreakerState,
    SwitchingStrategy,
)
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.interfaces import LimiterBackend
from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.schemas import RateLimitConfig


class MockLimiterBackend(LimiterBackend):
    """Mock limiter backend for testing."""

    def __init__(self, name: str = "mock", fail_on_connect: bool = False) -> None:
        """Initialize mock backend."""
        self.name = name
        self._connected = False
        self._fail_on_connect = fail_on_connect
        self._should_fail = False
        self._request_count = 0
        self._check_limit_calls: list[tuple[str, RateLimitConfig]] = []

    async def connect(self, config: Any = None) -> None:
        """Mock connect method."""
        if self._fail_on_connect:
            raise LimiterBackendError(f"Mock {self.name} backend connection failed")
        self._connected = True

    async def disconnect(self) -> None:
        """Mock disconnect method."""
        self._connected = False

    async def check_limit(self, key: str, config: RateLimitConfig) -> RateLimitResult:
        """Mock check_limit method."""
        self._request_count += 1
        self._check_limit_calls.append((key, config))

        if self._should_fail:
            raise LimiterBackendError(f"Mock {self.name} backend failed")

        # Return mock result
        return RateLimitResult(
            is_exceeded=False,
            limit_times=config.times,
            retry_after_ms=0,
            remaining_requests=config.times - 1,
            reset_time=None,
        )

    def is_connected(self, raise_exc: bool = False) -> bool:
        """Mock is_connected method."""
        if not self._connected and raise_exc:
            raise LimiterBackendError(f"Mock {self.name} backend not connected")
        return self._connected

    def set_should_fail(self, should_fail: bool) -> None:
        """Control whether this backend should fail."""
        self._should_fail = should_fail

    def get_request_count(self) -> int:
        """Get number of requests made to this backend."""
        return self._request_count

    def get_check_limit_calls(self) -> list[tuple[str, RateLimitConfig]]:
        """Get all check_limit calls made to this backend."""
        return self._check_limit_calls.copy()

    def reset_stats(self) -> None:
        """Reset backend statistics."""
        self._request_count = 0
        self._check_limit_calls.clear()


@pytest.fixture
def mock_primary_backend() -> MockLimiterBackend:
    """Provide a mock primary backend."""
    return MockLimiterBackend(name="primary")


@pytest.fixture
def mock_fallback_backend() -> MockLimiterBackend:
    """Provide a mock fallback backend."""
    return MockLimiterBackend(name="fallback")


@pytest.fixture
def failing_primary_backend() -> MockLimiterBackend:
    """Provide a mock primary backend that fails on connect."""
    return MockLimiterBackend(name="primary", fail_on_connect=True)


@pytest.fixture
def failing_fallback_backend() -> MockLimiterBackend:
    """Provide a mock fallback backend that fails on connect."""
    return MockLimiterBackend(name="fallback", fail_on_connect=True)


@pytest.fixture
def rate_limit_config() -> RateLimitConfig:
    """Provide a standard rate limit configuration for testing."""
    return RateLimitConfig(times=10, seconds=60)


@pytest.fixture
def strict_rate_limit_config() -> RateLimitConfig:
    """Provide a strict rate limit configuration for testing."""
    return RateLimitConfig(times=2, seconds=10)


@pytest.fixture
def composite_backend_default(
    mock_primary_backend: MockLimiterBackend,
    mock_fallback_backend: MockLimiterBackend,
) -> CompositeLimiterBackend:
    """Provide a composite backend with default settings."""
    return CompositeLimiterBackend(
        primary=mock_primary_backend,
        fallback=mock_fallback_backend,
    )


@pytest.fixture
def composite_backend_fail_fast(
    mock_primary_backend: MockLimiterBackend,
    mock_fallback_backend: MockLimiterBackend,
) -> CompositeLimiterBackend:
    """Provide a composite backend with fail-fast strategy."""
    return CompositeLimiterBackend(
        primary=mock_primary_backend,
        fallback=mock_fallback_backend,
        strategy=SwitchingStrategy.FAIL_FAST,
    )


@pytest.fixture
def composite_backend_health_check(
    mock_primary_backend: MockLimiterBackend,
    mock_fallback_backend: MockLimiterBackend,
) -> CompositeLimiterBackend:
    """Provide a composite backend with health check strategy."""
    return CompositeLimiterBackend(
        primary=mock_primary_backend,
        fallback=mock_fallback_backend,
        strategy=SwitchingStrategy.HEALTH_CHECK,
        health_check_interval_seconds=1,  # Fast for testing
    )


@pytest.fixture
def composite_backend_circuit_breaker(
    mock_primary_backend: MockLimiterBackend,
    mock_fallback_backend: MockLimiterBackend,
) -> CompositeLimiterBackend:
    """Provide a composite backend with circuit breaker strategy and fast settings."""
    return CompositeLimiterBackend(
        primary=mock_primary_backend,
        fallback=mock_fallback_backend,
        strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        failure_threshold=3,  # Low threshold for testing
        recovery_timeout_seconds=2,  # Fast recovery for testing
    )


@pytest_asyncio.fixture
async def connected_composite_backend(
    composite_backend_default: CompositeLimiterBackend,
) -> AsyncGenerator[CompositeLimiterBackend, None]:
    """Provide a connected composite backend."""
    await composite_backend_default.connect()
    yield composite_backend_default
    await composite_backend_default.disconnect()


@pytest_asyncio.fixture
async def connected_composite_circuit_breaker(
    composite_backend_circuit_breaker: CompositeLimiterBackend,
) -> AsyncGenerator[CompositeLimiterBackend, None]:
    """Provide a connected composite backend with circuit breaker."""
    await composite_backend_circuit_breaker.connect()
    yield composite_backend_circuit_breaker
    await composite_backend_circuit_breaker.disconnect()


@pytest_asyncio.fixture
async def connected_composite_health_check(
    composite_backend_health_check: CompositeLimiterBackend,
) -> AsyncGenerator[CompositeLimiterBackend, None]:
    """Provide a connected composite backend with health checking."""
    await composite_backend_health_check.connect()
    yield composite_backend_health_check
    await composite_backend_health_check.disconnect()


@pytest.fixture
def circuit_breaker_scenario_data() -> dict[str, Any]:
    """Provide test data for circuit breaker scenarios."""
    return {
        "failure_threshold": 3,
        "recovery_timeout": 2,
        "test_key": "circuit_test_key",
        "expected_states": [
            CircuitBreakerState.CLOSED,
            CircuitBreakerState.OPEN,
            CircuitBreakerState.HALF_OPEN,
        ],
    }


@pytest.fixture
def health_check_scenario_data() -> dict[str, Any]:
    """Provide test data for health check scenarios."""
    return {
        "health_check_interval": 1,
        "test_key": "health_test_key",
        "check_iterations": 5,
    }


class ErrorScenarios:
    """Helper class for creating error scenarios."""

    @staticmethod
    def make_backend_fail_after(backend: MockLimiterBackend, requests: int) -> None:
        """Make backend fail after specified number of requests."""
        original_check = backend.check_limit
        call_count = 0

        async def failing_check(key: str, config: RateLimitConfig) -> RateLimitResult:
            nonlocal call_count
            call_count += 1
            if call_count > requests:
                backend.set_should_fail(True)
            return await original_check(key, config)

        backend.check_limit = failing_check

    @staticmethod
    def make_backend_recover_after(backend: MockLimiterBackend, requests: int) -> None:
        """Make backend recover after specified number of requests."""
        original_check = backend.check_limit
        call_count = 0

        async def recovering_check(
            key: str, config: RateLimitConfig
        ) -> RateLimitResult:
            nonlocal call_count
            call_count += 1
            if call_count > requests:
                backend.set_should_fail(False)
            return await original_check(key, config)

        backend.check_limit = recovering_check


@pytest.fixture
def error_scenarios() -> ErrorScenarios:
    """Provide error scenario helper."""
    return ErrorScenarios()


# Mock response fixtures for different scenarios
@pytest.fixture
def exceeded_limit_result() -> RateLimitResult:
    """Provide a rate limit exceeded result."""
    return RateLimitResult(
        is_exceeded=True,
        limit_times=10,
        retry_after_ms=60000,
        remaining_requests=0,
        reset_time=datetime.datetime.now() + datetime.timedelta(minutes=5),
    )


@pytest.fixture
def allowed_limit_result() -> RateLimitResult:
    """Provide a rate limit allowed result."""
    return RateLimitResult(
        is_exceeded=False,
        limit_times=10,
        retry_after_ms=0,
        remaining_requests=5,
        reset_time=None,
    )


# Performance testing fixtures
@pytest.fixture
def performance_config() -> dict[str, Any]:
    """Configuration for performance testing."""
    return {
        "concurrent_requests": 100,
        "test_duration_seconds": 10,
        "request_rate_per_second": 50,
    }


# Nested backend prevention fixtures
@pytest.fixture
def nested_composite_primary(
    mock_fallback_backend: MockLimiterBackend,
) -> CompositeLimiterBackend:
    """Create a composite backend to test nested prevention."""
    return CompositeLimiterBackend(
        primary=mock_fallback_backend,
        fallback=mock_fallback_backend,
    )


# Utility fixtures for assertions
@pytest.fixture
def assert_helpers():
    """Provide assertion helpers for composite backend testing."""

    class AssertHelpers:
        @staticmethod
        def assert_backend_used(
            backend: MockLimiterBackend, expected_calls: int
        ) -> None:
            """Assert that backend was used expected number of times."""
            assert backend.get_request_count() == expected_calls

        @staticmethod
        def assert_circuit_state(
            composite: CompositeLimiterBackend, expected_state: CircuitBreakerState
        ) -> None:
            """Assert circuit breaker state."""
            stats = composite.get_stats()
            assert CircuitBreakerState(stats["circuit_state"]) == expected_state

        @staticmethod
        def assert_backend_selected(
            composite: CompositeLimiterBackend, expected: str
        ) -> None:
            """Assert which backend is currently selected."""
            assert composite.current_backend == expected

        @staticmethod
        async def assert_health_status(
            composite: CompositeLimiterBackend,
            primary_healthy: bool,
            fallback_healthy: bool,
        ) -> None:
            """Assert health status of backends."""
            stats = composite.get_stats()
            assert stats["primary_healthy"] == primary_healthy
            assert stats["fallback_healthy"] == fallback_healthy

    return AssertHelpers()
