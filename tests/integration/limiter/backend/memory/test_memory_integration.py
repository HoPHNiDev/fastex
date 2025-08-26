"""Integration tests for memory backend with real usage scenarios."""

import asyncio
import time
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from fastex.limiter.backend.enums import FallbackMode
from fastex.limiter.backend.memory.memory import InMemoryLimiterBackend
from fastex.limiter.backend.memory.schemas import MemoryLimiterBackendConnectConfig
from fastex.limiter.schemas import RateLimitConfig

# Test configuration
TEST_KEY_PREFIX = "test:memory:integration:"


@pytest.fixture
def memory_backend() -> InMemoryLimiterBackend:
    """Provide a memory backend instance for testing."""
    return InMemoryLimiterBackend()


@pytest.fixture
def memory_config() -> MemoryLimiterBackendConnectConfig:
    """Provide a test configuration for memory backend."""
    return MemoryLimiterBackendConnectConfig(
        cleanup_interval_seconds=1,  # Fast cleanup for testing
        max_keys=1000,
        fallback_mode=FallbackMode.ALLOW,
    )


@pytest_asyncio.fixture
async def connected_memory_backend(
    memory_backend: InMemoryLimiterBackend,
    memory_config: MemoryLimiterBackendConnectConfig,
) -> AsyncGenerator[InMemoryLimiterBackend, None]:
    """Provide a connected memory backend for integration testing."""
    await memory_backend.connect(memory_config)
    yield memory_backend
    await memory_backend.disconnect()


class TestMemoryBackendIntegrationBasicFlow:
    """Test basic integration flow of memory backend."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_connection_lifecycle(self) -> None:
        """Test complete connection lifecycle."""
        backend = InMemoryLimiterBackend()
        config = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=1, max_keys=100, fallback_mode=FallbackMode.ALLOW
        )

        # Test initial state
        assert not backend.is_connected()

        # Test connection
        await backend.connect(config)

        assert backend.is_connected()
        assert backend._cleanup_interval == 1
        assert backend._max_keys == 100
        assert backend._fallback_mode == FallbackMode.ALLOW
        assert backend._cleanup_task is not None

        # Test disconnection
        await backend.disconnect()

        assert not backend.is_connected()
        assert backend._cleanup_task is None or backend._cleanup_task.done()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rate_limiting_basic_flow(
        self, connected_memory_backend: InMemoryLimiterBackend
    ) -> None:
        """Test basic rate limiting flow."""
        config = RateLimitConfig(times=3, seconds=60)
        key = f"{TEST_KEY_PREFIX}basic_flow"

        # First requests should not be limited
        for i in range(3):
            result = await connected_memory_backend.check_limit(key, config)
            assert not result.is_exceeded
            assert result.remaining_requests == 2 - i

        # Fourth request should be limited
        result = await connected_memory_backend.check_limit(key, config)
        assert result.is_exceeded
        assert result.remaining_requests == 0
        assert result.retry_after_ms > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_different_keys_independent_limits(
        self, connected_memory_backend: InMemoryLimiterBackend
    ) -> None:
        """Test that different keys have independent rate limits."""
        config = RateLimitConfig(times=2, seconds=60)

        key1 = f"{TEST_KEY_PREFIX}key1"
        key2 = f"{TEST_KEY_PREFIX}key2"

        # Exhaust limit for key1
        for _ in range(2):
            result = await connected_memory_backend.check_limit(key1, config)
            assert not result.is_exceeded

        # key1 should be limited
        result = await connected_memory_backend.check_limit(key1, config)
        assert result.is_exceeded

        # key2 should still be available
        result = await connected_memory_backend.check_limit(key2, config)
        assert not result.is_exceeded

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sliding_window_time_progression(self) -> None:
        """Test sliding window behavior with real time progression."""
        backend = InMemoryLimiterBackend()
        config_connect = MemoryLimiterBackendConnectConfig()
        await backend.connect(config_connect)

        config = RateLimitConfig(
            times=2, milliseconds=500
        )  # 2 requests per 0.5 seconds
        key = f"{TEST_KEY_PREFIX}sliding"

        try:
            # Make 2 requests quickly
            result1 = await backend.check_limit(key, config)
            assert not result1.is_exceeded

            result2 = await backend.check_limit(key, config)
            assert not result2.is_exceeded

            # Third request should be blocked
            result3 = await backend.check_limit(key, config)
            assert result3.is_exceeded

            # Wait for window to slide
            await asyncio.sleep(0.6)

            # Request should be allowed again
            result4 = await backend.check_limit(key, config)
            assert not result4.is_exceeded

        finally:
            await backend.disconnect()


class TestMemoryBackendIntegrationMemoryManagement:
    """Test memory management and cleanup scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_memory_protection_triggers_fallback(self) -> None:
        """Test memory protection behavior."""
        backend = InMemoryLimiterBackend(max_keys=3)
        config_connect = MemoryLimiterBackendConnectConfig(
            max_keys=3, fallback_mode=FallbackMode.ALLOW
        )
        await backend.connect(config_connect)

        config = RateLimitConfig(times=5, seconds=60)

        try:
            # Fill up to max_keys
            for i in range(3):
                result = await backend.check_limit(f"key_{i}", config)
                assert not result.is_exceeded

            # This should trigger memory protection fallback
            result = await backend.check_limit("key_overflow", config)
            assert not result.is_exceeded  # ALLOW fallback

            # Verify key wasn't actually stored
            assert "key_overflow" not in backend._store

        finally:
            await backend.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_memory_protection_deny_fallback(self) -> None:
        """Test memory protection with DENY fallback."""
        backend = InMemoryLimiterBackend(max_keys=2)
        config_connect = MemoryLimiterBackendConnectConfig(
            max_keys=2, fallback_mode=FallbackMode.DENY
        )
        await backend.connect(config_connect)

        config = RateLimitConfig(times=5, seconds=60)

        try:
            # Fill up to max_keys
            await backend.check_limit("key_1", config)
            await backend.check_limit("key_2", config)

            # This should trigger DENY fallback
            result = await backend.check_limit("key_overflow", config)
            assert result.is_exceeded

        finally:
            await backend.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_background_cleanup_removes_old_entries(self) -> None:
        """Test that background cleanup removes old entries."""
        backend = InMemoryLimiterBackend()
        config_connect = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=1  # Fast cleanup for testing
        )
        await backend.connect(config_connect)

        try:
            # Add some data
            await backend.check_limit("test_key", RateLimitConfig(times=5, seconds=60))

            # Manually add very old data
            old_time_ms = (time.time() - 25 * 60 * 60) * 1000  # 25 hours ago
            backend._store["old_key"] = [old_time_ms]

            # Wait for cleanup to run (cleanup_interval=1s)
            await asyncio.sleep(1.5)

            # Old key should be removed, new key should remain
            assert "old_key" not in backend._store
            assert "test_key" in backend._store

        finally:
            await backend.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_clear_operations_in_running_backend(
        self, connected_memory_backend: InMemoryLimiterBackend
    ) -> None:
        """Test clear operations while backend is running."""
        config = RateLimitConfig(times=5, seconds=60)

        # Add some data
        await connected_memory_backend.check_limit("key1", config)
        await connected_memory_backend.check_limit("key2", config)

        # Test individual key clearing
        result = await connected_memory_backend.clear_key("key1")
        assert result is True
        assert "key1" not in connected_memory_backend._store
        assert "key2" in connected_memory_backend._store

        # Test clearing non-existent key
        result = await connected_memory_backend.clear_key("nonexistent")
        assert result is False

        # Test clear all
        await connected_memory_backend.clear_all()
        assert len(connected_memory_backend._store) == 0


class TestMemoryBackendIntegrationPerformance:
    """Test performance characteristics of memory backend."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_high_concurrency_rate_limiting(
        self, connected_memory_backend: InMemoryLimiterBackend
    ) -> None:
        """Test rate limiting under high concurrency."""
        config = RateLimitConfig(times=100, seconds=60)
        key = f"{TEST_KEY_PREFIX}concurrency"

        async def make_request() -> bool:
            result = await connected_memory_backend.check_limit(key, config)
            return not result.is_exceeded

        # Make 150 concurrent requests (should exceed limit of 100)
        tasks = [make_request() for _ in range(150)]
        results = await asyncio.gather(*tasks)

        allowed_count = sum(results)
        denied_count = len(results) - allowed_count

        # Should allow exactly 100 requests
        assert allowed_count == 100
        assert denied_count == 50

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_keys_concurrent_access(
        self, connected_memory_backend: InMemoryLimiterBackend
    ) -> None:
        """Test concurrent access to multiple different keys."""
        config = RateLimitConfig(times=5, seconds=60)

        async def test_key(key_suffix: str) -> int:
            key = f"{TEST_KEY_PREFIX}multi_{key_suffix}"
            allowed_count = 0

            # Make 10 requests to this key (limit is 5)
            for _ in range(10):
                result = await connected_memory_backend.check_limit(key, config)
                if not result.is_exceeded:
                    allowed_count += 1

            return allowed_count

        # Test 5 different keys concurrently
        tasks = [test_key(str(i)) for i in range(5)]
        results = await asyncio.gather(*tasks)

        # Each key should allow exactly 5 requests
        assert all(count == 5 for count in results)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rapid_sequential_requests(
        self, connected_memory_backend: InMemoryLimiterBackend
    ) -> None:
        """Test rapid sequential requests to the same key."""
        config = RateLimitConfig(times=10, milliseconds=500)
        key = f"{TEST_KEY_PREFIX}rapid"

        allowed_count = 0
        denied_count = 0

        # Make 20 rapid requests
        for _ in range(20):
            result = await connected_memory_backend.check_limit(key, config)
            if result.is_exceeded:
                denied_count += 1
            else:
                allowed_count += 1

        # Should allow exactly 10 requests
        assert allowed_count == 10
        assert denied_count == 10

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_memory_efficiency_large_dataset(self) -> None:
        """Test memory efficiency with large number of keys."""
        backend = InMemoryLimiterBackend(max_keys=1000)
        config_connect = MemoryLimiterBackendConnectConfig(
            max_keys=1000, cleanup_interval_seconds=10  # Slow cleanup for this test
        )
        await backend.connect(config_connect)

        try:
            config = RateLimitConfig(times=5, seconds=60)

            # Create many keys
            for i in range(500):
                await backend.check_limit(f"key_{i}", config)

            stats = backend.get_stats()
            assert stats["total_keys"] == 500
            assert stats["total_entries"] == 500  # One entry per key
            assert stats["max_keys_limit"] == 1000

        finally:
            await backend.disconnect()


class TestMemoryBackendIntegrationRealScenarios:
    """Test typical real-world usage scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_api_rate_limiting_scenario(
        self, connected_memory_backend: InMemoryLimiterBackend
    ) -> None:
        """Test typical API rate limiting scenario."""
        # Simulate different rate limits for different endpoints

        # Conservative limit for heavy operations
        heavy_config = RateLimitConfig(times=10, minutes=1)

        # Moderate limit for normal operations
        normal_config = RateLimitConfig(times=100, minutes=1)

        # Liberal limit for read operations
        read_config = RateLimitConfig(times=1000, minutes=1)

        user_id = "user123"

        # Simulate usage patterns
        heavy_key = f"{TEST_KEY_PREFIX}heavy:{user_id}"
        normal_key = f"{TEST_KEY_PREFIX}normal:{user_id}"
        read_key = f"{TEST_KEY_PREFIX}read:{user_id}"

        # Heavy operations - should be limited quickly
        heavy_allowed = 0
        for _ in range(15):  # Try 15, limit is 10
            result = await connected_memory_backend.check_limit(heavy_key, heavy_config)
            if not result.is_exceeded:
                heavy_allowed += 1

        # Normal operations - moderate usage
        normal_allowed = 0
        for _ in range(120):  # Try 120, limit is 100
            result = await connected_memory_backend.check_limit(
                normal_key, normal_config
            )
            if not result.is_exceeded:
                normal_allowed += 1

        # Read operations - should handle high volume
        read_allowed = 0
        for _ in range(50):  # Try 50, all should be allowed
            result = await connected_memory_backend.check_limit(read_key, read_config)
            if not result.is_exceeded:
                read_allowed += 1

        assert heavy_allowed == 10
        assert normal_allowed == 100
        assert read_allowed == 50

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_burst_and_sustained_traffic(
        self, connected_memory_backend: InMemoryLimiterBackend
    ) -> None:
        """Test handling of burst traffic followed by sustained load."""
        config = RateLimitConfig(times=50, seconds=10)  # 50 requests per 10 seconds
        key = f"{TEST_KEY_PREFIX}burst"

        # Phase 1: Burst traffic (consume all allowance quickly)
        burst_allowed = 0
        for _ in range(60):  # Try 60 requests rapidly
            result = await connected_memory_backend.check_limit(key, config)
            if not result.is_exceeded:
                burst_allowed += 1

        assert burst_allowed == 50

        # Phase 2: Sustained traffic (should be rate limited)
        sustained_denied = 0
        for _ in range(20):
            result = await connected_memory_backend.check_limit(key, config)
            if result.is_exceeded:
                sustained_denied += 1

        assert sustained_denied == 20

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multi_tenant_isolation(
        self, connected_memory_backend: InMemoryLimiterBackend
    ) -> None:
        """Test that different tenants have isolated rate limits."""
        config = RateLimitConfig(times=5, seconds=60)

        # Different tenant patterns
        tenant_patterns = ["tenant:alice:api", "tenant:bob:api", "tenant:charlie:api"]

        results = {}

        # Each tenant uses their full allowance
        for tenant in tenant_patterns:
            allowed = 0
            for _ in range(7):  # Try 7, limit is 5
                result = await connected_memory_backend.check_limit(tenant, config)
                if not result.is_exceeded:
                    allowed += 1
            results[tenant] = allowed

        # Each tenant should have exactly 5 allowed requests
        for tenant, allowed in results.items():
            assert allowed == 5, f"Tenant {tenant} had {allowed} allowed requests"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_statistics_monitoring(
        self, connected_memory_backend: InMemoryLimiterBackend
    ) -> None:
        """Test statistics and monitoring capabilities."""
        config = RateLimitConfig(times=3, seconds=60)

        # Initial stats
        initial_stats = connected_memory_backend.get_stats()
        assert initial_stats["total_keys"] == 0
        assert initial_stats["total_entries"] == 0

        # Add some usage
        await connected_memory_backend.check_limit("key1", config)
        await connected_memory_backend.check_limit("key1", config)
        await connected_memory_backend.check_limit("key2", config)

        # Check updated stats
        stats = connected_memory_backend.get_stats()
        assert stats["total_keys"] == 2
        assert stats["total_entries"] == 3
        assert stats["max_keys_limit"] > 0
        assert isinstance(stats["last_cleanup_seconds_ago"], int)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_graceful_degradation_under_pressure(self) -> None:
        """Test graceful degradation when memory limits are reached."""
        backend = InMemoryLimiterBackend(max_keys=10)
        config_connect = MemoryLimiterBackendConnectConfig(
            max_keys=10, fallback_mode=FallbackMode.ALLOW
        )
        await backend.connect(config_connect)

        try:
            config = RateLimitConfig(times=5, seconds=60)

            # Fill up to max capacity
            for i in range(10):
                result = await backend.check_limit(f"key_{i}", config)
                assert not result.is_exceeded

            # Additional requests should use fallback
            for i in range(5):
                result = await backend.check_limit(f"overflow_{i}", config)
                assert not result.is_exceeded  # ALLOW fallback

            # Existing keys should still work
            result = await backend.check_limit("key_0", config)
            assert not result.is_exceeded

        finally:
            await backend.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_cleanup_during_active_usage(self) -> None:
        """Test that cleanup works correctly during active usage."""
        backend = InMemoryLimiterBackend()
        config_connect = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=1  # Frequent cleanup for testing
        )
        await backend.connect(config_connect)

        try:
            config = RateLimitConfig(times=10, seconds=60)

            # Continuous usage while cleanup runs
            async def continuous_requests() -> None:
                for i in range(50):
                    await backend.check_limit(f"active_key_{i % 5}", config)
                    await asyncio.sleep(0.01)

            # Let it run for a bit with background cleanup
            await asyncio.wait_for(continuous_requests(), timeout=2.0)

            # System should still be functioning
            result = await backend.check_limit("final_test", config)
            assert not result.is_exceeded

            stats = backend.get_stats()
            assert stats["total_keys"] > 0

        finally:
            await backend.disconnect()
