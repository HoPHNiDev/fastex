from typing import Any

from pydantic import BaseModel, model_validator

from fastex.limiter.backend.interfaces import LimiterBackend
from fastex.limiter.state.interfaces import (
    CallbackFunction,
    IdentifierFunction,
)


class LimiterStateConfig(BaseModel):
    """State of the limiter config."""

    prefix: str | None = None
    trust_proxy_headers: bool | None = None
    identifier: IdentifierFunction | None = None
    callback: CallbackFunction | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_config(cls, data: Any) -> Any:
        if not data or not isinstance(data, dict) or not any(data.values()):
            raise ValueError("At least one configuration field must be provided.")
        return data

    class Config:
        arbitrary_types_allowed = True


class LimiterStateConfigWithBackend(LimiterStateConfig):
    """State of the limiter config with mandatory backend."""

    backend: LimiterBackend | None = None
