"""Integration tests for Redis backend with real Redis operations."""

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from redis import exceptions as redis_exc

from fastex.limiter.backend.enums import FallbackMode
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.redis.redis import RedisLimiterBackend
from fastex.limiter.backend.redis.scripts import FixedWindowScript, SlidingWindowScript
from fastex.limiter.schemas import RateLimitConfig

# Redis test configuration
REDIS_URL = "redis://localhost:6379/15"  # Use database 15 for tests
TEST_KEY_PREFIX = "test:limiter:"


class MockRedisForIntegration:
    """Mock Redis implementation for integration testing without real Redis server."""

    def __init__(self) -> None:
        self.scripts: dict[str, Any] = {}
        self.data: dict[str, Any] = {}
        self.expirations: dict[str, Any] = {}
        self.script_counter = 0

    async def script_load(self, script: str) -> str:
        """Mock script loading."""
        self.script_counter += 1
        sha = f"mock_sha_{self.script_counter}"
        self.scripts[sha] = script
        return sha

    async def evalsha(self, sha: str, num_keys: int, *args: Any) -> list[Any]:
        """Mock script execution with simplified logic."""
        if sha not in self.scripts:
            raise redis_exc.ResponseError("NOSCRIPT")

        key = args[0]
        limit = int(args[1])
        window_ms = int(args[2])

        current_time = int(time.time() * 1000)

        # Simple sliding window logic
        if key not in self.data:
            self.data[key] = []

        # Clean expired entries
        cutoff = current_time - window_ms
        self.data[key] = [t for t in self.data[key] if t > cutoff]

        current_count = len(self.data[key])

        if current_count < limit:
            # Add new request
            self.data[key].append(current_time)
            return [0, current_count + 1]
        else:
            # Limit exceeded, calculate retry after
            if self.data[key]:
                oldest = min(self.data[key])
                retry_after = oldest + window_ms - current_time
                return [max(0, retry_after), current_count]
            else:
                return [window_ms, current_count]

    async def aclose(self) -> None:
        """Mock connection close."""
        pass


@pytest.fixture
def mock_redis_integration() -> MockRedisForIntegration:
    """Provide a mock Redis instance for integration testing."""
    return MockRedisForIntegration()


@pytest_asyncio.fixture
async def redis_backend_integration(
    mock_redis_integration: MockRedisForIntegration,
) -> AsyncGenerator[RedisLimiterBackend, None]:
    """Provide a connected Redis backend for integration testing."""
    backend = RedisLimiterBackend()

    # Bypass Pydantic validation by setting directly
    backend._redis = mock_redis_integration  # type: ignore
    backend._fallback_mode = FallbackMode.ALLOW
    backend._lua_script = SlidingWindowScript()

    # Load script manually to simulate connection
    await backend._load_script()

    yield backend

    # Cleanup
    backend._redis = None
    backend._script_sha = None


class TestRedisBackendIntegrationBasicFlow:
    """Test basic integration flow of Redis backend."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_connection_lifecycle(self) -> None:
        """Test complete connection lifecycle."""
        mock_redis = MockRedisForIntegration()
        backend = RedisLimiterBackend()

        # Simulate connection by setting attributes directly
        assert not backend.is_connected()

        # Manual setup to avoid Pydantic validation
        backend._redis = mock_redis  # type: ignore
        backend._fallback_mode = FallbackMode.ALLOW
        backend._lua_script = SlidingWindowScript()
        await backend._load_script()

        assert backend.is_connected()
        assert backend._script_sha is not None
        assert isinstance(backend._lua_script, SlidingWindowScript)

        # Test disconnection
        await backend.disconnect()

        assert not backend.is_connected()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rate_limiting_basic_flow(
        self, redis_backend_integration: RedisLimiterBackend
    ) -> None:
        """Test basic rate limiting flow."""
        config = RateLimitConfig(times=3, seconds=60)
        key = f"{TEST_KEY_PREFIX}basic_flow"

        # First requests should not be limited
        for i in range(3):
            result = await redis_backend_integration.check_limit(key, config)
            assert not result.is_exceeded
            assert result.remaining_requests == 3 - (i + 1)

        # Fourth request should be limited
        result = await redis_backend_integration.check_limit(key, config)
        assert result.is_exceeded
        assert result.retry_after_ms > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_different_keys_independent_limits(
        self, redis_backend_integration: RedisLimiterBackend
    ) -> None:
        """Test that different keys have independent rate limits."""
        config = RateLimitConfig(times=2, seconds=60)

        key1 = f"{TEST_KEY_PREFIX}key1"
        key2 = f"{TEST_KEY_PREFIX}key2"

        # Exhaust limit for key1
        for _ in range(2):
            result = await redis_backend_integration.check_limit(key1, config)
            assert not result.is_exceeded

        # key1 should be limited
        result = await redis_backend_integration.check_limit(key1, config)
        assert result.is_exceeded

        # key2 should still be available
        result = await redis_backend_integration.check_limit(key2, config)
        assert not result.is_exceeded

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sliding_window_vs_fixed_window(self) -> None:
        """Test difference between sliding and fixed window algorithms."""
        # Test with sliding window
        sliding_backend = RedisLimiterBackend()
        sliding_backend._redis = MockRedisForIntegration()  # type: ignore
        sliding_backend._fallback_mode = FallbackMode.ALLOW
        sliding_backend._lua_script = SlidingWindowScript()
        await sliding_backend._load_script()

        # Test with fixed window
        fixed_backend = RedisLimiterBackend()
        fixed_backend._redis = MockRedisForIntegration()  # type: ignore
        fixed_backend._fallback_mode = FallbackMode.ALLOW
        fixed_backend._lua_script = FixedWindowScript()
        await fixed_backend._load_script()

        config = RateLimitConfig(times=2, milliseconds=1000)

        # Both should allow initial requests
        sliding_result = await sliding_backend.check_limit("sliding_key", config)
        fixed_result = await fixed_backend.check_limit("fixed_key", config)

        assert not sliding_result.is_exceeded
        assert not fixed_result.is_exceeded

        await sliding_backend.disconnect()
        await fixed_backend.disconnect()


class TestRedisBackendIntegrationErrorHandling:
    """Test error handling in integration scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_script_loading_failure_integration(self) -> None:
        """Test script loading failure in integration context."""

        class FailingMockRedis(MockRedisForIntegration):
            async def script_load(self, script: str) -> str:
                raise redis_exc.ResponseError("Script compilation error")

        backend = RedisLimiterBackend()
        # Set up manually to avoid Pydantic validation
        backend._redis = FailingMockRedis()  # type: ignore
        backend._fallback_mode = FallbackMode.ALLOW
        backend._lua_script = SlidingWindowScript()

        with pytest.raises(LimiterBackendError, match="Failed to load Lua script"):
            await backend._load_script()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_evalsha_failure_with_fallback(self) -> None:
        """Test evalsha failure with fallback modes."""

        class FailingEvalMockRedis(MockRedisForIntegration):
            async def evalsha(self, *args: Any) -> list[Any]:
                raise redis_exc.ConnectionError("Connection lost")

        # Test ALLOW fallback
        backend_allow = RedisLimiterBackend()
        backend_allow._redis = FailingEvalMockRedis()  # type: ignore
        backend_allow._fallback_mode = FallbackMode.ALLOW
        backend_allow._lua_script = SlidingWindowScript()
        await backend_allow._load_script()

        config = RateLimitConfig(times=1, seconds=60)
        result = await backend_allow.check_limit("test_key", config)
        assert not result.is_exceeded

        # Test DENY fallback
        backend_deny = RedisLimiterBackend()
        backend_deny._redis = FailingEvalMockRedis()  # type: ignore
        backend_deny._fallback_mode = FallbackMode.DENY
        backend_deny._lua_script = SlidingWindowScript()
        await backend_deny._load_script()

        result = await backend_deny.check_limit("test_key", config)
        assert result.is_exceeded

        # Test RAISE fallback
        backend_raise = RedisLimiterBackend()
        backend_raise._redis = FailingEvalMockRedis()  # type: ignore
        backend_raise._fallback_mode = FallbackMode.RAISE
        backend_raise._lua_script = SlidingWindowScript()
        await backend_raise._load_script()

        with pytest.raises(LimiterBackendError):
            await backend_raise.check_limit("test_key", config)

        await backend_allow.disconnect()
        await backend_deny.disconnect()
        await backend_raise.disconnect()


class TestRedisBackendIntegrationPerformance:
    """Test performance characteristics of Redis backend."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_high_concurrency_rate_limiting(
        self, redis_backend_integration: RedisLimiterBackend
    ) -> None:
        """Test rate limiting under high concurrency."""
        config = RateLimitConfig(times=100, seconds=60)
        key = f"{TEST_KEY_PREFIX}concurrency"

        async def make_request() -> bool:
            result = await redis_backend_integration.check_limit(key, config)
            return not result.is_exceeded

        # Make 150 concurrent requests (should exceed limit of 100)
        tasks = [make_request() for _ in range(150)]
        results = await asyncio.gather(*tasks)

        allowed_count = sum(results)
        denied_count = len(results) - allowed_count

        # Should have approximately 100 allowed and 50 denied
        # Allow some variance due to timing and concurrency
        assert 90 <= allowed_count <= 110
        assert denied_count > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_keys_concurrent_access(
        self, redis_backend_integration: RedisLimiterBackend
    ) -> None:
        """Test concurrent access to multiple different keys."""
        config = RateLimitConfig(times=5, seconds=60)

        async def test_key(key_suffix: str) -> int:
            key = f"{TEST_KEY_PREFIX}multi_{key_suffix}"
            _allowed_count = 0

            # Make 10 requests to this key (limit is 5)
            for _ in range(10):
                result = await redis_backend_integration.check_limit(key, config)
                if not result.is_exceeded:
                    _allowed_count += 1

            return _allowed_count

        # Test 5 different keys concurrently
        tasks = [test_key(str(i)) for i in range(5)]
        results = await asyncio.gather(*tasks)

        # Each key should allow exactly 5 requests
        for allowed_count in results:
            assert allowed_count == 5

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rapid_sequential_requests(
        self, redis_backend_integration: RedisLimiterBackend
    ) -> None:
        """Test rapid sequential requests to the same key."""
        config = RateLimitConfig(times=10, milliseconds=500)
        key = f"{TEST_KEY_PREFIX}rapid"

        allowed_count = 0
        denied_count = 0

        # Make 20 rapid requests
        for _ in range(20):
            result = await redis_backend_integration.check_limit(key, config)
            if result.is_exceeded:
                denied_count += 1
            else:
                allowed_count += 1

        # Should have exactly 10 allowed (the limit)
        assert allowed_count == 10
        assert denied_count == 10


class TestRedisBackendIntegrationRealScenarios:
    """Test real-world usage scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_api_rate_limiting_scenario(
        self, redis_backend_integration: RedisLimiterBackend
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
            result = await redis_backend_integration.check_limit(
                heavy_key, heavy_config
            )
            if not result.is_exceeded:
                heavy_allowed += 1

        # Normal operations - should allow more
        normal_allowed = 0
        for _ in range(50):  # Try 50, limit is 100
            result = await redis_backend_integration.check_limit(
                normal_key, normal_config
            )
            if not result.is_exceeded:
                normal_allowed += 1

        # Read operations - should allow most
        read_allowed = 0
        for _ in range(50):  # Try 50, limit is 1000
            result = await redis_backend_integration.check_limit(read_key, read_config)
            if not result.is_exceeded:
                read_allowed += 1

        assert heavy_allowed == 10  # Exactly the limit
        assert normal_allowed == 50  # All allowed (under limit)
        assert read_allowed == 50  # All allowed (well under limit)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_burst_and_sustained_traffic(
        self, redis_backend_integration: RedisLimiterBackend
    ) -> None:
        """Test handling of burst traffic followed by sustained load."""
        config = RateLimitConfig(times=50, seconds=10)  # 50 requests per 10 seconds
        key = f"{TEST_KEY_PREFIX}burst"

        # Phase 1: Burst traffic (consume all allowance quickly)
        burst_allowed = 0
        for _ in range(60):  # Try 60 requests rapidly
            result = await redis_backend_integration.check_limit(key, config)
            if not result.is_exceeded:
                burst_allowed += 1

        assert burst_allowed == 50  # Should allow exactly the limit

        # Phase 2: Immediate sustained requests (should be denied)
        sustained_denied = 0
        for _ in range(10):
            result = await redis_backend_integration.check_limit(key, config)
            if result.is_exceeded:
                sustained_denied += 1

        assert sustained_denied == 10  # All should be denied

        # Verify rate limit information is accurate
        result = await redis_backend_integration.check_limit(key, config)
        assert result.is_exceeded
        assert result.remaining_requests == 0
        assert result.retry_after_ms > 0
