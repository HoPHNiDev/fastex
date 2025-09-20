from typing import Literal

from .interfaces import ITagExtractor
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
    "ITagExtractor",
    "ParameterTagExtractor",
    "RequestTagExtractor",
    "ResultTagExtractor",
    "CompositeTagExtractor",
    "ExtractorChoices",
    "ExtractorChoiceType",
]
