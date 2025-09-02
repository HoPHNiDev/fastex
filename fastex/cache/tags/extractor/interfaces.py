from abc import ABC
from typing import Any


class TagExtractor(ABC):
    async def extract_tags(self, context: dict[str, Any]) -> list[str]:
        raise NotImplementedError
