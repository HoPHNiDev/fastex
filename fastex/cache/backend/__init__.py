from typing import Literal

from .interfaces import CacheBackend
from .redis_backend import RedisCacheBackend

BackendChoices = {
    "redis": RedisCacheBackend,
}
BackendChoiceType = Literal["redis"]

__all__ = ["CacheBackend", "RedisCacheBackend", "BackendChoiceType", "BackendChoices"]
