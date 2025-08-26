from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import redis.asyncio as aredis

from fastex.limiter.backend.enums import FallbackMode
from fastex.limiter.backend.redis.redis import RedisLimiterBackend
from fastex.limiter.backend.redis.schemas import RedisLimiterBackendConnectConfig
from fastex.limiter.backend.redis.scripts import FixedWindowScript, SlidingWindowScript
from fastex.limiter.schemas import RateLimitConfig


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create a mock Redis client for testing."""
    mock = AsyncMock(spec=aredis.Redis)
    mock.script_load.return_value = "mock_sha"
    mock.evalsha.return_value = [0, 1]  # Default: not exceeded, 1 request
    mock.aclose.return_value = None
    return mock


@pytest.fixture
def redis_backend() -> RedisLimiterBackend:
    """Create a Redis backend instance for testing."""
    return RedisLimiterBackend()


@pytest.fixture
def sliding_window_script() -> SlidingWindowScript:
    """Create a SlidingWindowScript instance."""
    return SlidingWindowScript()


@pytest.fixture
def fixed_window_script() -> FixedWindowScript:
    """Create a FixedWindowScript instance."""
    return FixedWindowScript()


@pytest.fixture
def redis_config(mock_redis: AsyncMock) -> RedisLimiterBackendConnectConfig:
    """Create a Redis backend configuration."""
    return RedisLimiterBackendConnectConfig(
        redis_client=mock_redis,
        fallback_mode=FallbackMode.ALLOW,
        lua_script=SlidingWindowScript(),
    )


@pytest.fixture
def redis_url_config() -> RedisLimiterBackendConnectConfig:
    """Create a Redis backend configuration with URL string."""
    return RedisLimiterBackendConnectConfig(
        redis_client="redis://localhost:6379/0",
        fallback_mode=FallbackMode.DENY,
        lua_script=FixedWindowScript(),
    )


@pytest.fixture
def rate_limit_config() -> RateLimitConfig:
    """Create a basic rate limit configuration."""
    return RateLimitConfig(times=10, seconds=60)


@pytest.fixture
def rate_limit_config_ms() -> RateLimitConfig:
    """Create a rate limit configuration with milliseconds."""
    return RateLimitConfig(times=5, milliseconds=1000)


@pytest.fixture
def rate_limit_config_mixed() -> RateLimitConfig:
    """Create a rate limit configuration with mixed time units."""
    return RateLimitConfig(times=100, minutes=1, seconds=30)


@pytest.fixture
async def connected_redis_backend(
    redis_backend: RedisLimiterBackend, redis_config: RedisLimiterBackendConnectConfig
) -> AsyncGenerator[RedisLimiterBackend, None]:
    """Create a connected Redis backend for testing."""
    await redis_backend.connect(redis_config)
    yield redis_backend
    try:
        await redis_backend.disconnect()
    except Exception:
        pass  # Ignore cleanup errors


# Mock helpers for specific test scenarios
@pytest.fixture
def redis_connection_error_mock() -> AsyncMock:
    """Create a mock Redis client that raises connection errors."""
    mock = AsyncMock(spec=aredis.Redis)
    mock.script_load.side_effect = aredis.ConnectionError("Connection failed")
    mock.evalsha.side_effect = aredis.ConnectionError("Connection failed")
    return mock


@pytest.fixture
def redis_timeout_error_mock() -> AsyncMock:
    """Create a mock Redis client that raises timeout errors."""
    mock = AsyncMock(spec=aredis.Redis)
    mock.script_load.side_effect = aredis.TimeoutError("Operation timed out")
    mock.evalsha.side_effect = aredis.TimeoutError("Operation timed out")
    return mock


@pytest.fixture
def redis_script_load_error_mock() -> AsyncMock:
    """Create a mock Redis client that fails to load scripts."""
    mock = AsyncMock(spec=aredis.Redis)
    mock.script_load.side_effect = Exception("Script load failed")
    return mock


@pytest.fixture
def redis_invalid_response_mock() -> AsyncMock:
    """Create a mock Redis client that returns invalid responses."""
    mock = AsyncMock(spec=aredis.Redis)
    mock.script_load.return_value = "valid_sha"
    mock.evalsha.return_value = ["invalid", "response"]  # Invalid format
    return mock
