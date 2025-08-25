import inspect
from datetime import datetime, timedelta
from typing import Any

from redis import asyncio as aredis
from redis import exceptions as redis_exc

from fastex.limiter.backend.base import BaseLimiterBackend
from fastex.limiter.backend.enums import FallbackMode
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.interfaces import LimiterBackendConnectConfig
from fastex.limiter.backend.redis.schemas import RedisLimiterBackendConnectConfig
from fastex.limiter.backend.redis.scripts import LuaScript, SlidingWindowScript
from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.backend.utils import filter_arguments
from fastex.limiter.config import limiter_settings
from fastex.limiter.schemas import RateLimitConfig
from fastex.logging import log


class RedisLimiterBackend(BaseLimiterBackend):
    """Redis backend for rate limiting."""

    _redis: aredis.Redis | None
    _script_sha: str | None
    _lua_script: LuaScript | None

    async def _load_script(self) -> None:
        """Load Lua script into Redis and store its SHA."""
        try:
            script_content = self.lua_script.get_script()
            self._script_sha = await self.redis.script_load(script_content)
            log.debug(f"Lua script loaded with SHA: {self._script_sha}")

        except Exception as e:
            log.error(f"Failed to load Lua script: {e}")
            raise LimiterBackendError(f"Failed to load Lua script: {e}")

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def connect(
        self,
        config: LimiterBackendConnectConfig,
    ) -> None:
        """Connect to the Redis service."""
        if not isinstance(config, RedisLimiterBackendConnectConfig):
            raise LimiterBackendError(
                "Invalid config type. Expected RedisLimiterBackendConfig"
            )

        if isinstance(config.redis_client, str):
            self._redis = aredis.from_url(config.redis_client)  # type: ignore
        else:
            self._redis = config.redis_client
        log.debug("Redis connection established")

        self._fallback_mode = config.fallback_mode or limiter_settings.FALLBACK_MODE
        self._lua_script = config.lua_script or SlidingWindowScript()
        await self._load_script()

    async def disconnect(self):
        """Disconnect from the Redis service."""
        if self._redis:
            await self._redis.aclose()
            log.debug("Redis connection closed")
        self._redis = None
        self._script_sha = None

    async def check_limit(self, key: str, config: RateLimitConfig) -> RateLimitResult:
        """Check if the given key exceeds the rate limit in Redis."""
        try:
            extra_params = self.lua_script.extra_params()

            result = self.redis.evalsha(
                self.script_sha,
                1,
                key,
                str(config.times),
                str(config.total_milliseconds),
                *extra_params,
            )

            result = await self._maybe_await(result)

            retry_after_ms, current = self.lua_script.parse_result(result)

            if retry_after_ms > 0:
                reset_time = datetime.now() + timedelta(milliseconds=retry_after_ms)
                return RateLimitResult(
                    is_exceeded=True,
                    limit_times=config.times,
                    retry_after_ms=retry_after_ms,
                    remaining_requests=config.times - current,
                    reset_time=reset_time,
                )

            return RateLimitResult(
                is_exceeded=False,
                limit_times=config.times,
                remaining_requests=config.times - current,
            )

        except (redis_exc.ConnectionError, redis_exc.RedisError) as e:
            log.error(f"[RateLimiter] Redis unavailable: {e}. Skipping rate limit.")
            return await self._handle_fallback(e, config)

    def is_connected(self, raise_exc: bool = False) -> bool:
        """Check if connected to Redis and Lua script is loaded."""
        connected = self._redis is not None and self._script_sha is not None

        if not connected and raise_exc:
            raise LimiterBackendError("Redis not connected or Lua script not loaded")

        return connected

    def composite_config(
        self,
        redis_client: aredis.Redis | str,
        fallback_mode: FallbackMode | None = None,
        lua_script: LuaScript | None = None,
    ) -> dict[str, Any]:
        return filter_arguments(self.connect, redis_client, fallback_mode, lua_script)

    @property
    def redis(self) -> aredis.Redis:
        if not self._redis:
            raise LimiterBackendError("Redis not connected")
        return self._redis

    @property
    def script_sha(self) -> str:
        if not self._script_sha:
            raise LimiterBackendError("Lua script not loaded")
        return self._script_sha

    @property
    def lua_script(self) -> LuaScript:
        if not self._lua_script:
            raise LimiterBackendError("Lua script object not set")
        return self._lua_script
