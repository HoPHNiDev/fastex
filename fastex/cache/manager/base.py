from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastex.cache.backend.interfaces import CacheBackend
from fastex.cache.manager.interfaces import ICacheManager
from fastex.cache.tags import CacheTagsEnum
from fastex.cache.tags.interfaces import AbstractCacheTags
from fastex.logging.logger import FastexLogger

R = TypeVar("R")


class BaseCacheManager(ICacheManager):
    """Base Cache Manager with common functionality"""

    def __init__(
        self,
        backend: CacheBackend,
        tag_manager: type[AbstractCacheTags],
    ):
        self.tag_manager = tag_manager
        self.backend = backend
        self.logger = FastexLogger(self.__class__.__name__)

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[R]],
        ttl: int,
        tag_manager: AbstractCacheTags | None = None,
    ) -> R:
        """Get a value from the cache or set it using the factory function if not present."""
        cached: R = await self.backend.get_value(key)
        if cached is not None:
            self.logger.info("Cache hit for key: %s", key)
            return cached

        self.logger.info("Cache miss for key: %s", key)
        result = await factory()

        await self.backend.set_value(key, result, ttl)

        if tag_manager:
            await tag_manager.set_tags(key)

        return result

    async def invalidate_by_tags(
        self,
        tags: list[str | CacheTagsEnum],
        excluded_tags: list[str | CacheTagsEnum],
    ) -> None:
        """Invalidate cache entries by tags."""
        await self.tag_manager(backend=self.backend).invalidate_tags(
            tags, excluded_tags
        )
