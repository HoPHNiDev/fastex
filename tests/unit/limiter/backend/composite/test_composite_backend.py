"""
Unit tests for CompositeLimiterBackend initialization and basic structure.

This module tests the core functionality of CompositeLimiterBackend:
- Class inheritance and structure
- Initialization with different parameters
- Basic properties and methods
- Validation logic
- Type checking

Tests cover:
- Default initialization
- Custom parameter initialization
- Nested backend prevention
- Property accessors
- Basic structure validation
"""

from unittest.mock import MagicMock

import pytest

from fastex.limiter.backend.composite.composite import CompositeLimiterBackend
from fastex.limiter.backend.composite.enums import (
    CircuitBreakerState,
    SwitchingStrategy,
)
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.interfaces import LimiterBackend


class TestCompositeLimiterBackendInheritance:
    """Test CompositeLimiterBackend inheritance and basic structure."""

    def test_inheritance(self) -> None:
        """Test that CompositeLimiterBackend inherits from LimiterBackend."""
        assert issubclass(CompositeLimiterBackend, LimiterBackend)

    def test_class_has_required_methods(self) -> None:
        """Test that class has all required abstract methods."""
        required_methods = [
            "connect",
            "disconnect",
            "check_limit",
            "is_connected",
        ]

        for method_name in required_methods:
            assert hasattr(CompositeLimiterBackend, method_name)
            assert callable(getattr(CompositeLimiterBackend, method_name))

    def test_class_has_composite_specific_methods(self) -> None:
        """Test that class has composite-specific methods."""
        composite_methods = [
            "get_stats",
            "force_switch_to_primary",
            "force_switch_to_fallback",
            "current_backend",
            "primary_backend",
            "fallback_backend",
        ]

        for method_name in composite_methods:
            assert hasattr(CompositeLimiterBackend, method_name)

    def test_class_has_logger(self) -> None:
        """Test that class has logger configured."""
        assert hasattr(CompositeLimiterBackend, "logger")
        assert CompositeLimiterBackend.logger.name == "CompositeLimiterBackend"


class TestCompositeLimiterBackendInitialization:
    """Test CompositeLimiterBackend initialization functionality."""

    def test_initialization_defaults(self) -> None:
        """Test initialization with default parameters."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Test default values
        assert backend._primary is primary
        assert backend._fallback is fallback
        assert backend._strategy == SwitchingStrategy.CIRCUIT_BREAKER
        assert backend._failure_threshold == 5
        assert backend._recovery_timeout == 60
        assert backend._health_check_interval == 30

        # Test initial state
        assert backend._circuit_state == CircuitBreakerState.CLOSED
        assert backend._failure_count == 0
        assert backend._last_failure_time is None
        assert backend._last_success_time is None
        assert backend._health_check_task is None
        assert backend._primary_healthy is True
        assert backend._fallback_healthy is True
        assert backend._connected is False

        # Test statistics initialization
        assert backend._primary_requests == 0
        assert backend._fallback_requests == 0
        assert backend._primary_errors == 0
        assert backend._fallback_errors == 0

    def test_initialization_custom_parameters(self) -> None:
        """Test initialization with custom parameters."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.FAIL_FAST,
            failure_threshold=10,
            recovery_timeout_seconds=120,
            health_check_interval_seconds=60,
        )

        assert backend._primary is primary
        assert backend._fallback is fallback
        assert backend._strategy == SwitchingStrategy.FAIL_FAST
        assert backend._failure_threshold == 10
        assert backend._recovery_timeout == 120
        assert backend._health_check_interval == 60

    @pytest.mark.parametrize(
        "strategy",
        [
            SwitchingStrategy.FAIL_FAST,
            SwitchingStrategy.CIRCUIT_BREAKER,
            SwitchingStrategy.HEALTH_CHECK,
        ],
    )
    def test_initialization_with_different_strategies(
        self, strategy: SwitchingStrategy
    ) -> None:
        """Test initialization with different switching strategies."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=strategy,
        )

        assert backend._strategy == strategy

    @pytest.mark.parametrize("threshold", [1, 5, 10, 100])
    def test_initialization_with_different_failure_thresholds(
        self, threshold: int
    ) -> None:
        """Test initialization with different failure thresholds."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            failure_threshold=threshold,
        )

        assert backend._failure_threshold == threshold

    @pytest.mark.parametrize("timeout", [1, 30, 60, 300])
    def test_initialization_with_different_recovery_timeouts(
        self, timeout: int
    ) -> None:
        """Test initialization with different recovery timeouts."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            recovery_timeout_seconds=timeout,
        )

        assert backend._recovery_timeout == timeout

    @pytest.mark.parametrize("interval", [1, 10, 30, 120])
    def test_initialization_with_different_health_check_intervals(
        self, interval: int
    ) -> None:
        """Test initialization with different health check intervals."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            health_check_interval_seconds=interval,
        )

        assert backend._health_check_interval == interval


class TestCompositeLimiterBackendNestedPrevention:
    """Test prevention of nested CompositeLimiterBackend instances."""

    def test_nested_primary_backend_prevention(self) -> None:
        """Test that nested CompositeLimiterBackend as primary is prevented."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Create first composite backend
        nested_primary = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Try to create second with first as primary
        with pytest.raises(
            LimiterBackendError,
            match="Nested CompositeLimiterBackend instances are not allowed",
        ):
            CompositeLimiterBackend(
                primary=nested_primary,
                fallback=fallback,
            )

    def test_nested_fallback_backend_prevention(self) -> None:
        """Test that nested CompositeLimiterBackend as fallback is prevented."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Create first composite backend
        nested_fallback = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Try to create second with first as fallback
        with pytest.raises(
            LimiterBackendError,
            match="Nested CompositeLimiterBackend instances are not allowed",
        ):
            CompositeLimiterBackend(
                primary=primary,
                fallback=nested_fallback,
            )

    def test_both_nested_backend_prevention(self) -> None:
        """Test that both nested CompositeLimiterBackend instances are prevented."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Create first composite backend
        nested_primary = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Create second composite backend
        nested_fallback = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Try to create third with both as nested
        with pytest.raises(
            LimiterBackendError,
            match="Nested CompositeLimiterBackend instances are not allowed",
        ):
            CompositeLimiterBackend(
                primary=nested_primary,
                fallback=nested_fallback,
            )


class TestCompositeLimiterBackendProperties:
    """Test CompositeLimiterBackend property accessors."""

    def test_primary_backend_property(self) -> None:
        """Test primary_backend property accessor."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        assert backend.primary_backend is primary

    def test_fallback_backend_property(self) -> None:
        """Test fallback_backend property accessor."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        assert backend.fallback_backend is fallback

    def test_current_backend_property_initial_state(self) -> None:
        """Test current_backend property in initial state."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Initial state should select primary for circuit breaker strategy
        assert backend.current_backend == "primary"

    def test_current_backend_property_with_different_strategies(self) -> None:
        """Test current_backend property with different strategies."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Test with fail-fast strategy
        backend_ff = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.FAIL_FAST,
        )
        assert backend_ff.current_backend == "primary"

        # Test with health check strategy
        backend_hc = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
        )
        assert backend_hc.current_backend == "primary"

    def test_current_backend_property_error_handling(self) -> None:
        """Test current_backend property error handling."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Mock _select_backend to raise exception
        def mock_select_error():
            raise Exception("Mock selection error")

        backend._select_backend = mock_select_error  # type: ignore

        # Should return "unknown" on error
        assert backend.current_backend == "unknown"


class TestCompositeLimiterBackendInitialStateValidation:
    """Test initial state validation of CompositeLimiterBackend."""

    def test_initial_connection_state(self) -> None:
        """Test that backend starts disconnected."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        assert not backend._connected
        assert not backend.is_connected()

    def test_initial_circuit_breaker_state(self) -> None:
        """Test that circuit breaker starts in CLOSED state."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        )

        assert backend._circuit_state == CircuitBreakerState.CLOSED
        assert backend._failure_count == 0

    def test_initial_health_state(self) -> None:
        """Test that both backends start as healthy."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        assert backend._primary_healthy is True
        assert backend._fallback_healthy is True

    def test_initial_statistics_state(self) -> None:
        """Test that statistics start at zero."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        assert backend._primary_requests == 0
        assert backend._fallback_requests == 0
        assert backend._primary_errors == 0
        assert backend._fallback_errors == 0

    def test_initial_task_state(self) -> None:
        """Test that background tasks start as None."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        assert backend._health_check_task is None

    def test_initial_timestamp_state(self) -> None:
        """Test that timestamps start as None."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        assert backend._last_failure_time is None
        assert backend._last_success_time is None
