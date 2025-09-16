from pydantic_settings import BaseSettings, SettingsConfigDict

from fastex.utils import singleton


@singleton
class CacheSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CACHE__", env_file=".env", case_sensitive=False
    )

    TAGS_ENABLED: bool = True
    DEFAULT_TTL: int = 3600  # seconds


cache_settings = CacheSettings()
