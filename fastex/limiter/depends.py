from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Request, Response
from pydantic import Field

from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.config import limiter_settings
from fastex.limiter.schemas import RateLimitConfig
from fastex.limiter.state import limiter_state
from fastex.limiter.state.interfaces import ILimiterState
from fastex.logging.logger import FastexLogger


class RateLimiter:
    """
    HTTP rate limiter dependency for FastAPI endpoints.
    Applies rate-limiting logic via Redis and Lua scripting.
    """

    state: ILimiterState = limiter_state
    logger = FastexLogger("RateLimiter")

    def __init__(
        self,
        times: Annotated[int, Field(ge=1)] = 1,
        milliseconds: Annotated[int, Field(ge=0)] = 0,
        seconds: Annotated[int, Field(ge=0)] = 0,
        minutes: Annotated[int, Field(ge=0)] = 0,
        hours: Annotated[int, Field(ge=0)] = 0,
        identifier: Callable[[Request], Awaitable[str]] | None = None,
        callback: (
            Callable[[Request, Response, RateLimitResult], Awaitable[None]] | None
        ) = None,
    ) -> None:
        """
        Initialize the rate limiter with time windows and custom behaviors.

        Args:
            times: Number of allowed requests in the time window
            milliseconds/seconds/minutes/hours: Time window duration
            identifier: Async function to generate unique rate-limit key
            callback: Async function to call when limit exceeded
        """
        self.config = RateLimitConfig(
            times=times or limiter_settings.DEFAULT_TIMES,
            seconds=seconds or limiter_settings.DEFAULT_WINDOW_SECONDS,
            milliseconds=milliseconds,
            minutes=minutes,
            hours=hours,
        )

        self.identifier = identifier or self.state.identifier
        self.callback = callback or self.state.callback

    async def _get_key(self, request: Request) -> str:
        route_index = 0
        dep_index = 0
        for i, route in enumerate(request.app.routes):
            if route.path == request.scope["path"] and request.method in route.methods:
                route_index = i
                for j, dependency in enumerate(route.dependencies):
                    if self is dependency.dependency:
                        dep_index = j
                        break

        rate_key = await self.identifier(request)
        key = f"{self.state.prefix}:{rate_key}:{route_index}:{dep_index}"
        self.logger.debug(f"Generated rate limit key: {key}")

        return key

    async def __call__(self, request: Request, response: Response) -> None:
        """
        FastAPI-compatible call method that applies rate limiting.

        Raises:
            HTTPException 429 if limit is exceeded
        """
        self.state.backend.is_connected(raise_exc=True)

        key = await self._get_key(request)
        self.logger.debug(f"Key: {key}")

        result = await self.state.backend.check_limit(key, self.config)

        if result.is_exceeded:
            self.logger.warning(
                f"Limit exceeded for key: {key}, will retry after {result.retry_after_ms}ms"
            )
            await self.callback(request, response, result)
