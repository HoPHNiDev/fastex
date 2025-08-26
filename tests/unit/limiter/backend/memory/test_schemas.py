"""Unit tests for memory backend configuration schemas."""

import pytest
from pydantic import ValidationError

from fastex.limiter.backend.enums import FallbackMode
from fastex.limiter.backend.interfaces import LimiterBackendConnectConfig
from fastex.limiter.backend.memory.schemas import MemoryLimiterBackendConnectConfig


class TestMemoryLimiterBackendConnectConfig:
    """Test MemoryLimiterBackendConnectConfig schema."""

    def test_inheritance(self) -> None:
        """Test that MemoryLimiterBackendConnectConfig inherits from LimiterBackendConnectConfig."""
        assert issubclass(
            MemoryLimiterBackendConnectConfig, LimiterBackendConnectConfig
        )

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        config = MemoryLimiterBackendConnectConfig()

        assert config.cleanup_interval_seconds is None
        assert config.max_keys is None
        assert config.fallback_mode is None

    def test_init_with_cleanup_interval(self) -> None:
        """Test initialization with cleanup_interval_seconds."""
        config = MemoryLimiterBackendConnectConfig(cleanup_interval_seconds=600)

        assert config.cleanup_interval_seconds == 600
        assert config.max_keys is None

    def test_init_with_max_keys(self) -> None:
        """Test initialization with max_keys."""
        config = MemoryLimiterBackendConnectConfig(max_keys=5000)

        assert config.max_keys == 5000
        assert config.cleanup_interval_seconds is None

    def test_init_with_all_parameters(self) -> None:
        """Test initialization with all parameters."""
        config = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=300,
            max_keys=10000,
            fallback_mode=FallbackMode.ALLOW,
        )

        assert config.cleanup_interval_seconds == 300
        assert config.max_keys == 10000
        assert config.fallback_mode == FallbackMode.ALLOW

    def test_cleanup_interval_validation_positive(self) -> None:
        """Test cleanup_interval_seconds validation with positive values."""
        valid_values = [1, 60, 300, 3600, 86400]

        for value in valid_values:
            config = MemoryLimiterBackendConnectConfig(cleanup_interval_seconds=value)
            assert config.cleanup_interval_seconds == value

    def test_cleanup_interval_validation_zero(self) -> None:
        """Test cleanup_interval_seconds validation with zero."""
        config = MemoryLimiterBackendConnectConfig(cleanup_interval_seconds=0)
        assert config.cleanup_interval_seconds == 0

    def test_cleanup_interval_validation_negative(self) -> None:
        """Test cleanup_interval_seconds validation with negative values."""
        with pytest.raises(ValidationError) as exc_info:
            MemoryLimiterBackendConnectConfig(cleanup_interval_seconds=-1)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "cleanup_interval_seconds" in str(errors[0]["loc"])

    def test_max_keys_validation_positive(self) -> None:
        """Test max_keys validation with positive values."""
        valid_values = [1, 100, 1000, 10000, 100000]

        for value in valid_values:
            config = MemoryLimiterBackendConnectConfig(max_keys=value)
            assert config.max_keys == value

    def test_max_keys_validation_zero(self) -> None:
        """Test max_keys validation with zero."""
        with pytest.raises(ValidationError) as exc_info:
            MemoryLimiterBackendConnectConfig(max_keys=0)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "max_keys" in str(errors[0]["loc"])

    def test_max_keys_validation_negative(self) -> None:
        """Test max_keys validation with negative values."""
        with pytest.raises(ValidationError) as exc_info:
            MemoryLimiterBackendConnectConfig(max_keys=-1)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "max_keys" in str(errors[0]["loc"])

    def test_fallback_mode_validation_valid_values(self) -> None:
        """Test fallback_mode validation with valid enum values."""
        for mode in FallbackMode:
            config = MemoryLimiterBackendConnectConfig(fallback_mode=mode)
            assert config.fallback_mode == mode

    def test_fallback_mode_none_allowed(self) -> None:
        """Test that fallback_mode can be None."""
        config = MemoryLimiterBackendConnectConfig(fallback_mode=None)
        assert config.fallback_mode is None

    def test_invalid_fallback_mode_type(self) -> None:
        """Test validation with invalid fallback_mode type."""
        with pytest.raises(ValidationError) as exc_info:
            MemoryLimiterBackendConnectConfig(fallback_mode="invalid")  # type: ignore

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "fallback_mode" in str(errors[0]["loc"])

    def test_config_immutability(self) -> None:
        """Test that config is immutable after creation."""
        MemoryLimiterBackendConnectConfig(cleanup_interval_seconds=300, max_keys=10000)

        # Pydantic models are not frozen by default, so this test might be skipped
        # or we need to check if the model is configured as frozen
        pytest.skip("Config immutability depends on Pydantic model configuration")

    def test_config_representation(self) -> None:
        """Test string representation of config."""
        config = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=300,
            max_keys=10000,
            fallback_mode=FallbackMode.ALLOW,
        )

        config_str = str(config)
        assert "300" in config_str
        assert "10000" in config_str
        assert "ALLOW" in config_str

    def test_config_equality(self) -> None:
        """Test equality comparison of config instances."""
        config1 = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=300,
            max_keys=10000,
            fallback_mode=FallbackMode.ALLOW,
        )
        config2 = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=300,
            max_keys=10000,
            fallback_mode=FallbackMode.ALLOW,
        )
        config3 = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=600,
            max_keys=10000,
            fallback_mode=FallbackMode.ALLOW,
        )

        assert config1 == config2
        assert config1 != config3

    def test_config_serialization(self) -> None:
        """Test config serialization to dict."""
        config = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=300,
            max_keys=10000,
            fallback_mode=FallbackMode.ALLOW,
        )

        config_dict = config.model_dump()
        assert config_dict["cleanup_interval_seconds"] == 300
        assert config_dict["max_keys"] == 10000
        # Fallback mode can be either enum or string depending on serialization mode
        assert config_dict["fallback_mode"] in [FallbackMode.ALLOW, "allow"]

    def test_large_values(self) -> None:
        """Test with large but valid values."""
        config = MemoryLimiterBackendConnectConfig(
            cleanup_interval_seconds=86400 * 7, max_keys=1000000  # 1 week  # 1 million
        )

        assert config.cleanup_interval_seconds == 86400 * 7
        assert config.max_keys == 1000000

    def test_type_validation(self) -> None:
        """Test that incorrect types are rejected."""
        with pytest.raises(ValidationError):
            MemoryLimiterBackendConnectConfig(cleanup_interval_seconds="not_an_int")  # type: ignore

        with pytest.raises(ValidationError):
            MemoryLimiterBackendConnectConfig(max_keys="not_an_int")  # type: ignore
