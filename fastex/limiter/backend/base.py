from abc import abstractmethod

from fastex.limiter.backend.enums import FallbackMode
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.interfaces import LimiterBackend
from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.config import limiter_settings
from fastex.limiter.schemas import RateLimitConfig
from fastex.logging.logger import FastexLogger


class BaseLimiterBackend(LimiterBackend):
    """Base class for all limiter backends."""

    _fallback_mode: FallbackMode | None = None
    logger: FastexLogger

    async def _handle_fallback(
        self, error: Exception | str, config: RateLimitConfig
    ) -> RateLimitResult:
        match self.fallback_mode:
            case FallbackMode.ALLOW:
                self.logger.warning(f"Redis unavailable: {error}. Allowing request.")
                return RateLimitResult(is_exceeded=False, limit_times=config.times)

            case FallbackMode.DENY:
                self.logger.warning(f"Redis unavailable: {error}. Denying request.")
                return RateLimitResult(
                    is_exceeded=True,
                    limit_times=config.times,
                    retry_after_ms=limiter_settings.DENY_FALLBACK_RETRY_AFTER_MS,
                )

            case FallbackMode.RAISE:
                raise LimiterBackendError(f"Redis unavailable: {error}")

            case _:
                raise LimiterBackendError(
                    f"Unknown fallback mode: {self.fallback_mode}"
                )

    @abstractmethod
    async def connect(self, *args, **kwargs):
        """Connect to the backend service."""
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the backend service."""
        raise NotImplementedError

    @abstractmethod
    async def check_limit(self, key: str, config: RateLimitConfig) -> RateLimitResult:
        """Check if the given key exceeds the rate limit."""
        raise NotImplementedError

    def is_connected(self, raise_exc: bool = False) -> bool:
        """Check if the backend is connected."""
        raise NotImplementedError

    @property
    def fallback_mode(self) -> FallbackMode:
        if not self._fallback_mode:
            raise LimiterBackendError("Fallback mode not set")
        return self._fallback_mode
