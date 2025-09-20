from collections.abc import Awaitable, Callable
from functools import wraps
from types import FunctionType
from typing import Any, TypeVar, cast

from fastex.cache.backend.interfaces import ICacheBackend
from fastex.cache.config import cache_settings
from fastex.cache.manager.base import BaseCacheManager
from fastex.cache.manager.interfaces import IDecoratorCacheManager
from fastex.cache.manager.key_builder.key_builder import FunctionKeyBuilder
from fastex.cache.tags import CacheTagsEnum
from fastex.cache.tags.extractor.interfaces import ITagExtractor
from fastex.cache.tags.interfaces import ICacheTags
from fastex.utils import _filter_arguments, maybe_await

R = TypeVar("R")


class FunctionCacheManager(BaseCacheManager, IDecoratorCacheManager):
    """Manager for Function Caching"""

    key_builder = FunctionKeyBuilder

    def __init__(
        self,
        backend: ICacheBackend,
        tag_manager: type[ICacheTags],
        tag_extractors: list[ITagExtractor] | None = None,
    ):
        super().__init__(backend, tag_manager)
        self.tag_extractors = tag_extractors or []

    def cache_decorator(
        self,
        ttl: int = cache_settings.DEFAULT_TTL,
        tags: list[str | CacheTagsEnum] | None = None,
        **kwargs: Any,
    ) -> Callable[..., Any]:
        """Decorator for function caching"""
        if tags is None:
            tags = []

        def wrapper(
            func: Callable[..., R | Awaitable[R]],
        ) -> Callable[..., Awaitable[R]]:
            @wraps(func)
            async def inner(*args: Any, **func_kwargs: Any) -> R:
                tag_manager = self.tag_manager(
                    backend=self.backend, tags=tags, extractors=self.tag_extractors
                )
                filtered_kwargs = _filter_arguments(func, *args, **func_kwargs)

                cache_key = await self.key_builder.build_key(
                    cast(FunctionType, func), **filtered_kwargs
                )

                context = {"parameters": filtered_kwargs}
                await tag_manager.extract_tags(context=context)

                async def factory() -> R:
                    result = await maybe_await(func(*args, **func_kwargs))

                    result_context = {"result": result}
                    await tag_manager.extract_tags(context=result_context)

                    return result

                return await self.get_or_set(cache_key, factory, ttl, tag_manager)

            return inner

        return wrapper
