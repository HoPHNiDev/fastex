from typing import Any

from pydantic import BaseModel, Field, model_validator


class RateLimitConfig(BaseModel):
    """Pydantic model for rate limit configuration."""

    times: int = Field(ge=1, description="Allowed number of requests", default=1)
    milliseconds: int = Field(ge=0, default=0)
    seconds: int = Field(ge=0, default=0)
    minutes: int = Field(ge=0, default=0)
    hours: int = Field(ge=0, default=0)

    @model_validator(mode="before")
    @classmethod
    def validate_time_window(cls, data: Any) -> Any:
        """Check that the total time window is greater than 0."""
        total_ms = (
            data.get("milliseconds", 0)
            + 1000 * data.get("seconds", 0)
            + 60_000 * data.get("minutes", 0)
            + 3_600_000 * data.get("hours", 0)
        )

        if total_ms <= 0:
            raise ValueError("Rate limiter window must be greater than 0ms.")

        return data

    @property
    def total_milliseconds(self) -> int:
        """Return total time window in milliseconds."""
        return (
            self.milliseconds
            + 1000 * self.seconds
            + 60_000 * self.minutes
            + 3_600_000 * self.hours
        )

    class Config:
        frozen = True
