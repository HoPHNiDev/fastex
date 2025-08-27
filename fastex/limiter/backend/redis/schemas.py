import redis.asyncio as aredis

from fastex.limiter.backend.enums import FallbackMode
from fastex.limiter.backend.interfaces import LimiterBackendConnectConfig
from fastex.limiter.backend.redis.scripts import LuaScript


class RedisLimiterBackendConnectConfig(LimiterBackendConnectConfig):
    redis_client: aredis.Redis | str
    fallback_mode: FallbackMode | None = None
    lua_script: LuaScript | None = None

    class Config:
        extra = "forbid"
