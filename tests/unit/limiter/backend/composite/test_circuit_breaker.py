"""
Unit tests for CompositeLimiterBackend circuit breaker logic.

This module tests the circuit breaker pattern implementation:
- State transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Failure counting and threshold management
- Recovery timeout handling
- Success/failure recording
- Manual circuit breaker control

Tests cover:
- Circuit breaker state transitions
- Failure threshold triggering
- Recovery timeout behavior
- Success resetting
- Manual force switching
- Time-based state changes
- Circuit breaker statistics
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fastex.limiter.backend.composite.composite import CompositeLimiterBackend
from fastex.limiter.backend.composite.enums import (
    CircuitBreakerState,
    SwitchingStrategy,
)
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.interfaces import LimiterBackend


class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state transitions."""

    @pytest.mark.asyncio
    async def test_closed_to_open_on_failure_threshold(self) -> None:
        """Test transition from CLOSED to OPEN when failure threshold is reached."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
            failure_threshold=3,
        )

        # Start in CLOSED state
        assert backend._circuit_state == CircuitBreakerState.CLOSED
        assert backend._failure_count == 0

        # Record failures to reach threshold
        error = LimiterBackendError("Test error")

        await backend._record_failure(primary, error)
        assert backend._circuit_state == CircuitBreakerState.CLOSED
        assert backend._failure_count == 1

        await backend._record_failure(primary, error)
        assert backend._circuit_state == CircuitBreakerState.CLOSED
        assert backend._failure_count == 2

        # Third failure should open the circuit
        await backend._record_failure(primary, error)
        assert backend._circuit_state == CircuitBreakerState.OPEN
        assert backend._failure_count == 3

    @patch("time.time")
    @pytest.mark.asyncio
    async def test_open_to_half_open_after_timeout(self, mock_time) -> None:
        """Test transition from OPEN to HALF_OPEN after recovery timeout."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
            recovery_timeout_seconds=60,
        )

        # Set circuit to OPEN state
        backend._circuit_state = CircuitBreakerState.OPEN
        backend._last_failure_time = 100.0

        # Before timeout expires
        mock_time.return_value = 150.0  # 50 seconds later
        selected = backend._select_circuit_breaker()
        assert backend._circuit_state == CircuitBreakerState.OPEN
        assert selected is fallback

        # After timeout expires
        mock_time.return_value = 200.0  # 100 seconds later (> 60 timeout)
        selected = backend._select_circuit_breaker()
        assert backend._circuit_state == CircuitBreakerState.HALF_OPEN
        assert selected is primary

    @pytest.mark.asyncio
    async def test_half_open_to_closed_on_success(self) -> None:
        """Test transition from HALF_OPEN to CLOSED on successful operation."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        )

        # Set circuit to HALF_OPEN state
        backend._circuit_state = CircuitBreakerState.HALF_OPEN
        backend._failure_count = 5  # Should be reset

        # Record success
        await backend._record_success(primary)

        assert backend._circuit_state == CircuitBreakerState.CLOSED
        assert backend._failure_count == 0

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self) -> None:
        """Test transition from HALF_OPEN to OPEN on failed operation."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        )

        # Set circuit to HALF_OPEN state
        backend._circuit_state = CircuitBreakerState.HALF_OPEN

        # Record failure
        error = LimiterBackendError("Test error")
        await backend._record_failure(primary, error)

        assert backend._circuit_state == CircuitBreakerState.OPEN


class TestCircuitBreakerFailureHandling:
    """Test circuit breaker failure handling logic."""

    @pytest.mark.asyncio
    async def test_record_failure_only_affects_primary_with_circuit_breaker(
        self,
    ) -> None:
        """Test that _record_failure only affects circuit for primary backend with circuit breaker strategy."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
            failure_threshold=3,
        )

        error = LimiterBackendError("Test error")

        # Fallback failure should not affect circuit breaker
        await backend._record_failure(fallback, error)
        assert backend._circuit_state == CircuitBreakerState.CLOSED
        assert backend._failure_count == 0

        # Primary failure should affect circuit breaker
        await backend._record_failure(primary, error)
        assert backend._circuit_state == CircuitBreakerState.CLOSED
        assert backend._failure_count == 1

    @pytest.mark.asyncio
    async def test_record_failure_non_circuit_breaker_strategy(self) -> None:
        """Test that _record_failure doesn't affect circuit with non-circuit breaker strategies."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        strategies = [SwitchingStrategy.FAIL_FAST, SwitchingStrategy.HEALTH_CHECK]

        for strategy in strategies:
            backend = CompositeLimiterBackend(
                primary=primary,
                fallback=fallback,
                strategy=strategy,
                failure_threshold=1,  # Low threshold
            )

            error = LimiterBackendError("Test error")

            # Primary failure should not affect circuit breaker
            await backend._record_failure(primary, error)
            assert backend._circuit_state == CircuitBreakerState.CLOSED
            assert backend._failure_count == 0

    @patch("time.time")
    @pytest.mark.asyncio
    async def test_record_failure_updates_timestamp(self, mock_time) -> None:
        """Test that _record_failure updates last failure timestamp."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        test_time = 12345.67
        mock_time.return_value = test_time

        error = LimiterBackendError("Test error")
        await backend._record_failure(primary, error)

        assert backend._last_failure_time == test_time


class TestCircuitBreakerSuccessHandling:
    """Test circuit breaker success handling logic."""

    @pytest.mark.asyncio
    async def test_record_success_resets_failure_count_in_closed_state(self) -> None:
        """Test that _record_success resets failure count in CLOSED state."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Set some failures in CLOSED state
        backend._circuit_state = CircuitBreakerState.CLOSED
        backend._failure_count = 3

        # Record success
        await backend._record_success(primary)

        assert backend._circuit_state == CircuitBreakerState.CLOSED
        assert backend._failure_count == 0

    @pytest.mark.asyncio
    async def test_record_success_from_fallback(self) -> None:
        """Test that _record_success from fallback doesn't affect circuit."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Set circuit to HALF_OPEN
        backend._circuit_state = CircuitBreakerState.HALF_OPEN
        backend._failure_count = 3

        # Record success from fallback (shouldn't change circuit)
        await backend._record_success(fallback)

        assert backend._circuit_state == CircuitBreakerState.HALF_OPEN
        assert backend._failure_count == 3

    @patch("time.time")
    @pytest.mark.asyncio
    async def test_record_success_updates_timestamp(self, mock_time) -> None:
        """Test that _record_success updates last success timestamp."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        test_time = 98765.43
        mock_time.return_value = test_time

        await backend._record_success(primary)

        assert backend._last_success_time == test_time


class TestCircuitBreakerManualControl:
    """Test manual circuit breaker control functions."""

    @pytest.mark.asyncio
    async def test_force_switch_to_primary(self) -> None:
        """Test manual force switch to primary backend."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        )

        # Set circuit to OPEN state
        backend._circuit_state = CircuitBreakerState.OPEN
        backend._failure_count = 10

        # Force switch to primary
        await backend.force_switch_to_primary()

        assert backend._circuit_state == CircuitBreakerState.CLOSED
        assert backend._failure_count == 0

    @pytest.mark.asyncio
    async def test_force_switch_to_fallback(self) -> None:
        """Test manual force switch to fallback backend."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        )

        # Start in CLOSED state
        assert backend._circuit_state == CircuitBreakerState.CLOSED

        # Force switch to fallback
        await backend.force_switch_to_fallback()

        assert backend._circuit_state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_force_switch_non_circuit_breaker_strategy(self) -> None:
        """Test that manual switching doesn't affect non-circuit breaker strategies."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        strategies = [SwitchingStrategy.FAIL_FAST, SwitchingStrategy.HEALTH_CHECK]

        for strategy in strategies:
            backend = CompositeLimiterBackend(
                primary=primary,
                fallback=fallback,
                strategy=strategy,
            )

            original_state = backend._circuit_state
            original_count = backend._failure_count

            # Try to force switch
            await backend.force_switch_to_primary()
            await backend.force_switch_to_fallback()

            # Should not change for non-circuit breaker strategies
            assert backend._circuit_state == original_state
            assert backend._failure_count == original_count


class TestCircuitBreakerTimingBehavior:
    """Test circuit breaker timing and timeout behavior."""

    @patch("time.time")
    def test_recovery_timeout_calculation(self, mock_time) -> None:
        """Test recovery timeout calculation logic."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            recovery_timeout_seconds=120,
        )

        # Set failure time
        failure_time = 1000.0
        backend._last_failure_time = failure_time
        backend._circuit_state = CircuitBreakerState.OPEN

        # Test within timeout
        mock_time.return_value = failure_time + 60  # 60 seconds later
        result = backend._select_circuit_breaker()
        assert backend._circuit_state == CircuitBreakerState.OPEN
        assert result is fallback

        # Test at timeout boundary
        mock_time.return_value = failure_time + 120  # Exactly 120 seconds later
        result = backend._select_circuit_breaker()
        assert backend._circuit_state == CircuitBreakerState.HALF_OPEN
        assert result is primary

        # Test after timeout
        mock_time.return_value = failure_time + 180  # 180 seconds later
        backend._circuit_state = CircuitBreakerState.OPEN  # Reset for test
        result = backend._select_circuit_breaker()
        assert backend._circuit_state == CircuitBreakerState.HALF_OPEN
        assert result is primary

    def test_different_recovery_timeouts(self) -> None:
        """Test circuit breaker with different recovery timeout values."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        timeouts = [1, 30, 60, 300, 3600]

        for timeout in timeouts:
            backend = CompositeLimiterBackend(
                primary=primary,
                fallback=fallback,
                recovery_timeout_seconds=timeout,
            )

            assert backend._recovery_timeout == timeout


class TestCircuitBreakerFailureThresholds:
    """Test circuit breaker failure threshold behavior."""

    @pytest.mark.asyncio
    async def test_different_failure_thresholds(self) -> None:
        """Test circuit breaker with different failure thresholds."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        thresholds = [1, 3, 5, 10, 100]

        for threshold in thresholds:
            backend = CompositeLimiterBackend(
                primary=primary,
                fallback=fallback,
                failure_threshold=threshold,
            )

            # Test failures up to threshold - 1
            error = LimiterBackendError("Test error")
            for i in range(threshold - 1):
                await backend._record_failure(primary, error)
                assert backend._circuit_state == CircuitBreakerState.CLOSED
                assert backend._failure_count == i + 1

            # One more failure should open circuit
            await backend._record_failure(primary, error)
            assert backend._circuit_state == CircuitBreakerState.OPEN
            assert backend._failure_count == threshold

    @pytest.mark.asyncio
    async def test_failure_threshold_one(self) -> None:
        """Test circuit breaker with failure threshold of 1 (fail-fast behavior)."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            failure_threshold=1,
        )

        # Single failure should open circuit
        error = LimiterBackendError("Test error")
        await backend._record_failure(primary, error)

        assert backend._circuit_state == CircuitBreakerState.OPEN
        assert backend._failure_count == 1


class TestCircuitBreakerEdgeCases:
    """Test circuit breaker edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_multiple_consecutive_failures_in_open_state(self) -> None:
        """Test multiple failures when circuit is already open."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            failure_threshold=2,
        )

        # Open the circuit
        error = LimiterBackendError("Test error")
        await backend._record_failure(primary, error)
        await backend._record_failure(primary, error)
        assert backend._circuit_state == CircuitBreakerState.OPEN

        original_count = backend._failure_count

        # Additional failures in OPEN state should still increment counter
        await backend._record_failure(primary, error)
        assert backend._circuit_state == CircuitBreakerState.OPEN
        assert backend._failure_count == original_count + 1

    @pytest.mark.asyncio
    async def test_success_in_open_state_no_effect(self) -> None:
        """Test that success in OPEN state doesn't change circuit."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Set to OPEN state
        backend._circuit_state = CircuitBreakerState.OPEN
        backend._failure_count = 5

        # Success from primary should not affect OPEN circuit
        await backend._record_success(primary)

        assert backend._circuit_state == CircuitBreakerState.OPEN
        assert backend._failure_count == 5

    @pytest.mark.asyncio
    async def test_zero_failure_threshold(self) -> None:
        """Test circuit breaker behavior with zero failure threshold."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            failure_threshold=0,
        )

        # Any failure should immediately open circuit
        error = LimiterBackendError("Test error")
        await backend._record_failure(primary, error)

        assert backend._circuit_state == CircuitBreakerState.OPEN
        assert backend._failure_count == 1
