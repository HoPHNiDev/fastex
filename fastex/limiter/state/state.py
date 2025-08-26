from fastex.limiter.backend.interfaces import LimiterBackend
from fastex.limiter.config import limiter_settings
from fastex.limiter.exceptions import RateLimiterNotInitialized
from fastex.limiter.state import (
    CallbackFunction,
    IdentifierFunction,
    ILimiterState,
    LimiterStateConfigWithBackend,
)
from fastex.limiter.utils import default_identifier, http_default_callback
from fastex.utils import singleton


@singleton
class LimiterState(ILimiterState):
    """Manages limiter configuration state."""

    def __init__(
        self,
        backend: LimiterBackend | None = None,
        prefix: str | None = None,
        trust_proxy_headers: bool | None = None,
        identifier: IdentifierFunction | None = default_identifier,
        callback: CallbackFunction | None = http_default_callback,
    ) -> None:
        self._backend = backend
        self._prefix = prefix or limiter_settings.DEFAULT_PREFIX
        self._trust_proxy_headers = (
            trust_proxy_headers or limiter_settings.TRUST_PROXY_HEADERS
        )
        self._identifier = identifier
        self._callback = callback

    @property
    def backend(self) -> LimiterBackend:
        if not self._backend:
            raise RateLimiterNotInitialized("Backend not set")
        return self._backend

    @property
    def prefix(self) -> str:
        return self._prefix

    @property
    def trust_proxy_headers(self) -> bool:
        return self._trust_proxy_headers

    @property
    def identifier(self) -> IdentifierFunction:
        if not self._identifier:
            raise RateLimiterNotInitialized("Identifier function not set")
        return self._identifier

    @property
    def callback(self) -> CallbackFunction:
        if not self._callback:
            raise RateLimiterNotInitialized("Callback function not set")
        return self._callback

    def configure(self, config: LimiterStateConfigWithBackend) -> None:
        """Updates the limiter state with new configuration values."""
        if config.backend is not None:
            self._backend = config.backend
        if config.prefix is not None:
            self._prefix = config.prefix
        if config.trust_proxy_headers is not None:
            self._trust_proxy_headers = config.trust_proxy_headers
        if config.identifier is not None:
            self._identifier = config.identifier
        if config.callback is not None:
            self._callback = config.callback
