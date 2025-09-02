from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from fastex.cache.backend.interfaces import CacheBackend
from fastex.cache.key_builder.interfaces import KeyBuilder
from fastex.cache.manager.base import BaseCacheManager
from fastex.cache.manager.interfaces import IDecoratorCacheManager
from fastex.cache.tags import CacheTagsEnum
from fastex.cache.tags.extractor.interfaces import TagExtractor
from fastex.cache.tags.interfaces import AbstractCacheTags
from fastex.utils import _filter_arguments, maybe_await

R = TypeVar("R")


class FunctionCacheManager(BaseCacheManager, IDecoratorCacheManager):
    """Manager for Function Caching"""

    def __init__(
        self,
        backend: CacheBackend,
        tag_manager: type[AbstractCacheTags],
        key_builder: KeyBuilder,
        tag_extractors: list[TagExtractor] | None = None,
    ):
        super().__init__(backend, tag_manager)
        self.key_builder = key_builder
        self.tag_extractors = tag_extractors or []

    def cache_decorator(
        self,
        ttl: int = 3600,
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

                cache_key = await self.key_builder.build_key(func, **filtered_kwargs)

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
