from fastapi import Request, Response

from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.exceptions import RateLimitExceeded


async def default_identifier(
    request: Request, trust_proxy_headers: bool = False
) -> str:
    """
    Creates a rate limiting key based on IP address and request path.
    """
    host = request.client.host if request.client else None
    if trust_proxy_headers:
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = host or "unknown"
    else:
        ip = host or "unknown"

    return f"{ip}:{request.scope['path']}"


async def http_default_callback(
    request: Request, response: Response, result: RateLimitResult
) -> None:
    """
    Default callback for rate-limited responses. Raises 429 with Retry-After header.
    """
    raise RateLimitExceeded(
        retry_after_ms=result.retry_after_ms,
        limit_times=result.limit_times,
        detail="Too Many Requests",
        reset_time=result.reset_time,
    )
