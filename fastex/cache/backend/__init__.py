from typing import Literal

from .interfaces import ICacheBackend
from .redis_backend import RedisCacheBackend

BackendChoices = {
    "redis": RedisCacheBackend,
}
BackendChoiceType = Literal["redis"]

__all__ = ["ICacheBackend", "RedisCacheBackend", "BackendChoiceType", "BackendChoices"]
