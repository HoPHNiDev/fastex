import hashlib
import json
from types import FunctionType
from typing import Any

from fastapi import Request
from fastex.cache.manager.key_builder.interfaces import (
    IFunctionKeyBuilder,
    IHttpKeyBuilder,
)
from fastex.utils import maybe_await


class FunctionKeyBuilder(IFunctionKeyBuilder):
    """Builds keys for function calls"""

    @classmethod
    async def build_key(cls, func: FunctionType, **kwargs: Any) -> str:
        if cls.callback_func:
            result = cls.callback_func(func, **kwargs)
            return await maybe_await(result)

        excluded_args = {"session", "self", "cls"}
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in excluded_args}

        cache_key = hashlib.blake2b(
            f"{func.__module__}:{func.__name__}:{filtered_kwargs}".encode()
        ).hexdigest()

        return f"cache:func:{cache_key}"


class HttpKeyBuilder(IHttpKeyBuilder):
    """Builds keys for HTTP requests"""

    @classmethod
    async def build_key(cls, request: Request, identity_id: str | None = None) -> str:
        if cls.callback_func:
            result = cls.callback_func(request, identity_id)
            return await maybe_await(result)

        func_name = f"{request.url.path}:{request.method}"
        query_params = dict(request.query_params)
        path_params = dict(request.path_params)

        payload = {
            "query": query_params,
            "path": path_params,
            "identity": identity_id,
        }

        raw = json.dumps(payload, sort_keys=True)
        hashed = hashlib.blake2b(raw.encode()).hexdigest()

        return f"cache:http:{func_name}:{hashed}"
