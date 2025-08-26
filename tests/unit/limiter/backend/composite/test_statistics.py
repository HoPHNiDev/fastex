"""
Unit tests for CompositeLimiterBackend statistics and monitoring.

This module tests the statistics and monitoring functionality:
- Statistics collection and reporting
- Request/error counters
- Timestamp tracking
- Stats structure and content
- Performance metrics

Tests cover:
- Statistics structure validation
- Request counting accuracy
- Error counting accuracy
- Timestamp calculations
- Statistics reset behavior
- Monitoring data completeness
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fastex.limiter.backend.composite.composite import CompositeLimiterBackend
from fastex.limiter.backend.composite.enums import (
    CircuitBreakerState,
    SwitchingStrategy,
)
from fastex.limiter.backend.interfaces import LimiterBackend


class TestStatisticsStructure:
    """Test statistics structure and content."""

    def test_get_stats_structure(self) -> None:
        """Test that get_stats returns expected structure."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        stats = backend.get_stats()

        # Verify all expected keys are present
        expected_keys = {
            "strategy",
            "circuit_state",
            "primary_healthy",
            "fallback_healthy",
            "primary_connected",
            "fallback_connected",
            "failure_count",
            "last_failure_seconds_ago",
            "last_success_seconds_ago",
            "primary_requests",
            "fallback_requests",
            "primary_errors",
            "fallback_errors",
            "total_requests",
            "total_errors",
        }

        assert set(stats.keys()) == expected_keys

    def test_get_stats_types(self) -> None:
        """Test that get_stats returns correct data types."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        primary.is_connected.return_value = True
        fallback.is_connected.return_value = False

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.FAIL_FAST,
        )

        stats = backend.get_stats()

        # Verify data types
        assert isinstance(stats["strategy"], str)
        assert isinstance(stats["circuit_state"], str)
        assert isinstance(stats["primary_healthy"], bool)
        assert isinstance(stats["fallback_healthy"], bool)
        assert isinstance(stats["primary_connected"], bool)
        assert isinstance(stats["fallback_connected"], bool)
        assert isinstance(stats["failure_count"], int)
        assert stats["last_failure_seconds_ago"] is None or isinstance(
            stats["last_failure_seconds_ago"], int
        )
        assert stats["last_success_seconds_ago"] is None or isinstance(
            stats["last_success_seconds_ago"], int
        )
        assert isinstance(stats["primary_requests"], int)
        assert isinstance(stats["fallback_requests"], int)
        assert isinstance(stats["primary_errors"], int)
        assert isinstance(stats["fallback_errors"], int)
        assert isinstance(stats["total_requests"], int)
        assert isinstance(stats["total_errors"], int)

    def test_get_stats_initial_values(self) -> None:
        """Test get_stats with initial values."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        primary.is_connected.return_value = False
        fallback.is_connected.return_value = False

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        )

        stats = backend.get_stats()

        # Verify initial values
        assert stats["strategy"] == "circuit_breaker"
        assert stats["circuit_state"] == "closed"
        assert stats["primary_healthy"] is True
        assert stats["fallback_healthy"] is True
        assert stats["primary_connected"] is False
        assert stats["fallback_connected"] is False
        assert stats["failure_count"] == 0
        assert stats["last_failure_seconds_ago"] is None
        assert stats["last_success_seconds_ago"] is None
        assert stats["primary_requests"] == 0
        assert stats["fallback_requests"] == 0
        assert stats["primary_errors"] == 0
        assert stats["fallback_errors"] == 0
        assert stats["total_requests"] == 0
        assert stats["total_errors"] == 0


class TestRequestCountingStatistics:
    """Test request counting in statistics."""

    @pytest.mark.asyncio
    async def test_primary_request_counting(self) -> None:
        """Test that primary requests are counted correctly."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Simulate successful primary requests
        backend._primary_requests = 5

        stats = backend.get_stats()
        assert stats["primary_requests"] == 5
        assert stats["fallback_requests"] == 0
        assert stats["total_requests"] == 5

    @pytest.mark.asyncio
    async def test_fallback_request_counting(self) -> None:
        """Test that fallback requests are counted correctly."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Simulate successful fallback requests
        backend._fallback_requests = 3

        stats = backend.get_stats()
        assert stats["primary_requests"] == 0
        assert stats["fallback_requests"] == 3
        assert stats["total_requests"] == 3

    @pytest.mark.asyncio
    async def test_mixed_request_counting(self) -> None:
        """Test counting of mixed primary and fallback requests."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Simulate mixed requests
        backend._primary_requests = 7
        backend._fallback_requests = 4

        stats = backend.get_stats()
        assert stats["primary_requests"] == 7
        assert stats["fallback_requests"] == 4
        assert stats["total_requests"] == 11

    @pytest.mark.asyncio
    async def test_large_request_counts(self) -> None:
        """Test statistics with large request counts."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Simulate large numbers
        backend._primary_requests = 1000000
        backend._fallback_requests = 500000

        stats = backend.get_stats()
        assert stats["primary_requests"] == 1000000
        assert stats["fallback_requests"] == 500000
        assert stats["total_requests"] == 1500000


class TestErrorCountingStatistics:
    """Test error counting in statistics."""

    @pytest.mark.asyncio
    async def test_primary_error_counting(self) -> None:
        """Test that primary errors are counted correctly."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Simulate primary errors
        backend._primary_errors = 2

        stats = backend.get_stats()
        assert stats["primary_errors"] == 2
        assert stats["fallback_errors"] == 0
        assert stats["total_errors"] == 2

    @pytest.mark.asyncio
    async def test_fallback_error_counting(self) -> None:
        """Test that fallback errors are counted correctly."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Simulate fallback errors
        backend._fallback_errors = 1

        stats = backend.get_stats()
        assert stats["primary_errors"] == 0
        assert stats["fallback_errors"] == 1
        assert stats["total_errors"] == 1

    @pytest.mark.asyncio
    async def test_mixed_error_counting(self) -> None:
        """Test counting of mixed primary and fallback errors."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Simulate mixed errors
        backend._primary_errors = 3
        backend._fallback_errors = 2

        stats = backend.get_stats()
        assert stats["primary_errors"] == 3
        assert stats["fallback_errors"] == 2
        assert stats["total_errors"] == 5

    @pytest.mark.asyncio
    async def test_error_request_ratio(self) -> None:
        """Test error-to-request ratio in statistics."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Simulate requests and errors
        backend._primary_requests = 100
        backend._primary_errors = 5
        backend._fallback_requests = 50
        backend._fallback_errors = 2

        stats = backend.get_stats()
        assert stats["total_requests"] == 150
        assert stats["total_errors"] == 7

        # Calculate error rate
        error_rate = stats["total_errors"] / stats["total_requests"]
        assert abs(error_rate - 0.0467) < 0.001  # ~4.67%


class TestTimestampStatistics:
    """Test timestamp-related statistics."""

    @patch("time.time")
    def test_last_failure_seconds_ago_calculation(self, mock_time) -> None:
        """Test calculation of seconds since last failure."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Set failure time and current time
        failure_time = 1000.0
        current_time = 1030.5  # 30.5 seconds later

        backend._last_failure_time = failure_time
        mock_time.return_value = current_time

        stats = backend.get_stats()
        assert stats["last_failure_seconds_ago"] == 30  # Truncated to int

    @patch("time.time")
    def test_last_success_seconds_ago_calculation(self, mock_time) -> None:
        """Test calculation of seconds since last success."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Set success time and current time
        success_time = 2000.0
        current_time = 2045.8  # 45.8 seconds later

        backend._last_success_time = success_time
        mock_time.return_value = current_time

        stats = backend.get_stats()
        assert stats["last_success_seconds_ago"] == 45  # Truncated to int

    def test_no_failure_timestamp(self) -> None:
        """Test statistics when no failure has occurred."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # No failure time set
        assert backend._last_failure_time is None

        stats = backend.get_stats()
        assert stats["last_failure_seconds_ago"] is None

    def test_no_success_timestamp(self) -> None:
        """Test statistics when no success has occurred."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # No success time set
        assert backend._last_success_time is None

        stats = backend.get_stats()
        assert stats["last_success_seconds_ago"] is None

    @patch("time.time")
    def test_both_timestamps_present(self, mock_time) -> None:
        """Test statistics when both timestamps are present."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Set both timestamps
        backend._last_failure_time = 500.0
        backend._last_success_time = 600.0
        mock_time.return_value = 700.0

        stats = backend.get_stats()
        assert stats["last_failure_seconds_ago"] == 200  # 700 - 500
        assert stats["last_success_seconds_ago"] == 100  # 700 - 600


class TestCircuitBreakerStatistics:
    """Test circuit breaker related statistics."""

    def test_circuit_state_in_stats(self) -> None:
        """Test that circuit state is included in statistics."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        states = [
            CircuitBreakerState.CLOSED,
            CircuitBreakerState.OPEN,
            CircuitBreakerState.HALF_OPEN,
        ]

        for state in states:
            backend._circuit_state = state
            stats = backend.get_stats()
            assert stats["circuit_state"] == state.value

    def test_failure_count_in_stats(self) -> None:
        """Test that failure count is included in statistics."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        failure_counts = [0, 1, 5, 10, 100]

        for count in failure_counts:
            backend._failure_count = count
            stats = backend.get_stats()
            assert stats["failure_count"] == count


class TestConnectionStatistics:
    """Test connection status in statistics."""

    def test_connection_status_in_stats(self) -> None:
        """Test that connection status is included in statistics."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Test different connection combinations
        connection_scenarios = [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]

        for primary_connected, fallback_connected in connection_scenarios:
            primary.is_connected.return_value = primary_connected
            fallback.is_connected.return_value = fallback_connected

            stats = backend.get_stats()
            assert stats["primary_connected"] == primary_connected
            assert stats["fallback_connected"] == fallback_connected

    def test_health_status_in_stats(self) -> None:
        """Test that health status is included in statistics."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Test different health combinations
        health_scenarios = [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]

        for primary_healthy, fallback_healthy in health_scenarios:
            backend._primary_healthy = primary_healthy
            backend._fallback_healthy = fallback_healthy

            stats = backend.get_stats()
            assert stats["primary_healthy"] == primary_healthy
            assert stats["fallback_healthy"] == fallback_healthy


class TestStrategyStatistics:
    """Test strategy information in statistics."""

    def test_strategy_in_stats(self) -> None:
        """Test that strategy is included in statistics."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        strategies = [
            SwitchingStrategy.FAIL_FAST,
            SwitchingStrategy.CIRCUIT_BREAKER,
            SwitchingStrategy.HEALTH_CHECK,
        ]

        for strategy in strategies:
            backend = CompositeLimiterBackend(
                primary=primary,
                fallback=fallback,
                strategy=strategy,
            )

            stats = backend.get_stats()
            assert stats["strategy"] == strategy.value


class TestStatisticsConsistency:
    """Test consistency of statistics."""

    def test_total_calculations_consistency(self) -> None:
        """Test that total calculations are consistent."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Set various values
        backend._primary_requests = 42
        backend._fallback_requests = 23
        backend._primary_errors = 3
        backend._fallback_errors = 1

        stats = backend.get_stats()

        # Verify totals are calculated correctly
        assert (
            stats["total_requests"]
            == stats["primary_requests"] + stats["fallback_requests"]
        )
        assert (
            stats["total_errors"] == stats["primary_errors"] + stats["fallback_errors"]
        )
        assert stats["total_requests"] == 65
        assert stats["total_errors"] == 4

    def test_statistics_immutability(self) -> None:
        """Test that modifying returned stats doesn't affect backend."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Get stats and modify them
        stats1 = backend.get_stats()
        stats1["primary_requests"] = 999999
        stats1["strategy"] = "modified"

        # Get fresh stats
        stats2 = backend.get_stats()

        # Should not be affected by modifications
        assert stats2["primary_requests"] == 0
        assert stats2["strategy"] == "circuit_breaker"
