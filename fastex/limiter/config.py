from pydantic_settings import BaseSettings, SettingsConfigDict

from fastex.limiter.backend.enums import FallbackMode
from fastex.utils import singleton


@singleton
class LimiterSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LIMITER_", env_file=".env", case_sensitive=False
    )

    DEFAULT_TIMES: int = 100
    DEFAULT_WINDOW_SECONDS: int = 60
    DEFAULT_PREFIX: str = "limiter"
    TRUST_PROXY_HEADERS: bool = False

    FALLBACK_MODE: FallbackMode = FallbackMode.ALLOW
    DENY_FALLBACK_RETRY_AFTER_MS: int = 60000  # 1 minute


limiter_settings = LimiterSettings()
