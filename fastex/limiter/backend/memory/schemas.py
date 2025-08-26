from typing import Any

from pydantic import field_validator

from fastex.limiter.backend.interfaces import LimiterBackendConnectConfig


class MemoryLimiterBackendConnectConfig(LimiterBackendConnectConfig):
    cleanup_interval_seconds: int | None = None
    max_keys: int | None = None

    @field_validator("cleanup_interval_seconds")
    @classmethod
    def validate_cleanup_interval(cls, v: Any) -> int | None:
        """Validate cleanup_interval_seconds."""
        if v is None:
            return v
        if not isinstance(v, int):
            raise ValueError("cleanup_interval_seconds must be an integer")
        if v < 0:
            raise ValueError("cleanup_interval_seconds must be non-negative")
        return v

    @field_validator("max_keys")
    @classmethod
    def validate_max_keys(cls, v: Any) -> int | None:
        """Validate max_keys."""
        if v is None:
            return v
        if not isinstance(v, int):
            raise ValueError("max_keys must be an integer")
        if v <= 0:
            raise ValueError("max_keys must be positive")
        return v
