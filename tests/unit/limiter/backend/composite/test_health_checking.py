"""
Unit tests for CompositeLimiterBackend health checking functionality.

This module tests the health checking capabilities:
- Health check task lifecycle
- Health status monitoring
- Health-based backend selection
- Health check intervals
- Error handling in health checks

Tests cover:
- Health check task start/stop
- Periodic health checking
- Health status updates
- Backend availability monitoring
- Health check error handling
- Task cancellation and cleanup
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from fastex.limiter.backend.composite.composite import CompositeLimiterBackend
from fastex.limiter.backend.composite.enums import SwitchingStrategy
from fastex.limiter.backend.interfaces import LimiterBackend


class TestHealthCheckTaskLifecycle:
    """Test health check task lifecycle management."""

    @pytest.mark.asyncio
    async def test_health_check_task_started_with_health_check_strategy(self) -> None:
        """Test that health check task is started with HEALTH_CHECK strategy."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=0.1,  # Fast for testing
        )

        # Connect should start health check task
        await backend.connect()

        assert backend._health_check_task is not None
        assert not backend._health_check_task.done()

        # Cleanup
        await backend.disconnect()

    @pytest.mark.asyncio
    async def test_health_check_task_not_started_with_other_strategies(self) -> None:
        """Test that health check task is not started with non-HEALTH_CHECK strategies."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        strategies = [SwitchingStrategy.FAIL_FAST, SwitchingStrategy.CIRCUIT_BREAKER]

        for strategy in strategies:
            backend = CompositeLimiterBackend(
                primary=primary,
                fallback=fallback,
                strategy=strategy,
            )

            # Connect should not start health check task
            await backend.connect()

            assert backend._health_check_task is None

            # Cleanup
            await backend.disconnect()

    @pytest.mark.asyncio
    async def test_health_check_task_cancelled_on_disconnect(self) -> None:
        """Test that health check task is cancelled on disconnect."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=0.1,
        )

        # Connect starts task
        await backend.connect()
        task = backend._health_check_task
        assert task is not None
        assert not task.done()

        # Disconnect should cancel task
        await backend.disconnect()

        # Task should be cancelled or done
        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_health_check_task_stops_when_disconnected(self) -> None:
        """Test that health check loop stops when backend is disconnected."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=0.1,
        )

        # Mock _perform_health_checks to track calls
        call_count = 0
        original_perform = backend._perform_health_checks

        async def counting_perform():
            nonlocal call_count
            call_count += 1
            await original_perform()

        backend._perform_health_checks = counting_perform

        # Connect and wait for some health checks
        await backend.connect()
        await asyncio.sleep(0.3)  # Allow multiple health checks

        # Disconnect should stop health checking
        await backend.disconnect()

        # Task should complete
        assert backend._health_check_task.done()

        # Should have made at least one health check call
        assert call_count > 0


class TestHealthCheckPerformance:
    """Test health check performance and timing."""

    @pytest.mark.asyncio
    async def test_health_check_interval_respected(self) -> None:
        """Test that health check interval is respected."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Use a longer interval for timing test
        interval = 0.2
        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=interval,
        )

        # Mock _perform_health_checks to track timing
        call_times = []

        async def timing_perform():
            call_times.append(asyncio.get_event_loop().time())

        backend._perform_health_checks = timing_perform

        # Connect and wait for multiple health checks
        await backend.connect()
        await asyncio.sleep(0.6)  # Should allow ~3 calls
        await backend.disconnect()

        # Should have made multiple calls
        assert len(call_times) >= 2

        # Check intervals between calls
        for i in range(1, len(call_times)):
            interval_actual = call_times[i] - call_times[i - 1]
            # Allow some tolerance for timing
            assert interval_actual >= interval * 0.8  # 20% tolerance

    @pytest.mark.asyncio
    async def test_health_check_with_different_intervals(self) -> None:
        """Test health checking with different interval values."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        intervals = [0.1, 0.5, 1.0]

        for interval in intervals:
            backend = CompositeLimiterBackend(
                primary=primary,
                fallback=fallback,
                strategy=SwitchingStrategy.HEALTH_CHECK,
                health_check_interval_seconds=interval,
            )

            assert backend._health_check_interval == interval

            # Connect and verify task starts
            await backend.connect()
            assert backend._health_check_task is not None

            # Cleanup
            await backend.disconnect()


class TestHealthStatusMonitoring:
    """Test health status monitoring and updates."""

    @pytest.mark.asyncio
    async def test_perform_health_checks_updates_status(self) -> None:
        """Test that _perform_health_checks updates backend health status."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Mock backend connection states
        primary.is_connected.return_value = True
        fallback.is_connected.return_value = False

        # Perform health checks
        await backend._perform_health_checks()

        # Verify health status updated
        assert backend._primary_healthy is True
        assert backend._fallback_healthy is False

    @pytest.mark.asyncio
    async def test_perform_health_checks_both_healthy(self) -> None:
        """Test health checks when both backends are healthy."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Mock both as connected
        primary.is_connected.return_value = True
        fallback.is_connected.return_value = True

        await backend._perform_health_checks()

        assert backend._primary_healthy is True
        assert backend._fallback_healthy is True

    @pytest.mark.asyncio
    async def test_perform_health_checks_both_unhealthy(self) -> None:
        """Test health checks when both backends are unhealthy."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Mock both as disconnected
        primary.is_connected.return_value = False
        fallback.is_connected.return_value = False

        await backend._perform_health_checks()

        assert backend._primary_healthy is False
        assert backend._fallback_healthy is False

    @pytest.mark.asyncio
    async def test_perform_health_checks_primary_throws_exception(self) -> None:
        """Test health checks when primary backend throws exception."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Make primary throw exception
        primary.is_connected.side_effect = Exception("Primary health check failed")
        fallback.is_connected.return_value = True

        # Should not raise exception
        await backend._perform_health_checks()

        assert backend._primary_healthy is False
        assert backend._fallback_healthy is True

    @pytest.mark.asyncio
    async def test_perform_health_checks_fallback_throws_exception(self) -> None:
        """Test health checks when fallback backend throws exception."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Make fallback throw exception
        primary.is_connected.return_value = True
        fallback.is_connected.side_effect = Exception("Fallback health check failed")

        # Should not raise exception
        await backend._perform_health_checks()

        assert backend._primary_healthy is True
        assert backend._fallback_healthy is False

    @pytest.mark.asyncio
    async def test_perform_health_checks_both_throw_exceptions(self) -> None:
        """Test health checks when both backends throw exceptions."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Make both throw exceptions
        primary.is_connected.side_effect = Exception("Primary health check failed")
        fallback.is_connected.side_effect = Exception("Fallback health check failed")

        # Should not raise exception
        await backend._perform_health_checks()

        assert backend._primary_healthy is False
        assert backend._fallback_healthy is False


class TestHealthCheckBasedSelection:
    """Test backend selection based on health status."""

    def test_select_health_check_prefers_healthy_primary(self) -> None:
        """Test that health check strategy prefers healthy primary."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        primary.is_connected.return_value = True
        fallback.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
        )

        # Both healthy - should prefer primary
        backend._primary_healthy = True
        backend._fallback_healthy = True

        selected = backend._select_health_check()
        assert selected is primary

    def test_select_health_check_fallback_when_primary_unhealthy(self) -> None:
        """Test that health check strategy selects fallback when primary unhealthy."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        primary.is_connected.return_value = False
        fallback.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
        )

        # Primary unhealthy, fallback healthy
        backend._primary_healthy = False
        backend._fallback_healthy = True

        selected = backend._select_health_check()
        assert selected is fallback

    def test_select_health_check_both_unhealthy_prefers_primary(self) -> None:
        """Test that health check strategy prefers primary when both unhealthy."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        primary.is_connected.return_value = False
        fallback.is_connected.return_value = False

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
        )

        # Both unhealthy - should prefer primary
        backend._primary_healthy = False
        backend._fallback_healthy = False

        selected = backend._select_health_check()
        assert selected is primary


class TestHealthCheckErrorHandling:
    """Test error handling in health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_loop_handles_general_exceptions(self) -> None:
        """Test that health check loop handles general exceptions gracefully."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=0.1,
        )

        # Mock _perform_health_checks to raise exception once
        call_count = 0
        original_perform = backend._perform_health_checks

        async def error_perform():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Health check error")
            await original_perform()

        backend._perform_health_checks = error_perform

        # Connect and wait - should handle exception and continue
        await backend.connect()
        await asyncio.sleep(0.3)  # Allow multiple health checks
        await backend.disconnect()

        # Should have made multiple calls despite the error
        assert call_count > 1

    @pytest.mark.asyncio
    async def test_health_check_loop_handles_cancelled_error(self) -> None:
        """Test that health check loop handles CancelledError properly."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=0.1,
        )

        # Connect and then immediately disconnect
        await backend.connect()
        task = backend._health_check_task

        # Cancel the task directly
        task.cancel()

        # Wait for task to complete
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Task should be cancelled
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_health_check_loop_exits_when_disconnected(self) -> None:
        """Test that health check loop exits when backend is disconnected."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=0.1,
        )

        loop_iterations = 0

        # Override the health check loop to count iterations
        async def counting_loop():
            nonlocal loop_iterations
            while backend._connected:
                loop_iterations += 1
                await asyncio.sleep(backend._health_check_interval)
                if not backend._connected:
                    break
                await backend._perform_health_checks()

        backend._health_check_loop = counting_loop

        # Connect, wait, then disconnect
        await backend.connect()
        await asyncio.sleep(0.3)
        await backend.disconnect()

        # Should have made some iterations
        assert loop_iterations > 0

        # Loop should have exited
        assert backend._health_check_task.done()


class TestHealthCheckInitialState:
    """Test health check initial state and configuration."""

    def test_initial_health_state(self) -> None:
        """Test that backends start in healthy state."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Both should start as healthy
        assert backend._primary_healthy is True
        assert backend._fallback_healthy is True

    def test_health_check_interval_configuration(self) -> None:
        """Test health check interval configuration."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        custom_interval = 45
        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            health_check_interval_seconds=custom_interval,
        )

        assert backend._health_check_interval == custom_interval

    @pytest.mark.asyncio
    async def test_health_status_in_stats(self) -> None:
        """Test that health status is included in statistics."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Set different health states
        backend._primary_healthy = True
        backend._fallback_healthy = False

        stats = backend.get_stats()

        assert "primary_healthy" in stats
        assert "fallback_healthy" in stats
        assert stats["primary_healthy"] is True
        assert stats["fallback_healthy"] is False
