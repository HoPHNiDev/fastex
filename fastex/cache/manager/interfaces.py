from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastex.cache.manager.key_builder import KeyBuilder
from fastex.cache.tags import CacheTagsEnum
from fastex.cache.tags.interfaces import AbstractCacheTags

R = TypeVar("R")


class ICacheManager(ABC):
    """Base Interface for Cache Managers"""

    key_builder: type[KeyBuilder]

    @abstractmethod
    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[R]],
        ttl: int,
        tag_manager: AbstractCacheTags | None = None,
    ) -> R: ...


class IDecoratorCacheManager(ICacheManager):
    """Interface for Cache Managers with Decorator Support"""

    @abstractmethod
    def cache_decorator(
        self,
        ttl: int = 3600,
        tags: list[str | CacheTagsEnum] | None = None,
        **kwargs: Any,
    ) -> Callable[..., Any]:
        raise NotImplementedError


class IHttpCacheManager(ICacheManager):
    """Interface for HTTP Caching"""

    @abstractmethod
    def cache_decorator(
        self,
        ttl: int = 3600,
        tags: list[str | CacheTagsEnum] | None = None,
        **kwargs: Any,
    ) -> Callable[..., Any]:
        raise NotImplementedError
