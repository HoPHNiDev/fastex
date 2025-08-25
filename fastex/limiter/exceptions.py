from datetime import datetime
from math import ceil

from fastapi import HTTPException, status


class RateLimitExceeded(HTTPException):
    """Exception for rate limit exceeded (HTTP 429)."""

    def __init__(
        self,
        retry_after_ms: int,
        limit_times: int,
        detail: str = "Rate limit exceeded",
        reset_time: datetime | None = None,
        remaining_requests: int | None = None,
    ) -> None:
        retry_after_seconds = ceil(retry_after_ms / 1000)

        headers = {"Retry-After": str(retry_after_seconds)}
        if limit_times:
            headers["RateLimit-Limit"] = str(limit_times)
        if reset_time:
            headers["RateLimit-Reset"] = reset_time.isoformat()
        if remaining_requests:
            headers["RateLimit-Remaining"] = str(remaining_requests)

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers=headers,
        )


class RateLimiterNotInitialized(RuntimeError):
    """Exception when the rate limiter is used before initialization."""

    def __init__(
        self, message: str = "Rate limiter must be initialized before use"
    ) -> None:
        super().__init__(message)
