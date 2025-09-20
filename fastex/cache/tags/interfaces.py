from abc import ABC, abstractmethod
from typing import Any, TypeVar

from fastex.cache.backend.interfaces import ICacheBackend
from fastex.cache.tags import CacheTagsEnum
from fastex.cache.tags.extractor.interfaces import ITagExtractor

R = TypeVar("R")


class ICacheTags(ABC):
    @abstractmethod
    def __init__(
        self,
        backend: ICacheBackend,
        tags: list[str | CacheTagsEnum] | None = None,
        extractors: list[ITagExtractor] | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def invalidate_tags(
        self,
        tags: list[str | CacheTagsEnum],
        excluded_tags: list[str | CacheTagsEnum],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def set_tags(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def extract_tags(self, context: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def append_tag(self, tag: str | CacheTagsEnum) -> None:
        raise NotImplementedError
