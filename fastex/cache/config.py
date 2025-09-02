from pydantic_settings import BaseSettings, SettingsConfigDict

from fastex.utils import singleton


@singleton
class CacheSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CACHE_", env_file=".env", case_sensitive=False
    )

    TAGS_ENABLED: bool = True
    PARSE_FROM_PARAMS: bool = True
    DEFAULT_TTL: int = 300  # seconds


cache_settings = CacheSettings()
