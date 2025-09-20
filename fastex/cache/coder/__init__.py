from typing import Literal

from .interfaces import ICacheCoder
from .json_coder import JsonCacheCoder
from .pickle_coder import PickleCacheCoder

CoderChoices = {
    "json": JsonCacheCoder,
    "pickle": PickleCacheCoder,
}
CoderChoiceType = Literal["json", "pickle"]

__all__ = [
    "ICacheCoder",
    "JsonCacheCoder",
    "PickleCacheCoder",
    "CoderChoiceType",
    "CoderChoices",
]
