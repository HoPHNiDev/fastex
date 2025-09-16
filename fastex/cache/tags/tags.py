import inspect
from enum import Enum
from typing import (
    Any,
    TypeVar,
    Callable,
    ParamSpec,
    Coroutine,
    overload,
    Optional,
)

from fastex.cache.backend.interfaces import CacheBackend
from fastex.cache.config import cache_settings
from fastex.cache.tags import CacheTagsEnum
from fastex.cache.tags.extractor.extractor import CompositeTagExtractor
from fastex.cache.tags.extractor.interfaces import TagExtractor
from fastex.cache.tags.interfaces import AbstractCacheTags
from fastex.logging.logger import FastexLogger

P = ParamSpec("P")
R = TypeVar("R")


@overload
def tags_enabled(
    func: Callable[P, Coroutine[Any, Any, R]],
) -> Callable[P, Coroutine[Any, Any, Optional[R]]]: ...
@overload
def tags_enabled(func: Callable[P, R]) -> Callable[P, Optional[R]]: ...


def tags_enabled(func: Callable[P, Any]) -> Callable[P, Any]:
    if inspect.iscoroutinefunction(func):

        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Optional[Any]:
            if not cache_settings.TAGS_ENABLED:
                return None
            return await func(*args, **kwargs)

        return wrapper
    else:

        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Optional[Any]:  # type: ignore
            if not cache_settings.TAGS_ENABLED:
                return None
            return func(*args, **kwargs)

        return wrapper


class CacheTags(AbstractCacheTags):
    def __init__(
        self,
        backend: CacheBackend,
        tags: list[str | CacheTagsEnum] | None = None,
        extractors: list[TagExtractor] | None = None,
    ) -> None:
        self._tags = tags or list()
        self._backend = backend
        self._extractor = CompositeTagExtractor(extractors) if extractors else None
        self.logger = FastexLogger(name="CacheTags")

    @tags_enabled
    async def invalidate_tags(
        self,
        tags: list[str | CacheTagsEnum],
        excluded_tags: list[str | CacheTagsEnum],
    ) -> None:
        if not cache_settings.TAGS_ENABLED:
            return
        key_sets = await self._get_tags_members(tags)

        excluded_key_sets = await self._get_tags_members(excluded_tags)

        if key_sets:
            keys = set.intersection(*key_sets)
            if excluded_key_sets:
                keys = keys - set().union(*excluded_key_sets)
            self.logger.debug("Invalidating keys: %s for tags: %s", keys, tags)
            await self._backend.invalidate_keys(list(keys))

    @tags_enabled
    async def set_tags(self, key: str) -> None:
        if not cache_settings.TAGS_ENABLED:
            return
        for tag in set(self._tags):
            if isinstance(tag, Enum):
                tag = tag.value
            await self._backend.add_tag(tag, key)

    @tags_enabled
    def append_tag(self, tag: str | CacheTagsEnum) -> None:
        if isinstance(tag, Enum):
            tag = tag.value
        if tag not in self._tags:
            self._tags.append(tag)

    @tags_enabled
    async def extract_tags(self, context: dict[str, Any]) -> None:
        if not self._extractor:
            return

        extracted_tags = await self._extractor.extract_tags(context=context)

        if extracted_tags:
            self._tags.extend(extracted_tags)
            self._tags = list(set(self._tags))
            self.logger.debug("Extracted tags: %s", extracted_tags)

    async def _get_tags_members(
        self,
        tags: list[str | CacheTagsEnum],
    ) -> list[set[str]]:
        key_sets = []
        for tag in tags:
            if isinstance(tag, Enum):
                tag = tag.value
            members = await self._backend.get_tag_members(tag)
            key_sets.append(members)
        return key_sets
