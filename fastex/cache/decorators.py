from fastex.cache.backend import BackendChoiceType, BackendChoices, CacheBackend
from fastex.cache.backend.redis_backend import RedisCacheBackend
from fastex.cache.coder import CoderChoiceType, CoderChoices
from fastex.cache.coder.pickle_coder import PickleCacheCoder
from fastex.cache.manager import FunctionCacheManager, HttpCacheManager
from fastex.cache.tags import ExtractorChoiceType, ExtractorChoices, TagExtractor
from fastex.cache.tags.extractor.extractor import (
    ParameterTagExtractor,
    ResultTagExtractor,
    RequestTagExtractor,
)
from fastex.cache.tags.tags import CacheTags

redis_backend = RedisCacheBackend(coder=PickleCacheCoder)

func_manager = FunctionCacheManager(
    backend=redis_backend,
    tag_manager=CacheTags,
    tag_extractors=[
        ParameterTagExtractor(),
        ResultTagExtractor(),
        RequestTagExtractor(),
    ],
)
func_cache = func_manager.cache_decorator

http_manager = HttpCacheManager(
    backend=redis_backend,
    tag_manager=CacheTags,
    tag_extractors=[
        ParameterTagExtractor(),
        ResultTagExtractor(),
        RequestTagExtractor(),
    ],
)
http_cache = http_manager.cache_decorator


def build_cache_components(
    coder: CoderChoiceType, backend: BackendChoiceType, extractors: ExtractorChoiceType
) -> tuple[CacheBackend, list[TagExtractor]]:
    """Build and return cache_coder and tag_extractors."""
    cache_coder = CoderChoices[coder]
    cache_backend = BackendChoices[backend](cache_coder)
    tag_extractors = [ExtractorChoices[ext]() for ext in extractors]
    return cache_backend, tag_extractors


def configure_func_cache(
    coder: CoderChoiceType, backend: BackendChoiceType, extractors: ExtractorChoiceType
) -> None:
    """Configure the function cache manager with custom coder, backend, and extractors."""
    cache_backend, tag_extractors = build_cache_components(coder, backend, extractors)

    func_manager.backend = cache_backend
    func_manager.tag_extractors = tag_extractors


def configure_http_cache(
    coder: CoderChoiceType, backend: BackendChoiceType, extractors: ExtractorChoiceType
) -> None:
    """Configure the HTTP cache manager with custom coder, backend, and extractors."""
    cache_backend, tag_extractors = build_cache_components(coder, backend, extractors)

    http_manager.backend = cache_backend
    http_manager.tag_extractors = tag_extractors
