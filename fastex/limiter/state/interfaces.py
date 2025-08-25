from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from fastapi import Request, Response

from fastex.limiter.backend.interfaces import LimiterBackend
from fastex.limiter.backend.schemas import RateLimitResult

if TYPE_CHECKING:
    from fastex.limiter.state.schemas import LimiterStateConfigWithBackend


@runtime_checkable
class IdentifierFunction(Protocol):
    """Protocol for request identifier functions."""

    async def __call__(
        self, request: Request, trust_proxy_headers: bool = False
    ) -> str:
        """Generate unique identifier for rate limiting."""
        ...


@runtime_checkable
class CallbackFunction(Protocol):
    """Protocol for rate limit exceeded callback functions."""

    async def __call__(
        self, request: Request, response: Response, result: RateLimitResult
    ) -> None:
        """Handle rate limit exceeded event."""
        ...


class ILimiterState(ABC):
    """Interface for limiter state management."""

    @property
    @abstractmethod
    def backend(self) -> LimiterBackend:
        """Get the backend type."""
        raise NotImplementedError

    @property
    @abstractmethod
    def prefix(self) -> str:
        """Get the prefix used in keys."""
        raise NotImplementedError

    @property
    @abstractmethod
    def trust_proxy_headers(self) -> bool:
        """Check if proxy headers are trusted."""
        raise NotImplementedError

    @property
    @abstractmethod
    def identifier(self) -> IdentifierFunction:
        """Get the identifier function."""
        raise NotImplementedError

    @property
    @abstractmethod
    def callback(self) -> CallbackFunction:
        """Get the callback function."""
        raise NotImplementedError

    @abstractmethod
    def configure(self, config: "LimiterStateConfigWithBackend") -> None:
        """Configure the limiter state."""
        raise NotImplementedError
