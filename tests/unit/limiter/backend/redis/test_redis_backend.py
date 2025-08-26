"""Unit tests for RedisLimiterBackend."""

import asyncio
import inspect
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as aredis
from redis import exceptions as redis_exc

from fastex.limiter.backend.base import BaseLimiterBackend
from fastex.limiter.backend.enums import FallbackMode
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.redis.redis import RedisLimiterBackend
from fastex.limiter.backend.redis.schemas import RedisLimiterBackendConnectConfig
from fastex.limiter.backend.redis.scripts import SlidingWindowScript
from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.schemas import RateLimitConfig


class TestRedisLimiterBackendInheritance:
    """Test RedisLimiterBackend inheritance and basic structure."""

    def test_inheritance(self) -> None:
        """Test that RedisLimiterBackend inherits from BaseLimiterBackend."""
        backend = RedisLimiterBackend()
        assert isinstance(backend, BaseLimiterBackend)

    def test_logger_attribute(self) -> None:
        """Test that backend has logger attribute."""
        backend = RedisLimiterBackend()
        assert hasattr(backend, "logger")
        assert backend.logger is not None

    def test_private_attributes_initialized(self) -> None:
        """Test that private attributes are properly initialized."""
        backend = RedisLimiterBackend()
        assert backend._redis is None
        assert backend._script_sha is None
        assert backend._lua_script is None


class TestRedisLimiterBackendConnection:
    """Test RedisLimiterBackend connection functionality."""

    @pytest.mark.asyncio
    async def test_connect_with_redis_client_instance(self) -> None:
        """Test connecting with a Redis client instance."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        # Make script_load awaitable
        mock_redis.script_load = AsyncMock(return_value="test_sha")

        backend = RedisLimiterBackend()
        config = RedisLimiterBackendConnectConfig(
            redis_client=mock_redis,
            fallback_mode=FallbackMode.ALLOW,
            lua_script=SlidingWindowScript(),
        )

        await backend.connect(config)

        assert backend._redis is mock_redis
        assert backend._script_sha == "test_sha"
        assert isinstance(backend._lua_script, SlidingWindowScript)
        assert backend._fallback_mode == FallbackMode.ALLOW
        mock_redis.script_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_redis_url_string(self) -> None:
        """Test connecting with a Redis URL string."""
        backend = RedisLimiterBackend()
        config = RedisLimiterBackendConnectConfig(
            redis_client="redis://localhost:6379/0", fallback_mode=FallbackMode.DENY
        )

        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_redis = AsyncMock(spec=aredis.Redis)
            mock_redis.script_load = AsyncMock(return_value="url_sha")
            mock_from_url.return_value = mock_redis

            await backend.connect(config)

            mock_from_url.assert_called_once_with("redis://localhost:6379/0")
            assert backend._redis is mock_redis
            assert backend._script_sha == "url_sha"
            assert backend._fallback_mode == FallbackMode.DENY

    @pytest.mark.asyncio
    async def test_connect_with_invalid_config_type(self) -> None:
        """Test connect raises error with invalid config type."""
        backend = RedisLimiterBackend()

        # Create a mock config that's not RedisLimiterBackendConnectConfig
        invalid_config = MagicMock()

        with pytest.raises(LimiterBackendError, match="Invalid config type"):
            await backend.connect(invalid_config)

    @pytest.mark.asyncio
    async def test_connect_uses_default_fallback_mode(self) -> None:
        """Test that connect uses default fallback mode when not specified."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.script_load = AsyncMock(return_value="test_sha")

        backend = RedisLimiterBackend()
        config = RedisLimiterBackendConnectConfig(redis_client=mock_redis)

        with patch(
            "fastex.limiter.config.limiter_settings.FALLBACK_MODE", FallbackMode.RAISE
        ):
            await backend.connect(config)
            assert backend._fallback_mode == FallbackMode.RAISE

    @pytest.mark.asyncio
    async def test_connect_uses_default_lua_script(self) -> None:
        """Test that connect uses default SlidingWindowScript when not specified."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.script_load = AsyncMock(return_value="test_sha")

        backend = RedisLimiterBackend()
        config = RedisLimiterBackendConnectConfig(redis_client=mock_redis)

        await backend.connect(config)

        assert isinstance(backend._lua_script, SlidingWindowScript)

    @pytest.mark.asyncio
    async def test_load_script_success(self) -> None:
        """Test successful Lua script loading."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.script_load = AsyncMock(return_value="script_sha_123")

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._lua_script = SlidingWindowScript()

        await backend._load_script()

        assert backend._script_sha == "script_sha_123"
        mock_redis.script_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_script_failure(self) -> None:
        """Test Lua script loading failure."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.script_load.side_effect = Exception("Script load failed")

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._lua_script = SlidingWindowScript()

        with pytest.raises(LimiterBackendError, match="Failed to load Lua script"):
            await backend._load_script()

    @pytest.mark.asyncio
    async def test_disconnect_success(self) -> None:
        """Test successful disconnection."""
        mock_redis = AsyncMock(spec=aredis.Redis)

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha"

        await backend.disconnect()

        mock_redis.aclose.assert_called_once()
        assert backend._redis is None
        assert backend._script_sha is None

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        """Test disconnect when not connected."""
        backend = RedisLimiterBackend()

        # Should not raise an error
        await backend.disconnect()

        assert backend._redis is None
        assert backend._script_sha is None


class TestRedisLimiterBackendProperties:
    """Test RedisLimiterBackend property access."""

    def test_redis_property_success(self) -> None:
        """Test successful redis property access."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        backend = RedisLimiterBackend()
        backend._redis = mock_redis

        assert backend.redis is mock_redis

    def test_redis_property_not_connected(self) -> None:
        """Test redis property raises error when not connected."""
        backend = RedisLimiterBackend()

        with pytest.raises(LimiterBackendError, match="Redis not connected"):
            _ = backend.redis

    def test_script_sha_property_success(self) -> None:
        """Test successful script_sha property access."""
        backend = RedisLimiterBackend()
        backend._script_sha = "test_sha"

        assert backend.script_sha == "test_sha"

    def test_script_sha_property_not_loaded(self) -> None:
        """Test script_sha property raises error when script not loaded."""
        backend = RedisLimiterBackend()

        with pytest.raises(LimiterBackendError, match="Lua script not loaded"):
            _ = backend.script_sha

    def test_lua_script_property_success(self) -> None:
        """Test successful lua_script property access."""
        script = SlidingWindowScript()
        backend = RedisLimiterBackend()
        backend._lua_script = script

        assert backend.lua_script is script

    def test_lua_script_property_not_set(self) -> None:
        """Test lua_script property raises error when not set."""
        backend = RedisLimiterBackend()

        with pytest.raises(LimiterBackendError, match="Lua script object not set"):
            _ = backend.lua_script

    def test_fallback_mode_property_success(self) -> None:
        """Test successful fallback_mode property access."""
        backend = RedisLimiterBackend()
        backend._fallback_mode = FallbackMode.DENY

        assert backend.fallback_mode == FallbackMode.DENY

    def test_fallback_mode_property_not_set(self) -> None:
        """Test fallback_mode property raises error when not set."""
        backend = RedisLimiterBackend()
        # _fallback_mode attribute should be None initially
        assert backend._fallback_mode is None

        with pytest.raises(LimiterBackendError, match="Fallback mode not set"):
            _ = backend.fallback_mode


class TestRedisLimiterBackendConnectionCheck:
    """Test RedisLimiterBackend connection checking."""

    def test_is_connected_true(self) -> None:
        """Test is_connected returns True when fully connected."""
        backend = RedisLimiterBackend()
        backend._redis = AsyncMock(spec=aredis.Redis)
        backend._script_sha = "test_sha"

        assert backend.is_connected() is True

    def test_is_connected_false_no_redis(self) -> None:
        """Test is_connected returns False when Redis not connected."""
        backend = RedisLimiterBackend()
        backend._script_sha = "test_sha"

        assert backend.is_connected() is False

    def test_is_connected_false_no_script_sha(self) -> None:
        """Test is_connected returns False when script not loaded."""
        backend = RedisLimiterBackend()
        backend._redis = AsyncMock(spec=aredis.Redis)

        assert backend.is_connected() is False

    def test_is_connected_false_neither(self) -> None:
        """Test is_connected returns False when neither connected nor script loaded."""
        backend = RedisLimiterBackend()

        assert backend.is_connected() is False

    def test_is_connected_with_raise_exc_true_connected(self) -> None:
        """Test is_connected with raise_exc=True when connected."""
        backend = RedisLimiterBackend()
        backend._redis = AsyncMock(spec=aredis.Redis)
        backend._script_sha = "test_sha"

        assert backend.is_connected(raise_exc=True) is True

    def test_is_connected_with_raise_exc_true_not_connected(self) -> None:
        """Test is_connected with raise_exc=True raises error when not connected."""
        backend = RedisLimiterBackend()

        with pytest.raises(
            LimiterBackendError, match="Redis not connected or Lua script not loaded"
        ):
            backend.is_connected(raise_exc=True)


class TestRedisLimiterBackendCheckLimit:
    """Test RedisLimiterBackend rate limit checking functionality."""

    @pytest.mark.asyncio
    async def test_check_limit_not_exceeded(self) -> None:
        """Test check_limit when limit is not exceeded."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.evalsha.return_value = [0, 3]  # Not exceeded, 3 current requests

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha"
        backend._lua_script = SlidingWindowScript()

        config = RateLimitConfig(times=10, seconds=60)
        result = await backend.check_limit("test_key", config)

        assert isinstance(result, RateLimitResult)
        assert result.is_exceeded is False
        assert result.limit_times == 10
        assert result.remaining_requests == 7  # 10 - 3
        assert result.retry_after_ms == 0
        assert result.reset_time is None

    @pytest.mark.asyncio
    async def test_check_limit_exceeded(self) -> None:
        """Test check_limit when limit is exceeded."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.evalsha.return_value = [
            5000,
            10,
        ]  # Exceeded, 5000ms retry, 10 current

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha"
        backend._lua_script = SlidingWindowScript()

        config = RateLimitConfig(times=10, seconds=60)

        with patch("fastex.limiter.backend.redis.redis.datetime") as mock_datetime:
            mock_now = datetime(2024, 1, 1, 12, 0, 0)
            mock_datetime.now.return_value = mock_now

            result = await backend.check_limit("test_key", config)

        assert isinstance(result, RateLimitResult)
        assert result.is_exceeded is True
        assert result.limit_times == 10
        assert result.remaining_requests == 0  # 10 - 10
        assert result.retry_after_ms == 5000
        expected_reset_time = mock_now + timedelta(milliseconds=5000)
        assert result.reset_time == expected_reset_time

    @pytest.mark.asyncio
    async def test_check_limit_calls_evalsha_correctly(self) -> None:
        """Test that check_limit calls evalsha with correct parameters."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.evalsha.return_value = [0, 1]

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha_123"

        mock_script = MagicMock()
        mock_script.extra_params.return_value = ["extra_param"]
        mock_script.parse_result.return_value = (0, 1)
        backend._lua_script = mock_script

        config = RateLimitConfig(times=5, milliseconds=2000)
        await backend.check_limit("my_key", config)

        mock_redis.evalsha.assert_called_once_with(
            "test_sha_123", 1, "my_key", "5", "2000", "extra_param"
        )

    @pytest.mark.asyncio
    async def test_check_limit_with_awaitable_result(self) -> None:
        """Test check_limit handling of awaitable Redis result."""

        async def async_result() -> list[int]:
            return [0, 2]

        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.evalsha.return_value = async_result()

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha"
        backend._lua_script = SlidingWindowScript()

        config = RateLimitConfig(times=10, seconds=60)
        result = await backend.check_limit("test_key", config)

        assert result.is_exceeded is False
        assert result.remaining_requests == 8  # 10 - 2

    @pytest.mark.asyncio
    async def test_maybe_await_with_awaitable(self) -> None:
        """Test _maybe_await with awaitable value."""

        async def async_value() -> str:
            return "async_result"

        result = await RedisLimiterBackend._maybe_await(async_value())
        assert result == "async_result"

    @pytest.mark.asyncio
    async def test_maybe_await_with_non_awaitable(self) -> None:
        """Test _maybe_await with non-awaitable value."""
        result = await RedisLimiterBackend._maybe_await("sync_result")
        assert result == "sync_result"

    @pytest.mark.asyncio
    async def test_maybe_await_with_coroutine(self) -> None:
        """Test _maybe_await properly handles coroutines."""

        async def coro_func() -> int:
            return 42

        coro = coro_func()
        result = await RedisLimiterBackend._maybe_await(coro)
        assert result == 42

    def test_maybe_await_is_static_method(self) -> None:
        """Test that _maybe_await is a static method."""
        assert inspect.isfunction(RedisLimiterBackend._maybe_await)


class TestRedisLimiterBackendFallbackHandling:
    """Test RedisLimiterBackend fallback handling for Redis errors."""

    @pytest.mark.asyncio
    async def test_check_limit_redis_connection_error_fallback_allow(self) -> None:
        """Test fallback to ALLOW mode on Redis connection error."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.evalsha.side_effect = redis_exc.ConnectionError("Connection failed")

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha"
        backend._lua_script = SlidingWindowScript()
        backend._fallback_mode = FallbackMode.ALLOW

        config = RateLimitConfig(times=10, seconds=60)
        result = await backend.check_limit("test_key", config)

        assert result.is_exceeded is False
        assert result.limit_times == 10

    @pytest.mark.asyncio
    async def test_check_limit_redis_error_fallback_deny(self) -> None:
        """Test fallback to DENY mode on Redis error."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.evalsha.side_effect = redis_exc.RedisError("Redis error")

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha"
        backend._lua_script = SlidingWindowScript()
        backend._fallback_mode = FallbackMode.DENY

        config = RateLimitConfig(times=10, seconds=60)
        result = await backend.check_limit("test_key", config)

        assert result.is_exceeded is True
        assert result.limit_times == 10
        assert result.retry_after_ms > 0

    @pytest.mark.asyncio
    async def test_check_limit_redis_error_fallback_raise(self) -> None:
        """Test fallback to RAISE mode on Redis error."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.evalsha.side_effect = redis_exc.TimeoutError("Timeout")

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha"
        backend._lua_script = SlidingWindowScript()
        backend._fallback_mode = FallbackMode.RAISE

        config = RateLimitConfig(times=10, seconds=60)

        with pytest.raises(LimiterBackendError, match="Redis unavailable: Timeout"):
            await backend.check_limit("test_key", config)

    @pytest.mark.asyncio
    async def test_check_limit_non_redis_error_not_handled(self) -> None:
        """Test that non-Redis errors are not handled by fallback."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.evalsha.side_effect = ValueError("Some other error")

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha"
        backend._lua_script = SlidingWindowScript()
        backend._fallback_mode = FallbackMode.ALLOW

        config = RateLimitConfig(times=10, seconds=60)

        # Should not be caught by fallback handler
        with pytest.raises(ValueError, match="Some other error"):
            await backend.check_limit("test_key", config)


class TestRedisLimiterBackendEdgeCases:
    """Test edge cases and unusual scenarios."""

    @pytest.mark.asyncio
    async def test_check_limit_with_zero_remaining_requests(self) -> None:
        """Test check_limit when exactly at the limit."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        mock_redis.evalsha.return_value = [0, 10]  # At limit but not exceeded

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha"
        backend._lua_script = SlidingWindowScript()

        config = RateLimitConfig(times=10, seconds=60)
        result = await backend.check_limit("test_key", config)

        assert result.is_exceeded is False
        assert result.remaining_requests == 0  # 10 - 10

    @pytest.mark.asyncio
    async def test_check_limit_with_negative_retry_after(self) -> None:
        """Test handling of negative retry_after values."""
        mock_redis = AsyncMock(spec=aredis.Redis)

        mock_script = MagicMock()
        mock_script.extra_params.return_value = []
        mock_script.parse_result.return_value = (-100, 5)  # Negative retry_after

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha"
        backend._lua_script = mock_script

        config = RateLimitConfig(times=10, seconds=60)
        result = await backend.check_limit("test_key", config)

        # Negative retry_after should be treated as not exceeded
        assert result.is_exceeded is False

    @pytest.mark.asyncio
    async def test_multiple_concurrent_check_limit_calls(self) -> None:
        """Test multiple concurrent check_limit calls."""
        mock_redis = AsyncMock(spec=aredis.Redis)

        call_count = 0

        async def mock_evalsha(*args):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate async delay
            return [0, call_count]

        mock_redis.evalsha = mock_evalsha

        backend = RedisLimiterBackend()
        backend._redis = mock_redis
        backend._script_sha = "test_sha"
        backend._lua_script = SlidingWindowScript()

        config = RateLimitConfig(times=10, seconds=60)

        # Run multiple concurrent calls
        tasks = [backend.check_limit(f"key_{i}", config) for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for result in results:
            assert isinstance(result, RateLimitResult)
            assert result.is_exceeded is False
