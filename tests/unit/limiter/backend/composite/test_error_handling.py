"""
Unit tests for CompositeLimiterBackend error handling and edge cases.

This module tests error handling scenarios and edge cases:
- Check limit error handling and fallback
- Connection/disconnection error scenarios
- Invalid configuration handling
- Boundary conditions
- Exception propagation
- Graceful degradation

Tests cover:
- Both backends failing
- Primary/fallback selection during errors
- Error statistics tracking
- Exception type handling
- Recovery from errors
- Timeout and boundary conditions
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from fastex.limiter.backend.composite.composite import CompositeLimiterBackend
from fastex.limiter.backend.composite.enums import SwitchingStrategy
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.interfaces import LimiterBackend
from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.schemas import RateLimitConfig


class TestCheckLimitErrorHandling:
    """Test error handling in check_limit method."""

    @pytest.mark.asyncio
    async def test_check_limit_not_connected_raises_error(self) -> None:
        """Test that check_limit raises error when not connected."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Don't connect
        assert backend._connected is False

        config = RateLimitConfig(times=5, seconds=60)

        with pytest.raises(
            LimiterBackendError, match="Composite backend is not connected"
        ):
            await backend.check_limit("test_key", config)

    @pytest.mark.asyncio
    async def test_check_limit_primary_fails_uses_fallback(self) -> None:
        """Test that check_limit uses fallback when primary fails."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Mock as connected
        backend._connected = True

        # Mock primary to fail
        primary_error = LimiterBackendError("Primary failed")
        primary.check_limit.side_effect = primary_error

        # Mock fallback to succeed
        fallback_result = RateLimitResult(
            is_exceeded=False,
            limit_times=5,
            retry_after_ms=0,
            remaining_requests=4,
            reset_time=None,
        )
        fallback.check_limit.return_value = fallback_result

        # Mock backend availability
        backend._is_backend_available = MagicMock(side_effect=lambda b: b == fallback)

        config = RateLimitConfig(times=5, seconds=60)
        result = await backend.check_limit("test_key", config)

        # Should return fallback result
        assert result == fallback_result

        # Verify both backends were called
        primary.check_limit.assert_called_once_with("test_key", config)
        fallback.check_limit.assert_called_once_with("test_key", config)

        # Verify error statistics
        assert backend._primary_errors == 1
        assert backend._fallback_errors == 0

    @pytest.mark.asyncio
    async def test_check_limit_fallback_fails_uses_primary(self) -> None:
        """Test that check_limit uses primary when fallback fails."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.FAIL_FAST,  # Will try fallback first if primary unavailable
        )

        # Mock as connected
        backend._connected = True

        # Mock fallback to fail
        fallback_error = LimiterBackendError("Fallback failed")
        fallback.check_limit.side_effect = fallback_error

        # Mock primary to succeed
        primary_result = RateLimitResult(
            is_exceeded=False,
            limit_times=5,
            retry_after_ms=0,
            remaining_requests=4,
            reset_time=None,
        )
        primary.check_limit.return_value = primary_result

        # Mock backend selection to choose fallback first
        backend._select_backend = MagicMock(return_value=fallback)
        backend._is_backend_available = MagicMock(side_effect=lambda b: b == primary)

        config = RateLimitConfig(times=5, seconds=60)
        result = await backend.check_limit("test_key", config)

        # Should return primary result
        assert result == primary_result

        # Verify both backends were called
        fallback.check_limit.assert_called_once_with("test_key", config)
        primary.check_limit.assert_called_once_with("test_key", config)

    @pytest.mark.asyncio
    async def test_check_limit_both_backends_fail(self) -> None:
        """Test that check_limit raises error when both backends fail."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Mock as connected
        backend._connected = True

        # Mock both to fail
        primary_error = LimiterBackendError("Primary failed")
        fallback_error = LimiterBackendError("Fallback failed")

        primary.check_limit.side_effect = primary_error
        fallback.check_limit.side_effect = fallback_error

        # Mock both backends as available
        backend._is_backend_available = MagicMock(return_value=True)

        config = RateLimitConfig(times=5, seconds=60)

        with pytest.raises(LimiterBackendError, match="Both backends failed"):
            await backend.check_limit("test_key", config)

        # Verify both backends were called
        primary.check_limit.assert_called_once_with("test_key", config)
        fallback.check_limit.assert_called_once_with("test_key", config)

        # Verify error statistics
        assert backend._primary_errors == 1
        # Note: fallback errors are tracked differently - they're only counted
        # when fallback is the selected backend, not when used as fallback
        assert backend._fallback_errors == 0

    @pytest.mark.asyncio
    async def test_check_limit_no_healthy_backend_available(self) -> None:
        """Test check_limit when no healthy backend is available."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Mock as connected
        backend._connected = True

        # Mock primary to fail
        primary_error = LimiterBackendError("Primary failed")
        primary.check_limit.side_effect = primary_error

        # Mock no backends as available
        backend._is_backend_available = MagicMock(return_value=False)

        config = RateLimitConfig(times=5, seconds=60)

        with pytest.raises(
            LimiterBackendError,
            match="primary backend failed and no healthy alternative",
        ):
            await backend.check_limit("test_key", config)

        # Verify only primary was called
        primary.check_limit.assert_called_once_with("test_key", config)
        fallback.check_limit.assert_not_called()


class TestConnectionErrorHandling:
    """Test error handling during connection/disconnection."""

    @pytest.mark.asyncio
    async def test_safe_disconnect_handles_exceptions(self) -> None:
        """Test that _safe_disconnect handles exceptions gracefully."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Make disconnect raise exception
        disconnect_error = Exception("Disconnect failed")
        primary.disconnect.side_effect = disconnect_error

        # Should not raise exception
        await backend._safe_disconnect(primary, "primary")

        # Should have been called
        primary.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_handles_multiple_backend_failures(self) -> None:
        """Test that disconnect handles multiple backend failures gracefully."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Connect first
        await backend.connect()

        # Make both disconnects fail
        primary.disconnect.side_effect = Exception("Primary disconnect failed")
        fallback.disconnect.side_effect = Exception("Fallback disconnect failed")

        # Should not raise exception
        await backend.disconnect()

        # Both should have been called
        primary.disconnect.assert_called_once()
        fallback.disconnect.assert_called_once()

        # Should be marked as disconnected
        assert backend._connected is False


class TestEdgeCasesAndBoundaryConditions:
    """Test edge cases and boundary conditions."""

    def test_zero_failure_threshold_edge_case(self) -> None:
        """Test behavior with zero failure threshold."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            failure_threshold=0,
        )

        # Should accept zero threshold
        assert backend._failure_threshold == 0

    def test_zero_recovery_timeout_edge_case(self) -> None:
        """Test behavior with zero recovery timeout."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            recovery_timeout_seconds=0,
        )

        # Should accept zero timeout
        assert backend._recovery_timeout == 0

    def test_zero_health_check_interval_edge_case(self) -> None:
        """Test behavior with zero health check interval."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            health_check_interval_seconds=0,
        )

        # Should accept zero interval
        assert backend._health_check_interval == 0

    def test_extremely_large_values_edge_case(self) -> None:
        """Test behavior with extremely large configuration values."""
        primary = MagicMock(spec=LimiterBackend)
        fallback = MagicMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            failure_threshold=1000000,
            recovery_timeout_seconds=86400 * 365,  # 1 year
            health_check_interval_seconds=3600 * 24,  # 1 day
        )

        # Should accept large values
        assert backend._failure_threshold == 1000000
        assert backend._recovery_timeout == 86400 * 365
        assert backend._health_check_interval == 3600 * 24

    @pytest.mark.asyncio
    async def test_concurrent_check_limit_calls(self) -> None:
        """Test concurrent check_limit calls."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Mock as connected
        backend._connected = True

        # Mock primary to succeed with delay
        async def delayed_check(key, config):
            await asyncio.sleep(0.1)
            return RateLimitResult(
                is_exceeded=False,
                limit_times=5,
                retry_after_ms=0,
                remaining_requests=4,
                reset_time=None,
            )

        primary.check_limit.side_effect = delayed_check

        config = RateLimitConfig(times=5, seconds=60)

        # Make concurrent calls
        tasks = [
            backend.check_limit("key1", config),
            backend.check_limit("key2", config),
            backend.check_limit("key3", config),
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 3
        assert all(not result.is_exceeded for result in results)

        # Should have made 3 primary calls
        assert primary.check_limit.call_count == 3


class TestExceptionTypeHandling:
    """Test handling of different exception types."""

    @pytest.mark.asyncio
    async def test_limiter_backend_error_handling(self) -> None:
        """Test handling of LimiterBackendError specifically."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        backend._connected = True

        # Use specific LimiterBackendError
        specific_error = LimiterBackendError("Specific backend error")
        primary.check_limit.side_effect = specific_error

        # Mock successful fallback
        fallback_result = RateLimitResult(
            is_exceeded=False,
            limit_times=5,
            retry_after_ms=0,
            remaining_requests=4,
            reset_time=None,
        )
        fallback.check_limit.return_value = fallback_result
        backend._is_backend_available = MagicMock(side_effect=lambda b: b == fallback)

        config = RateLimitConfig(times=5, seconds=60)
        result = await backend.check_limit("test_key", config)

        # Should handle error and use fallback
        assert result == fallback_result

    @pytest.mark.asyncio
    async def test_generic_exception_handling(self) -> None:
        """Test handling of generic exceptions."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        backend._connected = True

        # Use generic exception
        generic_error = ValueError("Generic error")
        primary.check_limit.side_effect = generic_error

        # Mock successful fallback
        fallback_result = RateLimitResult(
            is_exceeded=False,
            limit_times=5,
            retry_after_ms=0,
            remaining_requests=4,
            reset_time=None,
        )
        fallback.check_limit.return_value = fallback_result
        backend._is_backend_available = MagicMock(side_effect=lambda b: b == fallback)

        config = RateLimitConfig(times=5, seconds=60)
        result = await backend.check_limit("test_key", config)

        # Should handle error and use fallback
        assert result == fallback_result

    @pytest.mark.asyncio
    async def test_asyncio_exception_handling(self) -> None:
        """Test handling of asyncio-related exceptions."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        backend._connected = True

        # Use asyncio timeout error
        timeout_error = asyncio.TimeoutError("Operation timed out")
        primary.check_limit.side_effect = timeout_error

        # Mock successful fallback
        fallback_result = RateLimitResult(
            is_exceeded=False,
            limit_times=5,
            retry_after_ms=0,
            remaining_requests=4,
            reset_time=None,
        )
        fallback.check_limit.return_value = fallback_result
        backend._is_backend_available = MagicMock(side_effect=lambda b: b == fallback)

        config = RateLimitConfig(times=5, seconds=60)
        result = await backend.check_limit("test_key", config)

        # Should handle error and use fallback
        assert result == fallback_result


class TestErrorStatisticsAccuracy:
    """Test accuracy of error statistics during error conditions."""

    @pytest.mark.asyncio
    async def test_error_statistics_increment_correctly(self) -> None:
        """Test that error statistics increment correctly during errors."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        backend._connected = True

        # Mock primary to fail
        primary.check_limit.side_effect = LimiterBackendError("Primary failed")
        fallback.check_limit.return_value = RateLimitResult(
            is_exceeded=False,
            limit_times=5,
            retry_after_ms=0,
            remaining_requests=4,
            reset_time=None,
        )
        backend._is_backend_available = MagicMock(side_effect=lambda b: b == fallback)

        config = RateLimitConfig(times=5, seconds=60)

        # Initial statistics
        assert backend._primary_errors == 0
        assert backend._fallback_errors == 0

        # First error
        await backend.check_limit("key1", config)
        assert backend._primary_errors == 1
        assert backend._fallback_errors == 0
        assert backend._fallback_requests == 1  # Successful fallback

        # Second error
        await backend.check_limit("key2", config)
        assert backend._primary_errors == 2
        assert backend._fallback_errors == 0
        assert backend._fallback_requests == 2

    @pytest.mark.asyncio
    async def test_error_statistics_with_both_backend_failures(self) -> None:
        """Test error statistics when both backends fail."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        backend._connected = True

        # Mock both to fail
        primary.check_limit.side_effect = LimiterBackendError("Primary failed")
        fallback.check_limit.side_effect = LimiterBackendError("Fallback failed")
        backend._is_backend_available = MagicMock(return_value=True)

        config = RateLimitConfig(times=5, seconds=60)

        # Should raise error but track statistics
        with pytest.raises(LimiterBackendError):
            await backend.check_limit("key1", config)

        # Both should have error counts
        assert backend._primary_errors == 1
        # Note: fallback errors are only counted when fallback is selected,
        # not when used as secondary option after primary failure
        assert backend._fallback_errors == 0
        assert backend._primary_requests == 0  # No successful requests
        assert backend._fallback_requests == 0


class TestRecoveryScenarios:
    """Test recovery scenarios after errors."""

    @pytest.mark.asyncio
    async def test_recovery_after_primary_failure(self) -> None:
        """Test recovery behavior after primary backend failure."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        backend._connected = True

        # First call - primary fails
        primary.check_limit.side_effect = LimiterBackendError("Primary failed")
        fallback.check_limit.return_value = RateLimitResult(
            is_exceeded=False,
            limit_times=5,
            retry_after_ms=0,
            remaining_requests=4,
            reset_time=None,
        )
        backend._is_backend_available = MagicMock(side_effect=lambda b: b == fallback)

        config = RateLimitConfig(times=5, seconds=60)
        result1 = await backend.check_limit("key1", config)

        # Should use fallback
        assert not result1.is_exceeded
        assert backend._primary_errors == 1

        # Second call - primary recovers
        primary.check_limit.side_effect = None  # Clear the error
        primary.check_limit.return_value = RateLimitResult(
            is_exceeded=False,
            limit_times=5,
            retry_after_ms=0,
            remaining_requests=4,
            reset_time=None,
        )
        backend._is_backend_available = MagicMock(return_value=True)

        # Reset selection to prefer primary
        backend._select_backend = MagicMock(return_value=primary)

        result2 = await backend.check_limit("key2", config)

        # Should use primary again
        assert not result2.is_exceeded
        assert backend._primary_requests == 1  # Now has successful request
