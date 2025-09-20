import inspect
from typing import cast

from fastex.cache.backend import BackendChoiceType, BackendChoices, ICacheBackend
from fastex.cache.backend.redis_backend import RedisCacheBackend
from fastex.cache.coder import CoderChoiceType, CoderChoices, ICacheCoder
from fastex.cache.coder.pickle_coder import PickleCacheCoder
from fastex.cache.manager import FunctionCacheManager, HttpCacheManager
from fastex.cache.manager.key_builder.interfaces import (
    IFunctionKeyBuilder,
    IHttpKeyBuilder,
    HttpCallbackType,
    FunctionCallbackType,
)
from fastex.cache.manager.key_builder.key_builder import (
    FunctionKeyBuilder,
    HttpKeyBuilder,
)
from fastex.cache.tags import ExtractorChoiceType, ExtractorChoices, ITagExtractor
from fastex.cache.tags.extractor.extractor import (
    ParameterTagExtractor,
    ResultTagExtractor,
    RequestTagExtractor,
)
from fastex.cache.tags.tags import CacheTags

__redis_backend = RedisCacheBackend(coder=PickleCacheCoder)

__func_manager = FunctionCacheManager(
    backend=__redis_backend,
    tag_manager=CacheTags,
    tag_extractors=[
        ParameterTagExtractor(),
        ResultTagExtractor(),
        RequestTagExtractor(),
    ],
)
func_cache = __func_manager.cache_decorator

__http_manager = HttpCacheManager(
    backend=__redis_backend,
    tag_manager=CacheTags,
    tag_extractors=[
        ParameterTagExtractor(),
        ResultTagExtractor(),
        RequestTagExtractor(),
    ],
)
http_cache = __http_manager.cache_decorator


def __build_cache_components(
    coder: CoderChoiceType | ICacheCoder | None = None,
    backend: BackendChoiceType | ICacheBackend | None = None,
    extractors: ExtractorChoiceType | list[ITagExtractor] | None = None,
) -> tuple[ICacheBackend | None, list[ITagExtractor] | None]:
    """Build and return cache_backend and tag_extractors."""
    cache_backend: ICacheBackend | None = None

    if backend:
        if inspect.isclass(backend) and issubclass(backend, ICacheBackend):
            cache_backend = backend
        else:
            if not coder:
                raise ValueError("Backend could not be initialized without coder")

            if inspect.isclass(coder) and issubclass(coder, ICacheCoder):
                cache_coder = coder
            elif isinstance(coder, str):
                cache_coder = CoderChoices[coder]
            else:
                raise TypeError(
                    f"{type(coder)} is not valid | choose one of {list(CoderChoices.keys())} "
                    f"or provide an ICacheCoder subclass"
                )

            if not isinstance(backend, str):
                raise TypeError("Backend must be str when coder is provided")
            cache_backend = BackendChoices[backend](cache_coder)

    tag_extractors: list[ITagExtractor] | None = None
    if extractors:
        if all(
            isinstance(ext, str)
            for ext in extractors
            if not isinstance(extractors, str)
        ):
            tag_extractors = [ExtractorChoices[cast(str, e)]() for e in extractors]
        elif all(
            inspect.isclass(ext) and issubclass(ext, ITagExtractor)
            for ext in extractors
        ):
            tag_extractors = cast(list[ITagExtractor], extractors)
        else:
            raise TypeError(
                f"Extractors invalid | choose from {list(ExtractorChoices.keys())} "
                f"or provide subclasses of ITagExtractor"
            )

    return cache_backend, tag_extractors


def configure_func_cache(
    coder: CoderChoiceType | ICacheCoder | None = None,
    backend: BackendChoiceType | ICacheBackend | None = None,
    extractors: ExtractorChoiceType | list[ITagExtractor] | None = None,
    key_builder: IFunctionKeyBuilder | FunctionCallbackType | None = None,
) -> None:
    """Configure the function cache manager with custom coder, backend, and extractors."""
    cache_backend, tag_extractors = __build_cache_components(coder, backend, extractors)

    if cache_backend:
        __func_manager.backend = cache_backend

    if tag_extractors:
        __func_manager.tag_extractors = tag_extractors

    if key_builder:
        if inspect.isfunction(key_builder):
            HttpKeyBuilder.callback_func = key_builder
        elif inspect.isclass(key_builder) and issubclass(
            key_builder, IFunctionKeyBuilder
        ):
            __func_manager.key_builder = key_builder


def configure_http_cache(
    coder: CoderChoiceType | ICacheCoder | None = None,
    backend: BackendChoiceType | ICacheBackend | None = None,
    extractors: ExtractorChoiceType | list[ITagExtractor] | None = None,
    key_builder: IHttpKeyBuilder | HttpCallbackType | None = None,
) -> None:
    """Configure the HTTP cache manager with custom coder, backend, and extractors."""
    cache_backend, tag_extractors = __build_cache_components(coder, backend, extractors)

    if cache_backend:
        __http_manager.backend = cache_backend

    if tag_extractors:
        __http_manager.tag_extractors = tag_extractors

    if key_builder:
        if inspect.isfunction(key_builder):
            FunctionKeyBuilder.callback_func = key_builder
        elif inspect.isclass(key_builder) and issubclass(key_builder, IHttpKeyBuilder):
            __http_manager.key_builder = key_builder
