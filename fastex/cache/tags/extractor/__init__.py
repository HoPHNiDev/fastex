from typing import Literal

from .interfaces import TagExtractor
from .extractor import (
    ParameterTagExtractor,
    RequestTagExtractor,
    ResultTagExtractor,
    CompositeTagExtractor,
)

ExtractorChoices = {
    "parameter": ParameterTagExtractor,
    "request": RequestTagExtractor,
    "result": ResultTagExtractor,
}
ExtractorChoiceType = list[Literal["parameter", "request", "result"]]

__all__ = [
    "TagExtractor",
    "ParameterTagExtractor",
    "RequestTagExtractor",
    "ResultTagExtractor",
    "CompositeTagExtractor",
    "ExtractorChoices",
    "ExtractorChoiceType",
]
