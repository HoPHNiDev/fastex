from abc import abstractmethod, ABC
from types import FunctionType
from typing import Any, Protocol, ClassVar, Awaitable

from starlette.requests import Request


class FunctionCallbackType(Protocol):
    def __call__(self, func: FunctionType, **kwargs: Any) -> str | Awaitable[str]: ...


class HttpCallbackType(Protocol):
    def __call__(self, request: Request, identity_id: str | None = None) -> Any: ...


class IFunctionKeyBuilder(ABC):
    callback_func: ClassVar[FunctionCallbackType | None] = None

    @classmethod
    @abstractmethod
    async def build_key(cls, func: FunctionType, **kwargs: Any) -> str:
        raise NotImplementedError


class IHttpKeyBuilder(ABC):
    callback_func: ClassVar[HttpCallbackType | None] = None

    @classmethod
    @abstractmethod
    async def build_key(cls, request: Request, identity_id: str | None = None) -> str:
        raise NotImplementedError
