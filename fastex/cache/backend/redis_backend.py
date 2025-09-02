from typing import Any

from redis import asyncio as aioredis

from fastex.cache.backend.interfaces import CacheBackend
from fastex.cache.coder.interface import CacheCoder
from fastex.logging.logger import FastexLogger
from fastex.utils import maybe_await


class RedisCacheBackend(CacheBackend):
    def __init__(self, coder: CacheCoder) -> None:
        self._coder = coder
        self._redis: aioredis.Redis | None = None
        self.logger = FastexLogger(name="RedisCacheBackend")

    async def connect(self, url: str) -> None:
        """Connect to the Redis server."""
        if not self.is_initialized():
            self._redis = await aioredis.Redis.from_url(url)
            self.logger.info("Connected to Redis server at %s", url)

    async def close(self) -> None:
        """Close the Redis connection."""
        if self.is_initialized():
            await self.redis.aclose()
            self.logger.info("Closed Redis connection")
            self._redis = None

    async def get_value(self, key: str) -> Any:
        """Retrieve a value from the cache by its key."""
        cached = await self.redis.get(key)
        return self.coder.decode(cached) if cached else None

    async def set_value(self, key: str, value: Any, ttl: int) -> None:
        """Store a value in the cache with a specified time-to-live (ttl)."""
        encoded = self.coder.encode(value)
        await self.redis.set(key, encoded, ttl)

    async def delete(self, key: str) -> None:
        """Delete a value from the cache by its key."""
        await self.redis.delete(key)

    async def add_tag(self, tag: str, key: str) -> None:
        """Associate a key with a tag for cache invalidation purposes."""
        added = self.redis.sadd(f"tag:{tag}", key)
        await maybe_await(added)

    async def get_tag_members(self, tag: str) -> set[Any]:
        """Get all keys associated with a specific tag."""
        tag_key = f"tag:{tag}"
        keys = self.redis.smembers(tag_key)
        keys = await maybe_await(keys)
        return keys

    async def invalidate_keys(self, keys: list[str]) -> None:
        """Invalidate multiple keys."""
        if keys:
            await self.redis.delete(*keys)

    def is_initialized(self) -> bool:
        """Check if the redis cache backend is initialized."""
        return bool(self.redis)

    @property
    def redis(self) -> aioredis.Redis:
        if not self._redis:
            raise RuntimeError("Redis client is not initialized.")
        return self._redis

    @property
    def coder(self) -> CacheCoder:
        return self._coder
