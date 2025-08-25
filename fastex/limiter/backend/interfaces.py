from abc import ABC, abstractmethod
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from fastex.limiter.backend import FallbackMode
from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.schemas import RateLimitConfig


class ConnectProtocol(Protocol):
    @abstractmethod
    async def connect(self, *args: Any, **kwargs: Any) -> None: ...


class LimiterBackendConnectConfig(BaseModel):
    """Configuration model for LimiterBackend."""

    fallback_mode: FallbackMode | None = None

    class Config:
        arbitrary_types_allowed = True


BackendConfig = TypeVar("BackendConfig", bound=LimiterBackendConnectConfig)


class LimiterBackend(ABC):
    """Interface for rate limiter backends."""

    @abstractmethod
    async def connect(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
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
