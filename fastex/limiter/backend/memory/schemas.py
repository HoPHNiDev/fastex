from fastex.limiter.backend.interfaces import LimiterBackendConnectConfig


class MemoryLimiterBackendConnectConfig(LimiterBackendConnectConfig):
    cleanup_interval_seconds: int | None = None
    max_keys: int | None = None
