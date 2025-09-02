from abc import ABC, ABCMeta
from enum import Enum, EnumMeta


class ABCEnumMeta(ABCMeta, EnumMeta):
    pass


class CacheTagsEnum(ABC, Enum, metaclass=ABCEnumMeta):
    """
    Enum for cache tags used to categorize and manage cached data.
    Each tag represents a specific category of cached items, allowing for efficient invalidations and lookups.
    """
