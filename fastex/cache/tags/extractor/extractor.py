from typing import Any

from fastapi import Request
from fastapi_pagination import Page
from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase

from fastex.cache.tags.extractor.interfaces import ITagExtractor


class ParameterTagExtractor(ITagExtractor):
    """Extracts tags from function parameters"""

    async def extract_tags(self, context: dict[str, Any]) -> list[str]:
        params = context.get("parameters", dict())
        tags = []
        for key, value in params:
            if "id" in key.lower() and value is not None:
                tags.append(str(value))
        return tags


class ResultTagExtractor(ITagExtractor):
    """Extracts tags from function result"""

    async def extract_tags(self, context: dict[str, Any]) -> list[str]:
        if "result" not in context:
            return list()
        return self._extract_from_result(context.get("result"))

    def _extract_from_result(self, result: Any) -> list[str]:
        if isinstance(result, dict):
            return [str(v) for k, v in result.items() if "id" in k.lower()]
        elif isinstance(result, BaseModel):
            data = result.model_dump(exclude_none=True, exclude_unset=True)
            return [str(v) for k, v in data.items() if "id" in k.lower()]
        elif isinstance(result, DeclarativeBase):
            return [
                str(getattr(result, key))
                for key in vars(result)
                if "id" in key.lower() and not key.startswith("_")
            ]
        elif isinstance(result, (list, set, Page)):
            items = result.items if isinstance(result, Page) else result
            tags = []
            for item in items:
                tags.extend(self._extract_from_result(item))
            return tags
        return []


class RequestTagExtractor(ITagExtractor):
    """Extracts tags from FastAPI request parameters"""

    async def extract_tags(self, context: dict[str, Any]) -> list[str]:
        request = context.get("request")
        if not isinstance(request, Request):
            return []

        query_params = dict(request.query_params)
        path_params = dict(request.path_params)

        tags = []
        params = query_params | path_params
        for key, value in params.items():
            if "id" in key.lower():
                tags.append(str(value))

        return tags


class CompositeTagExtractor(ITagExtractor):
    """Combines multiple TagExtractors to extract tags from various sources"""

    def __init__(self, extractors: list[ITagExtractor]):
        self.extractors = extractors

    async def extract_tags(self, context: dict[str, Any]) -> list[str]:
        all_tags = []
        for extractor in self.extractors:
            tags = await extractor.extract_tags(context)
            all_tags.extend(tags)
        return list(set(all_tags))
