"""
Unit tests for CompositeLimiterBackend backend selection strategies.

This module tests the backend selection logic for different strategies:
- FAIL_FAST: Switch on first error
- CIRCUIT_BREAKER: Switch after threshold of failures
- HEALTH_CHECK: Switch based on health checks

Tests cover:
- Backend selection based on strategy
- Strategy-specific logic
- Backend availability checks
- State transitions
- Error handling in selection
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from fastex.limiter.backend.composite.composite import CompositeLimiterBackend
from fastex.limiter.backend.composite.enums import (
    CircuitBreakerState,
    SwitchingStrategy,
)
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.interfaces import LimiterBackend


class TestCompositeLimiterBackendBackendSelection:
    """Test CompositeLimiterBackend backend selection functionality."""

    def test_select_backend_unknown_strategy(self) -> None:
        """Test _select_backend with unknown strategy raises error."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Set invalid strategy
        backend._strategy = "invalid_strategy"  # type: ignore

        with pytest.raises(LimiterBackendError, match="Unknown switching strategy"):
            backend._select_backend()

    def test_is_backend_available_none_backend(self) -> None:
        """Test _is_backend_available with None backend."""
        result = CompositeLimiterBackend._is_backend_available(None)
        assert result is False

    def test_is_backend_available_connected_backend(self) -> None:
        """Test _is_backend_available with connected backend."""
        backend = MagicMock(spec=LimiterBackend)
        backend.is_connected.return_value = True

        result = CompositeLimiterBackend._is_backend_available(backend)
        assert result is True

    def test_is_backend_available_disconnected_backend(self) -> None:
        """Test _is_backend_available with disconnected backend."""
        backend = MagicMock(spec=LimiterBackend)
        backend.is_connected.return_value = False

        result = CompositeLimiterBackend._is_backend_available(backend)
        assert result is False


class TestFailFastStrategy:
    """Test FAIL_FAST strategy backend selection."""

    def test_select_fail_fast_primary_available(self) -> None:
        """Test fail-fast strategy selects primary when available."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Mock primary as available
        primary.is_connected.return_value = True
        fallback.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.FAIL_FAST,
        )

        selected = backend._select_fail_fast()
        assert selected is primary

    def test_select_fail_fast_primary_unavailable_fallback_available(self) -> None:
        """Test fail-fast strategy selects fallback when primary unavailable."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Mock primary as unavailable, fallback as available
        primary.is_connected.return_value = False
        fallback.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.FAIL_FAST,
        )

        selected = backend._select_fail_fast()
        assert selected is fallback

    def test_select_fail_fast_both_unavailable(self) -> None:
        """Test fail-fast strategy returns primary when both unavailable."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Mock both as unavailable
        primary.is_connected.return_value = False
        fallback.is_connected.return_value = False

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.FAIL_FAST,
        )

        # Should return primary to let error handling deal with it
        selected = backend._select_fail_fast()
        assert selected is primary


class TestCircuitBreakerStrategy:
    """Test CIRCUIT_BREAKER strategy backend selection."""

    def test_select_circuit_breaker_closed_state(self) -> None:
        """Test circuit breaker strategy in CLOSED state selects primary."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        )

        # Ensure circuit is closed
        backend._circuit_state = CircuitBreakerState.CLOSED

        selected = backend._select_circuit_breaker()
        assert selected is primary

    def test_select_circuit_breaker_open_state_within_timeout(self) -> None:
        """Test circuit breaker strategy in OPEN state within timeout selects fallback."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
            recovery_timeout_seconds=60,
        )

        # Set circuit to open and recent failure
        backend._circuit_state = CircuitBreakerState.OPEN
        backend._last_failure_time = time.time()  # Recent failure

        selected = backend._select_circuit_breaker()
        assert selected is fallback

    @patch("time.time")
    def test_select_circuit_breaker_open_state_timeout_expired(self, mock_time) -> None:
        """Test circuit breaker strategy in OPEN state after timeout moves to HALF_OPEN."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
            recovery_timeout_seconds=60,
        )

        # Set circuit to open with old failure time
        backend._circuit_state = CircuitBreakerState.OPEN
        backend._last_failure_time = 100.0
        mock_time.return_value = 200.0  # 100 seconds later (> 60 timeout)

        selected = backend._select_circuit_breaker()

        # Should move to HALF_OPEN and select primary
        assert backend._circuit_state == CircuitBreakerState.HALF_OPEN
        assert selected is primary

    def test_select_circuit_breaker_open_state_no_failure_time(self) -> None:
        """Test circuit breaker strategy in OPEN state with no failure time."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        )

        # Set circuit to open with no failure time
        backend._circuit_state = CircuitBreakerState.OPEN
        backend._last_failure_time = None

        selected = backend._select_circuit_breaker()
        assert selected is fallback

    def test_select_circuit_breaker_half_open_state(self) -> None:
        """Test circuit breaker strategy in HALF_OPEN state selects primary."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        )

        # Set circuit to half-open
        backend._circuit_state = CircuitBreakerState.HALF_OPEN

        selected = backend._select_circuit_breaker()
        assert selected is primary

    def test_select_circuit_breaker_unknown_state(self) -> None:
        """Test circuit breaker strategy with unknown state raises error."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        )

        # Set invalid circuit state
        backend._circuit_state = "invalid_state"  # type: ignore

        with pytest.raises(LimiterBackendError, match="Unknown circuit state"):
            backend._select_circuit_breaker()


class TestHealthCheckStrategy:
    """Test HEALTH_CHECK strategy backend selection."""

    def test_select_health_check_primary_healthy_and_available(self) -> None:
        """Test health check strategy selects primary when healthy and available."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Mock primary as healthy and available
        primary.is_connected.return_value = True
        fallback.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
        )

        backend._primary_healthy = True
        backend._fallback_healthy = True

        selected = backend._select_health_check()
        assert selected is primary

    def test_select_health_check_primary_unhealthy_fallback_healthy(self) -> None:
        """Test health check strategy selects fallback when primary unhealthy."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Mock fallback as available
        primary.is_connected.return_value = False
        fallback.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
        )

        backend._primary_healthy = False
        backend._fallback_healthy = True

        selected = backend._select_health_check()
        assert selected is fallback

    def test_select_health_check_primary_healthy_but_unavailable(self) -> None:
        """Test health check strategy selects fallback when primary unavailable."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Mock primary as unavailable despite being healthy
        primary.is_connected.return_value = False
        fallback.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
        )

        backend._primary_healthy = True  # Healthy but unavailable
        backend._fallback_healthy = True

        selected = backend._select_health_check()
        assert selected is fallback

    def test_select_health_check_both_unhealthy(self) -> None:
        """Test health check strategy prefers primary when both unhealthy."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Mock both as unavailable
        primary.is_connected.return_value = False
        fallback.is_connected.return_value = False

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
        )

        backend._primary_healthy = False
        backend._fallback_healthy = False

        # Should prefer primary when both are unhealthy
        selected = backend._select_health_check()
        assert selected is primary

    def test_select_health_check_fallback_unhealthy_but_available(self) -> None:
        """Test health check strategy considers availability over health."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        # Primary unhealthy and unavailable, fallback unhealthy but available
        primary.is_connected.return_value = False
        fallback.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
        )

        backend._primary_healthy = False
        backend._fallback_healthy = False

        # Should prefer primary over unhealthy fallback
        selected = backend._select_health_check()
        assert selected is primary


class TestIntegratedBackendSelection:
    """Test integrated backend selection across all strategies."""

    @pytest.mark.parametrize(
        "strategy",
        [
            SwitchingStrategy.FAIL_FAST,
            SwitchingStrategy.CIRCUIT_BREAKER,
            SwitchingStrategy.HEALTH_CHECK,
        ],
    )
    def test_select_backend_calls_appropriate_strategy_method(
        self, strategy: SwitchingStrategy
    ) -> None:
        """Test that _select_backend calls the appropriate strategy method."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        primary.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=strategy,
        )

        # Mock the strategy methods to verify they're called
        backend._select_fail_fast = MagicMock(return_value=primary)
        backend._select_circuit_breaker = MagicMock(return_value=primary)
        backend._select_health_check = MagicMock(return_value=primary)

        result = backend._select_backend()

        # Verify the correct method was called
        if strategy == SwitchingStrategy.FAIL_FAST:
            backend._select_fail_fast.assert_called_once()
            backend._select_circuit_breaker.assert_not_called()
            backend._select_health_check.assert_not_called()
        elif strategy == SwitchingStrategy.CIRCUIT_BREAKER:
            backend._select_fail_fast.assert_not_called()
            backend._select_circuit_breaker.assert_called_once()
            backend._select_health_check.assert_not_called()
        elif strategy == SwitchingStrategy.HEALTH_CHECK:
            backend._select_fail_fast.assert_not_called()
            backend._select_circuit_breaker.assert_not_called()
            backend._select_health_check.assert_called_once()

        assert result is primary

    def test_backend_selection_consistency(self) -> None:
        """Test that backend selection is consistent for same conditions."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        primary.is_connected.return_value = True
        fallback.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.FAIL_FAST,
        )

        # Multiple calls should return the same backend
        selected1 = backend._select_backend()
        selected2 = backend._select_backend()
        selected3 = backend._select_backend()

        assert selected1 is selected2 is selected3 is primary
