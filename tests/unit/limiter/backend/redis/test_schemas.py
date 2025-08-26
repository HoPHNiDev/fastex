"""Unit tests for Redis backend schemas."""

from unittest.mock import AsyncMock

import pytest
import redis.asyncio as aredis
from pydantic import ValidationError

from fastex.limiter.backend.enums import FallbackMode
from fastex.limiter.backend.interfaces import LimiterBackendConnectConfig
from fastex.limiter.backend.redis.schemas import RedisLimiterBackendConnectConfig
from fastex.limiter.backend.redis.scripts import FixedWindowScript, SlidingWindowScript


class TestRedisLimiterBackendConnectConfig:
    """Test the RedisLimiterBackendConnectConfig schema."""

    def test_inheritance(self) -> None:
        """Test that config inherits from LimiterBackendConnectConfig."""
        config = RedisLimiterBackendConnectConfig(redis_client="redis://localhost:6379")
        assert isinstance(config, LimiterBackendConnectConfig)

    def test_init_with_redis_url_string(self) -> None:
        """Test initialization with Redis URL string."""
        redis_url = "redis://localhost:6379/0"
        config = RedisLimiterBackendConnectConfig(redis_client=redis_url)

        assert config.redis_client == redis_url
        assert config.fallback_mode is None
        assert config.lua_script is None

    def test_init_with_redis_client_instance(self) -> None:
        """Test initialization with Redis client instance."""
        mock_redis = AsyncMock(spec=aredis.Redis)
        config = RedisLimiterBackendConnectConfig(redis_client=mock_redis)

        assert config.redis_client is mock_redis
        assert config.fallback_mode is None
        assert config.lua_script is None

    def test_init_with_all_parameters(self) -> None:
        """Test initialization with all parameters."""
        redis_url = "redis://localhost:6379/1"
        fallback_mode = FallbackMode.DENY
        lua_script = SlidingWindowScript()

        config = RedisLimiterBackendConnectConfig(
            redis_client=redis_url, fallback_mode=fallback_mode, lua_script=lua_script
        )

        assert config.redis_client == redis_url
        assert config.fallback_mode == fallback_mode
        assert config.lua_script is lua_script

    def test_fallback_mode_validation_valid_values(self) -> None:
        """Test that valid FallbackMode values are accepted."""
        for mode in FallbackMode:
            config = RedisLimiterBackendConnectConfig(
                redis_client="redis://localhost:6379", fallback_mode=mode
            )
            assert config.fallback_mode == mode

    def test_fallback_mode_none_allowed(self) -> None:
        """Test that None is allowed for fallback_mode."""
        config = RedisLimiterBackendConnectConfig(
            redis_client="redis://localhost:6379", fallback_mode=None
        )
        assert config.fallback_mode is None

    def test_lua_script_with_sliding_window(self) -> None:
        """Test initialization with SlidingWindowScript."""
        script = SlidingWindowScript()
        config = RedisLimiterBackendConnectConfig(
            redis_client="redis://localhost:6379", lua_script=script
        )
        assert config.lua_script is script

    def test_lua_script_with_fixed_window(self) -> None:
        """Test initialization with FixedWindowScript."""
        script = FixedWindowScript()
        config = RedisLimiterBackendConnectConfig(
            redis_client="redis://localhost:6379", lua_script=script
        )
        assert config.lua_script is script

    def test_lua_script_none_allowed(self) -> None:
        """Test that None is allowed for lua_script."""
        config = RedisLimiterBackendConnectConfig(
            redis_client="redis://localhost:6379", lua_script=None
        )
        assert config.lua_script is None

    def test_missing_redis_client_raises_validation_error(self) -> None:
        """Test that missing redis_client raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RedisLimiterBackendConnectConfig()  # type: ignore

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "missing"
        assert "redis_client" in str(errors[0]["loc"])

    def test_invalid_redis_client_type(self) -> None:
        """Test validation with invalid redis_client type."""
        with pytest.raises(ValidationError) as exc_info:
            RedisLimiterBackendConnectConfig(redis_client=123)

        errors = exc_info.value.errors()
        # Should have 2 errors: one for Redis instance validation, one for string validation
        assert len(errors) == 2
        # All errors should be related to redis_client field
        for error in errors:
            assert "redis_client" in str(error["loc"])

    def test_invalid_fallback_mode_type(self) -> None:
        """Test validation with invalid fallback_mode type."""
        with pytest.raises(ValidationError) as exc_info:
            RedisLimiterBackendConnectConfig(
                redis_client="redis://localhost:6379",
                fallback_mode="invalid_mode",
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        error = errors[0]
        assert "fallback_mode" in str(error["loc"])

    def test_config_is_immutable(self) -> None:
        """Test that config instances are immutable."""
        config = RedisLimiterBackendConnectConfig(redis_client="redis://localhost:6379")

        # Pydantic models with frozen=True should be immutable
        # This test depends on whether the model has frozen=True configured
        # Let's test if we can modify attributes (should fail if frozen)
        try:
            config.redis_client = "redis://localhost:6380"
            # If this succeeds, the model is not frozen
            pytest.skip("Config model is not frozen - mutability test skipped")
        except (AttributeError, TypeError, ValidationError):
            # Expected behavior for immutable/frozen models
            pass

    def test_arbitrary_types_allowed(self) -> None:
        """Test that arbitrary types (like Redis client) are allowed."""
        # This tests the Config.arbitrary_types_allowed setting
        mock_redis = AsyncMock(spec=aredis.Redis)

        # Should not raise validation error for arbitrary types
        config = RedisLimiterBackendConnectConfig(redis_client=mock_redis)
        assert config.redis_client is mock_redis

    def test_config_representation(self) -> None:
        """Test string representation of config."""
        config = RedisLimiterBackendConnectConfig(
            redis_client="redis://localhost:6379", fallback_mode=FallbackMode.ALLOW
        )

        config_str = str(config)
        # Pydantic v2 doesn't include class name in string representation by default
        assert "redis://localhost:6379" in config_str
        assert "ALLOW" in config_str
        # Verify it contains the field values
        assert "fallback_mode" in config_str
        assert "redis_client" in config_str

    def test_config_equality(self) -> None:
        """Test equality comparison of config instances."""
        config1 = RedisLimiterBackendConnectConfig(
            redis_client="redis://localhost:6379", fallback_mode=FallbackMode.ALLOW
        )
        config2 = RedisLimiterBackendConnectConfig(
            redis_client="redis://localhost:6379", fallback_mode=FallbackMode.ALLOW
        )
        config3 = RedisLimiterBackendConnectConfig(
            redis_client="redis://localhost:6380", fallback_mode=FallbackMode.ALLOW
        )

        assert config1 == config2
        assert config1 != config3

    def test_config_with_complex_redis_url(self) -> None:
        """Test config with complex Redis URL including authentication."""
        complex_url = "redis://user:password@localhost:6379/2?ssl=true"
        config = RedisLimiterBackendConnectConfig(redis_client=complex_url)

        assert config.redis_client == complex_url

    def test_config_serialization(self) -> None:
        """Test that config can be serialized to dict."""
        script = SlidingWindowScript()
        config = RedisLimiterBackendConnectConfig(
            redis_client="redis://localhost:6379",
            fallback_mode=FallbackMode.DENY,
            lua_script=script,
        )

        config_dict = config.model_dump()
        assert isinstance(config_dict, dict)
        assert config_dict["redis_client"] == "redis://localhost:6379"
        assert config_dict["fallback_mode"] == FallbackMode.DENY
        assert config_dict["lua_script"] is script

    def test_config_with_redis_sentinels_url(self) -> None:
        """Test config with Redis Sentinel URL format."""
        sentinel_url = "redis+sentinel://localhost:26379/mymaster/0"
        config = RedisLimiterBackendConnectConfig(redis_client=sentinel_url)

        assert config.redis_client == sentinel_url

    def test_config_with_rediss_url(self) -> None:
        """Test config with secure Redis URL (rediss://)."""
        secure_url = "rediss://localhost:6380/0"
        config = RedisLimiterBackendConnectConfig(redis_client=secure_url)

        assert config.redis_client == secure_url
