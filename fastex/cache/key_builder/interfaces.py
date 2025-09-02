from typing import Any, Protocol


class KeyBuilder(Protocol):
    @staticmethod
    async def build_key(*args: Any, **kwargs: Any) -> str: ...
