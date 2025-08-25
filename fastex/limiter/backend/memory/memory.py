import asyncio
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastex.limiter.backend.base import BaseLimiterBackend
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.interfaces import LimiterBackendConnectConfig
from fastex.limiter.backend.memory.schemas import MemoryLimiterBackendConnectConfig
from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.config import limiter_settings
from fastex.limiter.schemas import RateLimitConfig
from fastex.logging import log


class InMemoryLimiterBackend(BaseLimiterBackend):
    """
    In-memory rate limiter backend using sliding window algorithm.

    This backend is suitable for:
    - Development and testing environments
    - Single-instance applications
    - Applications where Redis is not available

    Features:
    - Thread-safe operations using asyncio locks
    - Automatic cleanup of expired entries
    - Memory-efficient sliding window implementation
    - Configurable cleanup intervals
    - Fallback mode support

    Note: Data is not persistent and will be lost on restart.
    """

    def __init__(
        self,
        cleanup_interval_seconds: int = 300,  # 5 minutes
        max_keys: int = 10000,  # Memory protection
    ) -> None:
        """
        Initialize in-memory backend.

        Args:
            cleanup_interval_seconds: How often to run cleanup of expired entries
            max_keys: Maximum number of keys to store (memory protection)
        """
        self._store: dict[str, list[float]] = defaultdict(list)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._global_lock = asyncio.Lock()
        self._connected = False
        self._cleanup_interval = cleanup_interval_seconds
        self._max_keys = max_keys
        self._cleanup_task: asyncio.Task[Any] | None = None
        self._last_cleanup = time.time()

    async def connect(
        self,
        config: LimiterBackendConnectConfig,
    ) -> None:
        """
        Connect the in-memory backend.

        Args:
            config: LimiterBackendConfig[MemoryLimiterBackendConfig] - Configuration for the backend **NOT OPTIONAL**
        """
        if not isinstance(config, MemoryLimiterBackendConnectConfig):
            raise LimiterBackendError(
                "Invalid config type. Expected MemoryLimiterBackendConfig"
            )
        if config.cleanup_interval_seconds is not None:
            self._cleanup_interval = config.cleanup_interval_seconds
        if config.max_keys is not None:
            self._max_keys = config.max_keys

        self._fallback_mode = config.fallback_mode or limiter_settings.FALLBACK_MODE
        self._connected = True

        self._cleanup_task = asyncio.create_task(self._background_cleanup())

        log.debug(
            f"InMemoryLimiterBackend connected with cleanup_interval={self._cleanup_interval}s, "
            f"max_keys={self._max_keys}, fallback_mode={self.fallback_mode.value}"
        )

    async def disconnect(self) -> None:
        """Disconnect and cleanup resources."""
        self._connected = False

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Clear all data
        async with self._global_lock:
            self._store.clear()
            self._locks.clear()

        log.debug("InMemoryLimiterBackend disconnected and cleaned up")

    async def check_limit(self, key: str, config: RateLimitConfig) -> RateLimitResult:
        """
        Check if rate limit is exceeded for the given key.

        Uses sliding window algorithm for accurate rate limiting.

        Args:
            key: Unique identifier for rate limiting
            config: Rate limit configuration

        Returns:
            RateLimitResult with limit check results

        Raises:
            LimiterBackendError: If backend is not connected
        """
        if not self._connected:
            raise LimiterBackendError("In-memory backend is not connected")

        # Memory protection check
        if len(self._store) >= self._max_keys and key not in self._store:
            log.warning(
                f"Memory backend reached max_keys limit ({self._max_keys}), "
                f"applying fallback mode: {self.fallback_mode.value}"
            )
            return await self._handle_memory_limit_exceeded(config)

        now_ms = time.time() * 1000
        window_start_ms = now_ms - config.total_milliseconds

        # Use per-key lock for thread safety
        async with self._locks[key]:
            # Clean up old entries for this key
            timestamps = self._store[key]
            valid_timestamps = [ts for ts in timestamps if ts > window_start_ms]
            self._store[key] = valid_timestamps

            current_count = len(valid_timestamps)

            if current_count >= config.times:
                # Rate limit exceeded
                oldest_timestamp = min(valid_timestamps) if valid_timestamps else now_ms
                retry_after_ms = int(
                    oldest_timestamp + config.total_milliseconds - now_ms
                )
                reset_time = datetime.fromtimestamp(
                    (oldest_timestamp + config.total_milliseconds) / 1000
                )

                log.debug(
                    f"Rate limit exceeded for key '{key}': {current_count}/{config.times} "
                    f"requests, retry_after={retry_after_ms}ms"
                )

                return RateLimitResult(
                    is_exceeded=True,
                    retry_after_ms=max(retry_after_ms, 0),
                    limit_times=config.times,
                    remaining_requests=0,
                    reset_time=reset_time,
                )

            # Add current request
            self._store[key].append(now_ms)
            remaining_requests = config.times - current_count - 1

            log.debug(
                f"Request allowed for key '{key}': {current_count + 1}/{config.times} "
                f"requests, remaining={remaining_requests}"
            )

            return RateLimitResult(
                is_exceeded=False,
                limit_times=config.times,
                remaining_requests=remaining_requests,
            )

    def is_connected(self, raise_exc: bool = False) -> bool:
        """
        Check if backend is connected.

        Args:
            raise_exc: Whether to raise exception if not connected

        Returns:
            True if connected, False otherwise

        Raises:
            LimiterBackendError: If not connected and raise_exc=True
        """
        if not self._connected and raise_exc:
            raise LimiterBackendError("In-memory backend is not connected")
        return self._connected

    async def _handle_memory_limit_exceeded(
        self, config: RateLimitConfig
    ) -> RateLimitResult:
        """Handle situation when memory limit is exceeded."""
        error = f"Memory backend reached max_keys limit ({self._max_keys})"
        return await self._handle_fallback(error, config)

    async def _background_cleanup(self) -> None:
        """Background task for periodic cleanup of expired entries."""
        while self._connected:
            try:
                await asyncio.sleep(self._cleanup_interval)
                if not self._connected:
                    break
                await self._cleanup_expired_entries()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in background cleanup: {e}")

    async def _cleanup_expired_entries(self) -> None:
        """Remove expired entries from all keys to free memory."""
        now_ms = time.time() * 1000
        keys_to_remove = []
        cleaned_count = 0

        async with self._global_lock:
            for key in list(self._store.keys()):
                # Get lock for this key
                async with self._locks[key]:
                    timestamps = self._store[key]
                    original_count = len(timestamps)

                    # Keep only recent entries (use 24h window for cleanup)
                    cleanup_window_ms = 24 * 60 * 60 * 1000  # 24 hours
                    valid_timestamps = [
                        ts for ts in timestamps if ts > now_ms - cleanup_window_ms
                    ]

                    if not valid_timestamps:
                        keys_to_remove.append(key)
                    else:
                        self._store[key] = valid_timestamps
                        cleaned_count += original_count - len(valid_timestamps)

            # Remove empty keys
            for key in keys_to_remove:
                del self._store[key]
                if key in self._locks:
                    del self._locks[key]

        if keys_to_remove or cleaned_count:
            log.debug(
                f"Cleanup completed: removed {len(keys_to_remove)} empty keys, "
                f"cleaned {cleaned_count} expired entries, "
                f"total keys: {len(self._store)}"
            )

        self._last_cleanup = time.time()

    def get_stats(self) -> dict[str, int]:
        """Get backend statistics for monitoring."""
        return {
            "total_keys": len(self._store),
            "total_entries": sum(
                len(timestamps) for timestamps in self._store.values()
            ),
            "last_cleanup_seconds_ago": int(time.time() - self._last_cleanup),
            "max_keys_limit": self._max_keys,
        }

    async def clear_key(self, key: str) -> bool:
        """
        Clear all entries for a specific key.

        Args:
            key: Key to clear

        Returns:
            True if key existed and was cleared, False otherwise
        """
        async with self._locks[key]:
            if key in self._store:
                del self._store[key]
                if key in self._locks:
                    del self._locks[key]
                return True
            return False

    async def clear_all(self) -> None:
        """Clear all stored data."""
        async with self._global_lock:
            self._store.clear()
            self._locks.clear()
        log.debug("All in-memory rate limit data cleared")
