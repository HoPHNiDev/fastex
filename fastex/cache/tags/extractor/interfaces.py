from abc import ABC
from typing import Any


class ITagExtractor(ABC):
    async def extract_tags(self, context: dict[str, Any]) -> list[str]:
        raise NotImplementedError
