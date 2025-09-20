from collections.abc import Awaitable, Callable
from functools import wraps
from inspect import Parameter, Signature
from typing import Any, ParamSpec, TypeVar, cast

from fastapi import Request, Response
from fastapi.dependencies.utils import get_typed_signature

from fastex.cache.backend.interfaces import ICacheBackend
from fastex.cache.manager.base import BaseCacheManager
from fastex.cache.manager.interfaces import IHttpCacheManager
from fastex.cache.manager.key_builder.key_builder import HttpKeyBuilder
from fastex.cache.tags import CacheTagsEnum
from fastex.cache.tags.extractor.interfaces import ITagExtractor
from fastex.cache.tags.interfaces import ICacheTags
from fastex.utils import maybe_await

P = ParamSpec("P")
R = TypeVar("R")

injected_request = Parameter(
    name="__http_cache_request",
    annotation=Request,
    kind=Parameter.KEYWORD_ONLY,
)
injected_response = Parameter(
    name="__http_cache_response",
    annotation=Response,
    kind=Parameter.KEYWORD_ONLY,
)


class HttpCacheManager(BaseCacheManager, IHttpCacheManager):
    """Manager for HTTP Caching"""

    key_builder = HttpKeyBuilder

    def __init__(
        self,
        backend: ICacheBackend,
        tag_manager: type[ICacheTags],
        tag_extractors: list[ITagExtractor] | None = None,
    ):
        super().__init__(backend, tag_manager)
        self.tag_extractors = tag_extractors or []
        self.cache_status_header = "X-Cache-Status"

    def cache_decorator(
        self,
        ttl: int = 3600,
        tags: list[str | CacheTagsEnum] | None = None,
        identity: Callable[[Request], Awaitable[str | None]] | None = None,
        **kwargs: Any,
    ) -> Callable[[Callable[P, R | Awaitable[R]]], Callable[P, R | Awaitable[R]]]:
        """Decorator for HTTP caching"""
        if tags is None:
            tags = []

        def wrapper(
            func: Callable[P, R | Awaitable[R]],
        ) -> Callable[P, R | Awaitable[R]]:
            wrapped_signature = get_typed_signature(func)
            to_inject: list[Parameter] = []
            self._locate_param(wrapped_signature, injected_request, to_inject)
            self._locate_param(wrapped_signature, injected_response, to_inject)

            @wraps(func)
            async def inner(*args: P.args, **func_kwargs: P.kwargs) -> R:
                tag_manager = self.tag_manager(
                    backend=self.backend, tags=tags, extractors=self.tag_extractors
                )
                request = self._extract_request(args, func_kwargs)
                response = self._extract_response(args, func_kwargs)

                if not request:
                    raise ValueError("Request object not found")

                identity_id = await identity(request) if identity else None

                cache_key = await self.key_builder.build_key(request, identity_id)

                context = {"request": request}
                await tag_manager.extract_tags(context=context)

                if identity_id:
                    tag_manager.append_tag(identity_id)

                async def factory() -> R:
                    res = await maybe_await(func(*args, **func_kwargs))

                    if response:
                        response.headers[self.cache_status_header] = "MISS"

                    result_context = {"result": res, "request": request}
                    await tag_manager.extract_tags(context=result_context)

                    return res

                result = await self.get_or_set(cache_key, factory, ttl, tag_manager)

                if (
                    response
                    and response.headers.get(self.cache_status_header) != "MISS"
                ):
                    response.headers[self.cache_status_header] = "HIT"

                return result

            cast(Any, inner).__signature__ = self._augment_signature(
                wrapped_signature, *to_inject
            )
            return inner

        return wrapper

    @staticmethod
    def _extract_request(args: Any, kwargs: Any) -> Request | None:
        """Extract Request from arguments"""
        for arg in args:
            if isinstance(arg, Request):
                return arg
        return next((v for v in kwargs.values() if isinstance(v, Request)), None)

    @staticmethod
    def _extract_response(args: Any, kwargs: Any) -> Response | None:
        """Extract Response from arguments"""
        for arg in args:
            if isinstance(arg, Response):
                return arg
        return next((v for v in kwargs.values() if isinstance(v, Response)), None)

    @staticmethod
    def _locate_param(
        sig: Signature, dep: Parameter, to_inject: list[Parameter]
    ) -> Parameter:
        """Locate an existing parameter in the decorated endpoint

        If not found, returns the injectable parameter, and adds it to the to_inject list.
        """
        param = next(
            (p for p in sig.parameters.values() if p.annotation is dep.annotation), None
        )
        if param is None:
            to_inject.append(dep)
            param = dep
        return param

    @staticmethod
    def _augment_signature(signature: Signature, *extra: Parameter) -> Signature:
        if not extra:
            return signature

        parameters = list(signature.parameters.values())
        variadic_keyword_params: list[Parameter] = []
        while parameters and parameters[-1].kind is Parameter.VAR_KEYWORD:
            variadic_keyword_params.append(parameters.pop())

        return signature.replace(
            parameters=[*parameters, *extra, *variadic_keyword_params]
        )
