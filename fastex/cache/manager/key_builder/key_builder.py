import hashlib
import json
from types import FunctionType
from typing import Any

from fastapi import Request


class FunctionKeyBuilder:
    """Builds keys for function calls"""

    @staticmethod
    async def build_key(func: FunctionType, **kwargs: Any) -> str:
        excluded_args = {"session", "self", "cls"}
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in excluded_args}

        cache_key = hashlib.blake2b(
            f"{func.__module__}:{func.__name__}:{filtered_kwargs}".encode()
        ).hexdigest()

        return f"cache:func:{cache_key}"


class HttpKeyBuilder:
    """Builds keys for HTTP requests"""

    @staticmethod
    async def build_key(request: Request, identity_id: str | None = None) -> str:
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
