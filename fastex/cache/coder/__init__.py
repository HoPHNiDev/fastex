from typing import Literal

from .interface import CacheCoder
from .json_coder import JsonCacheCoder
from .pickle_coder import PickleCacheCoder

CoderChoices = {
    "json": JsonCacheCoder,
    "pickle": PickleCacheCoder,
}
CoderChoiceType = Literal["json", "pickle"]

__all__ = [
    "CacheCoder",
    "JsonCacheCoder",
    "PickleCacheCoder",
    "CoderChoiceType",
    "CoderChoices",
]
