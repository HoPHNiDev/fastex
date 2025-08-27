from datetime import datetime

from pydantic import BaseModel


class RateLimitResult(BaseModel):
    """Limit check result."""

    is_exceeded: bool
    retry_after_ms: int = 0
    limit_times: int
    remaining_requests: int | None = None
    reset_time: datetime | None = None

    class Config:
        extra = "forbid"
