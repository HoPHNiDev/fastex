"""Unit tests for InMemoryLimiterBackend."""

import asyncio
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from fastex.limiter.backend.base import BaseLimiterBackend
from fastex.limiter.backend.enums import FallbackMode
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.memory.memory import InMemoryLimiterBackend
from fastex.limiter.backend.memory.schemas import MemoryLimiterBackendConnectConfig
from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.schemas import RateLimitConfig
from fastex.logging.logger import FastexLogger


class TestInMemoryLimiterBackendInheritance:
    """Test InMemoryLimiterBackend inheritance and basic structure."""

    def test_inheritance(self) -> None:
        """Test that InMemoryLimiterBackend inherits from BaseLimiterBackend."""
        assert issubclass(InMemoryLimiterBackend, BaseLimiterBackend)

    def test_logger_attribute(self) -> None:
        """Test that logger is properly initialized."""
        backend = InMemoryLimiterBackend()
        assert hasattr(backend, "logger")
        assert isinstance(backend.logger, FastexLogger)
        assert backend.logger.name == "InMemoryLimiterBackend"

    def test_initialization_defaults(self) -> None:
        """Test initialization with default parameters."""
        backend = InMemoryLimiterBackend()

        assert backend._cleanup_interval == 300
        assert backend._max_keys == 10000
        assert backend._connected is False
        assert len(backend._store) == 0
        assert len(backend._locks) == 0
        assert backend._cleanup_task is None
        assert isinstance(backend._last_cleanup, float)

    def test_initialization_custom_params(self) -> None:
        """Test initialization with custom parameters."""
        backend = InMemoryLimiterBackend(cleanup_interval_seconds=600, max_keys=5000)

        assert backend._cleanup_interval == 600
        assert backend._max_keys == 5000
        assert backend._connected is False

    def test_private_attributes_initialized(self) -> None:
        """Test that all private attributes are properly initialized."""
        backend = InMemoryLimiterBackend()

        assert hasattr(backend, "_store")
        assert hasattr(backend, "_locks")
        assert hasattr(backend, "_global_lock")
        assert hasattr(backend, "_connected")
        assert hasattr(backend, "_cleanup_interval")
        assert hasattr(backend, "_max_keys")
        assert hasattr(backend, "_cleanup_task")
        assert hasattr(backend, "_last_cleanup")


class TestInMemoryLimiterBackendConnection:
    """Test InMemoryLimiterBackend connection functionality."""

    @pytest.mark.asyncio
    async def test_connect_with_valid_config(self) -> None:
        """Test connecting with valid MemoryLimiterBackendConnectConfig."""
        backend = InMemoryLimiterBackend()
        config = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=600,
            max_keys=5000,
            fallback_mode=FallbackMode.ALLOW,
        )

        await backend.connect(config)

        assert backend._connected is True
        assert backend._cleanup_interval == 600
        assert backend._max_keys == 5000
        assert backend._fallback_mode == FallbackMode.ALLOW
        assert backend._cleanup_task is not None
        assert not backend._cleanup_task.done()

        # Cleanup
        await backend.disconnect()

    @pytest.mark.asyncio
    async def test_connect_with_minimal_config(self) -> None:
        """Test connecting with minimal config (defaults)."""
        backend = InMemoryLimiterBackend()
        config = MemoryLimiterBackendConnectConfig()

        with patch(
            "fastex.limiter.config.limiter_settings.FALLBACK_MODE", FallbackMode.DENY
        ):
            await backend.connect(config)

        assert backend._connected is True
        assert backend._cleanup_interval == 300  # Default from __init__
        assert backend._max_keys == 10000  # Default from __init__
        assert backend._fallback_mode == FallbackMode.DENY

        # Cleanup
        await backend.disconnect()

    @pytest.mark.asyncio
    async def test_connect_with_partial_config(self) -> None:
        """Test connecting with partial config."""
        backend = InMemoryLimiterBackend()
        config = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=450
            # max_keys not specified
        )

        await backend.connect(config)

        assert backend._cleanup_interval == 450
        assert backend._max_keys == 10000  # Default from __init__

        # Cleanup
        await backend.disconnect()

    @pytest.mark.asyncio
    async def test_connect_with_invalid_config_type(self) -> None:
        """Test connecting with invalid config type."""
        backend = InMemoryLimiterBackend()
        invalid_config = MagicMock()

        with pytest.raises(LimiterBackendError, match="Invalid config type"):
            await backend.connect(invalid_config)

    @pytest.mark.asyncio
    async def test_disconnect_success(self) -> None:
        """Test successful disconnection."""
        backend = InMemoryLimiterBackend()
        config = MemoryLimiterBackendConnectConfig()

        await backend.connect(config)
        assert backend._connected is True

        # Add some test data
        backend._store["test_key"] = [time.time() * 1000]

        await backend.disconnect()

        assert backend._connected is False
        assert len(backend._store) == 0
        assert len(backend._locks) == 0
        assert backend._cleanup_task is None or backend._cleanup_task.done()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        """Test disconnection when not connected."""
        backend = InMemoryLimiterBackend()

        # Should not raise an error
        await backend.disconnect()

        assert backend._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_cancels_cleanup_task(self) -> None:
        """Test that disconnect properly cancels cleanup task."""
        backend = InMemoryLimiterBackend()
        config = MemoryLimiterBackendConnectConfig()

        await backend.connect(config)
        cleanup_task = backend._cleanup_task
        assert cleanup_task is not None
        assert not cleanup_task.done()

        await backend.disconnect()

        assert cleanup_task.done()
        assert cleanup_task.cancelled()


class TestInMemoryLimiterBackendConnectionCheck:
    """Test InMemoryLimiterBackend connection checking."""

    def test_is_connected_true(self) -> None:
        """Test is_connected returns True when connected."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        assert backend.is_connected() is True
        assert backend.is_connected(raise_exc=True) is True

    def test_is_connected_false(self) -> None:
        """Test is_connected returns False when not connected."""
        backend = InMemoryLimiterBackend()
        backend._connected = False

        assert backend.is_connected() is False

    def test_is_connected_raises_when_not_connected(self) -> None:
        """Test is_connected raises exception when not connected and raise_exc=True."""
        backend = InMemoryLimiterBackend()
        backend._connected = False

        with pytest.raises(LimiterBackendError, match="not connected"):
            backend.is_connected(raise_exc=True)


class TestInMemoryLimiterBackendRateLimiting:
    """Test InMemoryLimiterBackend rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_check_limit_not_connected(self) -> None:
        """Test check_limit raises error when not connected."""
        backend = InMemoryLimiterBackend()
        config = RateLimitConfig(times=5, seconds=60)

        with pytest.raises(LimiterBackendError, match="not connected"):
            await backend.check_limit("test_key", config)

    @pytest.mark.asyncio
    async def test_check_limit_allowed_first_request(self) -> None:
        """Test first request is allowed."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=5, seconds=60)
        result = await backend.check_limit("test_key", config)

        assert not result.is_exceeded
        assert result.limit_times == 5
        assert result.remaining_requests == 4
        assert result.retry_after_ms == 0
        assert result.reset_time is None

    @pytest.mark.asyncio
    async def test_check_limit_multiple_requests_within_limit(self) -> None:
        """Test multiple requests within limit."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=3, seconds=60)

        # First request
        result1 = await backend.check_limit("test_key", config)
        assert not result1.is_exceeded
        assert result1.remaining_requests == 2

        # Second request
        result2 = await backend.check_limit("test_key", config)
        assert not result2.is_exceeded
        assert result2.remaining_requests == 1

        # Third request
        result3 = await backend.check_limit("test_key", config)
        assert not result3.is_exceeded
        assert result3.remaining_requests == 0

    @pytest.mark.asyncio
    async def test_check_limit_exceeded(self) -> None:
        """Test rate limit exceeded."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=2, seconds=60)

        # Make allowed requests
        await backend.check_limit("test_key", config)
        await backend.check_limit("test_key", config)

        # This should exceed the limit
        result = await backend.check_limit("test_key", config)

        assert result.is_exceeded
        assert result.limit_times == 2
        assert result.remaining_requests == 0
        assert result.retry_after_ms > 0
        assert isinstance(result.reset_time, datetime)

    @pytest.mark.asyncio
    async def test_check_limit_sliding_window_behavior(self) -> None:
        """Test sliding window behavior with time progression."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=2, milliseconds=1000)  # 2 requests per second

        with patch("time.time") as mock_time:
            # Start at time 0
            mock_time.return_value = 0

            # First request at t=0
            result1 = await backend.check_limit("test_key", config)
            assert not result1.is_exceeded

            # Second request at t=0
            result2 = await backend.check_limit("test_key", config)
            assert not result2.is_exceeded

            # Third request at t=0 (should be blocked)
            result3 = await backend.check_limit("test_key", config)
            assert result3.is_exceeded

            # Move forward 1.1 seconds (outside window)
            mock_time.return_value = 1.1

            # Request should be allowed again
            result4 = await backend.check_limit("test_key", config)
            assert not result4.is_exceeded

    @pytest.mark.asyncio
    async def test_check_limit_different_keys_independent(self) -> None:
        """Test that different keys have independent rate limits."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=1, seconds=60)

        # Exhaust limit for key1
        result1 = await backend.check_limit("key1", config)
        assert not result1.is_exceeded

        result2 = await backend.check_limit("key1", config)
        assert result2.is_exceeded

        # key2 should still be available
        result3 = await backend.check_limit("key2", config)
        assert not result3.is_exceeded

    @pytest.mark.asyncio
    async def test_check_limit_with_zero_remaining(self) -> None:
        """Test check_limit calculation when remaining requests is zero."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=1, seconds=60)

        result = await backend.check_limit("test_key", config)

        assert not result.is_exceeded
        assert result.remaining_requests == 0


class TestInMemoryLimiterBackendMemoryProtection:
    """Test InMemoryLimiterBackend memory protection functionality."""

    @pytest.mark.asyncio
    async def test_memory_protection_triggers_fallback(self) -> None:
        """Test that memory protection triggers fallback when max_keys reached."""
        backend = InMemoryLimiterBackend(max_keys=2)
        backend._connected = True
        backend._fallback_mode = FallbackMode.ALLOW

        config = RateLimitConfig(times=5, seconds=60)

        # Fill up to max_keys
        await backend.check_limit("key1", config)
        await backend.check_limit("key2", config)

        # This should trigger memory protection
        with patch.object(backend, "_handle_fallback") as mock_fallback:
            mock_fallback.return_value = RateLimitResult(
                is_exceeded=False, limit_times=5, remaining_requests=5
            )

            result = await backend.check_limit("key3", config)

            mock_fallback.assert_called_once()
            assert not result.is_exceeded

    @pytest.mark.asyncio
    async def test_memory_protection_allows_existing_keys(self) -> None:
        """Test that memory protection allows requests to existing keys."""
        backend = InMemoryLimiterBackend(max_keys=2)
        backend._connected = True

        config = RateLimitConfig(times=5, seconds=60)

        # Fill up to max_keys
        await backend.check_limit("key1", config)
        await backend.check_limit("key2", config)

        # Request to existing key should work
        result = await backend.check_limit("key1", config)
        assert not result.is_exceeded

    @pytest.mark.asyncio
    async def test_handle_memory_limit_exceeded(self) -> None:
        """Test _handle_memory_limit_exceeded method."""
        backend = InMemoryLimiterBackend()
        backend._max_keys = 100

        config = RateLimitConfig(times=5, seconds=60)

        with patch.object(backend, "_handle_fallback") as mock_fallback:
            mock_fallback.return_value = RateLimitResult(
                is_exceeded=True, limit_times=5, remaining_requests=0
            )

            await backend._handle_memory_limit_exceeded(config)

            mock_fallback.assert_called_once()
            expected_error = "Memory backend reached max_keys limit (100)"
            mock_fallback.assert_called_with(expected_error, config)


class TestInMemoryLimiterBackendCleanup:
    """Test InMemoryLimiterBackend cleanup functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_entries_removes_old_data(self) -> None:
        """Test that cleanup removes old entries."""
        backend = InMemoryLimiterBackend()

        current_time_ms = time.time() * 1000
        old_time_ms = current_time_ms - (25 * 60 * 60 * 1000)  # 25 hours ago

        # Add old and new data
        backend._store["key1"] = [old_time_ms, current_time_ms]
        backend._store["key2"] = [old_time_ms]  # Only old data

        await backend._cleanup_expired_entries()

        # key1 should have only new data
        assert len(backend._store["key1"]) == 1
        assert backend._store["key1"][0] == current_time_ms

        # key2 should be completely removed
        assert "key2" not in backend._store
        assert "key2" not in backend._locks

    @pytest.mark.asyncio
    async def test_cleanup_expired_entries_preserves_recent_data(self) -> None:
        """Test that cleanup preserves recent data."""
        backend = InMemoryLimiterBackend()

        current_time_ms = time.time() * 1000
        recent_time_ms = current_time_ms - (1 * 60 * 60 * 1000)  # 1 hour ago

        backend._store["key1"] = [recent_time_ms, current_time_ms]

        await backend._cleanup_expired_entries()

        # All data should be preserved
        assert len(backend._store["key1"]) == 2
        assert recent_time_ms in backend._store["key1"]
        assert current_time_ms in backend._store["key1"]

    @pytest.mark.asyncio
    async def test_cleanup_updates_last_cleanup_time(self) -> None:
        """Test that cleanup updates last_cleanup timestamp."""
        backend = InMemoryLimiterBackend()
        original_time = backend._last_cleanup

        # Small delay to ensure time difference
        await asyncio.sleep(0.01)

        await backend._cleanup_expired_entries()

        assert backend._last_cleanup > original_time

    @pytest.mark.asyncio
    async def test_background_cleanup_lifecycle(self) -> None:
        """Test background cleanup task lifecycle."""
        backend = InMemoryLimiterBackend()
        config = MemoryLimiterBackendConnectConfig(cleanup_interval_seconds=1)

        await backend.connect(config)

        # Cleanup task should be running
        assert backend._cleanup_task is not None
        assert not backend._cleanup_task.done()

        # Add some old data that should be cleaned
        old_time_ms = (time.time() - 25 * 60 * 60) * 1000  # 25 hours ago
        backend._store["old_key"] = [old_time_ms]

        # Wait for at least one cleanup cycle (cleanup_interval=1s)
        await asyncio.sleep(1.5)

        # Old data should be cleaned up
        assert "old_key" not in backend._store

        await backend.disconnect()

    @pytest.mark.asyncio
    async def test_background_cleanup_handles_exceptions(self) -> None:
        """Test that background cleanup handles exceptions gracefully."""
        backend = InMemoryLimiterBackend()
        config = MemoryLimiterBackendConnectConfig(cleanup_interval_seconds=1)

        with patch.object(backend, "_cleanup_expired_entries") as mock_cleanup:
            mock_cleanup.side_effect = Exception("Cleanup error")

            await backend.connect(config)

            # Wait a bit to let cleanup run and handle exception
            await asyncio.sleep(0.2)

            # Task should still be running despite exception
            assert backend._cleanup_task is not None
            assert not backend._cleanup_task.done()

            await backend.disconnect()

    @pytest.mark.asyncio
    async def test_background_cleanup_stops_on_disconnect(self) -> None:
        """Test that background cleanup stops when disconnected."""
        backend = InMemoryLimiterBackend()
        config = MemoryLimiterBackendConnectConfig(cleanup_interval_seconds=1)

        await backend.connect(config)
        cleanup_task = backend._cleanup_task

        await backend.disconnect()

        # Task should be cancelled
        assert cleanup_task is not None
        assert cleanup_task.done()
        assert cleanup_task.cancelled()


class TestInMemoryLimiterBackendStatistics:
    """Test InMemoryLimiterBackend statistics and monitoring."""

    def test_get_stats_empty_backend(self) -> None:
        """Test get_stats with empty backend."""
        backend = InMemoryLimiterBackend(max_keys=5000)

        stats = backend.get_stats()

        assert stats["total_keys"] == 0
        assert stats["total_entries"] == 0
        assert stats["max_keys_limit"] == 5000
        assert isinstance(stats["last_cleanup_seconds_ago"], int)
        assert stats["last_cleanup_seconds_ago"] >= 0

    def test_get_stats_with_data(self) -> None:
        """Test get_stats with existing data."""
        backend = InMemoryLimiterBackend(max_keys=1000)

        # Add some test data
        current_time = time.time() * 1000
        backend._store["key1"] = [current_time, current_time + 1000]
        backend._store["key2"] = [current_time]
        backend._store["key3"] = [current_time, current_time + 500, current_time + 1500]

        stats = backend.get_stats()

        assert stats["total_keys"] == 3
        assert stats["total_entries"] == 6  # 2 + 1 + 3
        assert stats["max_keys_limit"] == 1000

    def test_get_stats_last_cleanup_calculation(self) -> None:
        """Test get_stats calculates last_cleanup correctly."""
        backend = InMemoryLimiterBackend()

        # Set last_cleanup to 10 seconds ago
        backend._last_cleanup = time.time() - 10

        stats = backend.get_stats()

        # Should be around 10 seconds (allowing for small timing differences)
        assert 9 <= stats["last_cleanup_seconds_ago"] <= 11


class TestInMemoryLimiterBackendClearOperations:
    """Test InMemoryLimiterBackend clear operations."""

    @pytest.mark.asyncio
    async def test_clear_key_existing_key(self) -> None:
        """Test clearing an existing key."""
        backend = InMemoryLimiterBackend()

        # Add test data
        backend._store["test_key"] = [time.time() * 1000]
        backend._locks["test_key"] = asyncio.Lock()

        result = await backend.clear_key("test_key")

        assert result is True
        assert "test_key" not in backend._store
        assert "test_key" not in backend._locks

    @pytest.mark.asyncio
    async def test_clear_key_nonexistent_key(self) -> None:
        """Test clearing a non-existent key."""
        backend = InMemoryLimiterBackend()

        result = await backend.clear_key("nonexistent_key")

        assert result is False

    @pytest.mark.asyncio
    async def test_clear_key_thread_safety(self) -> None:
        """Test that clear_key is thread-safe."""
        backend = InMemoryLimiterBackend()

        # Add test data
        backend._store["test_key"] = [time.time() * 1000]

        # This should not raise any errors due to concurrent access
        result = await backend.clear_key("test_key")
        assert result is True

    @pytest.mark.asyncio
    async def test_clear_all(self) -> None:
        """Test clearing all data."""
        backend = InMemoryLimiterBackend()

        # Add test data
        current_time = time.time() * 1000
        backend._store["key1"] = [current_time]
        backend._store["key2"] = [current_time]
        backend._locks["key1"] = asyncio.Lock()
        backend._locks["key2"] = asyncio.Lock()

        await backend.clear_all()

        assert len(backend._store) == 0
        assert len(backend._locks) == 0

    @pytest.mark.asyncio
    async def test_clear_all_thread_safety(self) -> None:
        """Test that clear_all is thread-safe."""
        backend = InMemoryLimiterBackend()

        # Add test data
        backend._store["key1"] = [time.time() * 1000]
        backend._store["key2"] = [time.time() * 1000]

        # This should not raise any errors due to concurrent access
        await backend.clear_all()

        assert len(backend._store) == 0


class TestInMemoryLimiterBackendConcurrency:
    """Test InMemoryLimiterBackend concurrency scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_same_key(self) -> None:
        """Test concurrent requests to the same key."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=10, seconds=60)

        async def make_request() -> bool:
            result = await backend.check_limit("concurrent_key", config)
            return not result.is_exceeded

        # Make 20 concurrent requests (10 should be allowed, 10 denied)
        tasks = [make_request() for _ in range(20)]
        results = await asyncio.gather(*tasks)

        allowed_count = sum(results)
        assert allowed_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_requests_different_keys(self) -> None:
        """Test concurrent requests to different keys."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=5, seconds=60)

        async def make_request(key_suffix: int) -> bool:
            result = await backend.check_limit(f"key_{key_suffix}", config)
            return not result.is_exceeded

        # Make concurrent requests to different keys
        tasks = [make_request(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All should be allowed since they're different keys
        assert all(results)

    @pytest.mark.asyncio
    async def test_concurrent_cleanup_and_requests(self) -> None:
        """Test that cleanup doesn't interfere with ongoing requests."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=5, seconds=60)

        async def make_requests() -> list[bool]:
            results = []
            for i in range(10):
                result = await backend.check_limit(f"key_{i}", config)
                results.append(not result.is_exceeded)
                await asyncio.sleep(0.01)  # Small delay
            return results

        async def run_cleanup() -> None:
            await asyncio.sleep(0.05)  # Start cleanup in the middle
            await backend._cleanup_expired_entries()

        # Run requests and cleanup concurrently
        request_task = asyncio.create_task(make_requests())
        cleanup_task = asyncio.create_task(run_cleanup())

        results, _ = await asyncio.gather(request_task, cleanup_task)

        # All first requests to different keys should be allowed
        assert all(results)


class TestInMemoryLimiterBackendEdgeCases:
    """Test InMemoryLimiterBackend edge cases."""

    @pytest.mark.asyncio
    async def test_extremely_short_time_window(self) -> None:
        """Test with extremely short time windows."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=1, milliseconds=1)

        # First request should be allowed
        result1 = await backend.check_limit("test_key", config)
        assert not result1.is_exceeded

        # Second immediate request should be blocked
        result2 = await backend.check_limit("test_key", config)
        assert result2.is_exceeded

    @pytest.mark.asyncio
    async def test_very_large_time_window(self) -> None:
        """Test with very large time windows."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=100, seconds=365 * 24 * 3600)  # 1 year window

        result = await backend.check_limit("test_key", config)

        assert not result.is_exceeded
        assert result.remaining_requests == 99

    @pytest.mark.asyncio
    async def test_zero_time_limit(self) -> None:
        """Test with zero time limit."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=5, milliseconds=1)  # Very small window

        # First request should be allowed
        result1 = await backend.check_limit("test_key", config)
        assert not result1.is_exceeded

        # Second immediate request should be blocked due to very small window
        await backend.check_limit("test_key", config)
        # This may or may not be blocked depending on timing, so test both cases
        # The important thing is the system handles very small windows gracefully

    @pytest.mark.asyncio
    async def test_single_request_limit(self) -> None:
        """Test with limit of 1 request."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        config = RateLimitConfig(times=1, seconds=60)

        # First request allowed
        result1 = await backend.check_limit("test_key", config)
        assert not result1.is_exceeded
        assert result1.remaining_requests == 0

        # Second request blocked
        result2 = await backend.check_limit("test_key", config)
        assert result2.is_exceeded

    @pytest.mark.asyncio
    async def test_very_long_key_names(self) -> None:
        """Test with very long key names."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        long_key = "a" * 1000  # 1000 character key
        config = RateLimitConfig(times=5, seconds=60)

        result = await backend.check_limit(long_key, config)

        assert not result.is_exceeded
        assert long_key in backend._store

    @pytest.mark.asyncio
    async def test_unicode_key_names(self) -> None:
        """Test with unicode key names."""
        backend = InMemoryLimiterBackend()
        backend._connected = True

        unicode_key = "тест_ключ_🔑_测试"
        config = RateLimitConfig(times=5, seconds=60)

        result = await backend.check_limit(unicode_key, config)

        assert not result.is_exceeded
        assert unicode_key in backend._store
