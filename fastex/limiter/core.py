from fastex.limiter.backend.interfaces import LimiterBackend
from fastex.limiter.state import limiter_state
from fastex.limiter.state.schemas import (
    LimiterStateConfig,
    LimiterStateConfigWithBackend,
)
from fastex.logging.logger import FastexLogger

logger = FastexLogger("LimiterCore")


async def configure_limiter(
    backend: LimiterBackend, config: LimiterStateConfig | None = None
) -> None:
    """Configures the global limiter state.

    Args:
        backend (LimiterBackend): The backend instance to use for rate limiting.
        config (LimiterStateConfig | None): Optional configuration overrides.
    """
    if not isinstance(backend, LimiterBackend):
        raise TypeError("backend must be an instance of LimiterBackend")

    backend.is_connected()
    logger.debug("Checked that backend is connected")

    config_params = config.model_dump() if config else {}
    config_params["backend"] = backend
    config = LimiterStateConfigWithBackend.model_validate(config_params)
    logger.debug("Checked that config is valid")

    limiter_state.configure(config)
    logger.debug("Limiter state configured")
